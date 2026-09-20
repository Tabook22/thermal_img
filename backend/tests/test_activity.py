import io
import csv
from datetime import datetime,timedelta
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import ActivityEvent,ActivityVisit
from test_private_workspaces import workspace  # shared isolated database fixture


def test_server_actions_logged_without_sensitive_payloads(workspace):
    factory,engine,_=workspace
    bob=factory("bob")
    assert bob.get("/api/images/1/workspace").status_code==200
    private_note="DO NOT COPY THIS NOTE INTO THE ACTIVITY LOG"
    assert bob.post("/api/images/1/notes",json={"text":private_note,"x":.2,"y":.2}).status_code==201
    assert bob.put("/api/images/1/workspace",json={}).status_code==200
    log=bob.get("/api/activity/log").json()
    assert log["summary"]["sign_ins"]==1
    assert log["summary"]["images"]==1
    assert any(row["action"]=="image_open" and row["image_name"]=="bob.jpg" for row in log["events"])
    assert any(row["action"]=="draft_save" for row in log["events"])
    assert private_note not in str(log)
    assert "Test-Workspace-Password-123" not in str(log)
    assert "session_hash" not in str(log)
    # Polling and health checks do not flood the human action history.
    before=log["total"]
    bob.get("/api/auth/me");bob.get("/api/analyses/1");bob.get("/api/images/1/preview")
    assert bob.get("/api/activity/log").json()["total"]==before
    bob.post("/api/auth/logout")
    with Session(engine) as db:
        assert db.scalar(select(ActivityEvent).where(ActivityEvent.action=="sign_out"))


def test_log_ownership_admin_filters_and_unforgeable_identity(workspace):
    factory,_,_=workspace
    admin=factory("admin");alice=factory("alice");bob=factory("bob")
    assert factory().get("/api/activity/log").status_code==401
    assert alice.get("/api/activity/log?user_id=3").status_code==403
    assert alice.get("/api/activity/export?user_id=3").status_code==403
    assert alice.post("/api/activity/events",json={"action":"sign_in"}).status_code==422
    assert alice.post("/api/activity/events",json={"action":"undo","image_id":1}).status_code==404
    assert alice.post("/api/activity/events",json={"action":"undo","user_id":3}).status_code==201
    bob.post("/api/activity/events",json={"action":"tool_selected","image_id":1,"detail":"line-temperature"})
    own=alice.get("/api/activity/log").json()
    assert all(row["username"]=="alice" for row in own["events"])
    result=admin.get("/api/activity/log?user_id=3").json()
    assert all(row["username"]=="bob" for row in result["events"])
    assert any(row["action"]=="tool_selected" for row in result["events"])
    assert admin.get("/api/activity/log?user_id=3&category=editing&limit=1").json()["total"]==1
    assert admin.get("/api/activity/log?user_id=3&offset=999").json()["events"]==[]
    assert admin.get("/api/activity/log?since=2020-01-02T00:00:00Z&until=2020-01-01T00:00:00Z").status_code==422
    assert admin.delete("/api/admin/users/3").status_code==200
    assert admin.get("/api/activity/log?user_id=3").json()["total"]>=2


def test_visit_lifecycle_out_of_order_and_estimated_end(workspace):
    factory,engine,_=workspace
    bob=factory("bob");alice=factory("alice")
    vid=str(uuid4());payload={"visit_id":vid,"sequence":1,"page":"workspace","image_id":1}
    assert bob.post("/api/activity/presence",json=payload).status_code==200
    assert alice.post("/api/activity/presence",json={**payload,"image_id":None}).status_code==404
    with Session(engine) as db:
        visit=db.get(ActivityVisit,vid);visit.last_seen_at=datetime.utcnow()-timedelta(seconds=30);db.commit()
    assert bob.post("/api/activity/presence",json={**payload,"sequence":3,"page":"history","visible":False}).status_code==200
    assert bob.post("/api/activity/presence",json={**payload,"sequence":2,"ending":True}).json()=={"recorded":False}
    log=bob.get("/api/activity/log").json()
    assert log["visits"][0]["status"]=="Online · background tab"
    assert 29<=log["summary"]["foreground_seconds"]<=40
    assert any(row["summary"]=="Opened Inspections" for row in log["events"])
    assert bob.post("/api/activity/presence",json={**payload,"sequence":4,"ending":True}).status_code==200
    assert "browser reported" in bob.get("/api/activity/log").json()["visits"][0]["status"]
    assert bob.post("/api/activity/presence",json={**payload,"sequence":5}).json()["restart"]
    second=str(uuid4())
    bob.post("/api/activity/presence",json={**payload,"visit_id":second})
    with Session(engine) as db:
        db.get(ActivityVisit,second).last_seen_at=datetime.utcnow()-timedelta(minutes=6);db.commit()
    log=bob.get("/api/activity/log").json()
    assert any("estimated" in row["status"] for row in log["visits"])
    assert any(row["action"]=="visit_timeout" for row in log["events"])
    third=str(uuid4());bob.post("/api/activity/presence",json={**payload,"visit_id":third})
    bob.post("/api/auth/logout")
    with Session(engine) as db:
        assert db.get(ActivityVisit,third).end_reason=="Signed out"


def test_exports_preserve_dates_scope_and_escape_spreadsheet_formulas(workspace):
    factory,engine,_=workspace
    alice=factory("alice");admin=factory("admin")
    with Session(engine) as db:
        db.add(ActivityEvent(user_id=2,occurred_at=datetime(2026,1,2,3,4),action="image_open",category="image",summary="Opened image workspace",image_name="=HYPERLINK(test)",source="server",outcome="success"));db.commit()
    query="user_id=2&since=2026-01-01T00:00:00Z&until=2026-01-03T00:00:00Z"
    result=admin.get(f"/api/activity/export?{query}&format=csv")
    assert result.status_code==200 and "attachment" in result.headers["content-disposition"]
    rows=list(csv.reader(io.StringIO(result.content.decode("utf-8-sig"))))
    assert len(rows)==2 and rows[1][0]=="2026-01-02T03:04:00Z"
    assert rows[1][6].startswith("'=HYPERLINK")
    text=alice.get(f"/api/activity/export?{query}&format=txt")
    assert text.status_code==200 and "@alice" in text.text and "@admin" not in text.text
    assert "no-store" in text.headers["cache-control"]
