import io
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.auth import COOKIE, hash_password
from app.config import settings
from app.database import get_db
from app.main import app
from app.models import AnalysisVersion, Base, Inspection, Region, ThermalImage, Tower, User, UserSession

PASSWORD = "Test-Workspace-Password-123"
HEADERS = {"X-Thermal-Request": "1"}

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(settings,"storage_root",tmp_path)
    monkeypatch.setattr(settings,"session_cookie_secure",False)
    monkeypatch.setattr(settings,"session_cookie_path","/")
    engine=create_engine(f"sqlite:///{tmp_path/'test.db'}",connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    password_hash=hash_password(PASSWORD)
    with Session(engine) as db:
        for index,username in enumerate(("admin","alice","bob"),1):
            db.add(User(id=index,username=username,display_name=username.title(),password_hash=password_hash,
                        role="admin" if index==1 else "user",must_change_password=False))
        db.flush()
        db.add(Tower(id=1,tower_code="PRIVATE",owner_id=3,circuit="Bob circuit"))
        db.flush();db.add(Inspection(id=1,tower_id=1,owner_id=3));db.flush()
        (tmp_path/"previews").mkdir();Image.new("RGB",(20,20),"red").save(tmp_path/"previews/bob.jpg")
        db.add(ThermalImage(id=1,inspection_id=1,original_name="bob.jpg",storage_name="previews/bob.jpg",
                           sha256="a"*64,classification="ordinary_image",metadata_json={"preview_path":"previews/bob.jpg"}))
        db.flush()
        np.savez(tmp_path/"matrix.npz",temperatures=np.ones((20,20))*25,valid_mask=np.ones((20,20),dtype=bool))
        db.add(AnalysisVersion(id=1,image_id=1,version=1,status="completed",matrix_path="matrix.npz",width=20,height=20,stats_json={}))
        db.flush();db.add(Region(id=1,analysis_id=1,name="Bob region",kind="rectangle",geometry_json={"points":[{"x":0,"y":0},{"x":19,"y":19}]},stats_json={}))
        db.commit()
    def database():
        with Session(engine,expire_on_commit=False) as db: yield db
    app.dependency_overrides[get_db]=database
    clients=[]
    def client(username=None):
        result=TestClient(app,headers=HEADERS);clients.append(result)
        if username:
            response=result.post("/api/auth/login",json={"username":username,"password":PASSWORD})
            assert response.status_code==200,response.text
        return result
    yield client,engine,tmp_path
    for item in clients: item.close()
    app.dependency_overrides.clear();engine.dispose()

def test_login_cookies_csrf_and_logout(workspace):
    factory,engine,_=workspace
    client=factory()
    assert client.get("/api/inspections").status_code==401
    assert client.post("/api/auth/login",headers={"X-Thermal-Request":""},json={"username":"alice","password":PASSWORD}).status_code==403
    assert client.post("/api/auth/login",headers={"Origin":"https://evil.example"},json={"username":"alice","password":PASSWORD}).status_code==403
    response=client.post("/api/auth/login",json={"username":"alice","password":PASSWORD})
    assert response.status_code==200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    token=client.cookies[COOKIE]
    with Session(engine) as db:
        assert db.scalar(select(UserSession)).token_hash!=token
        assert PASSWORD not in db.get(User,2).password_hash
    assert client.get("/api/auth/me").json()["username"]=="alice"
    assert "no-store" in client.get("/api/inspections").headers["cache-control"]
    assert client.post("/api/auth/logout").status_code==200
    client.cookies.set(COOKIE,token)
    assert client.get("/api/auth/me").status_code==401

def test_every_resource_route_checks_owner_before_read_or_write(workspace):
    factory,_,_=workspace
    alice=factory("alice");admin=factory("admin")
    count=0
    for route in app.routes:
        path=route.path
        if path.startswith("/api/admin/"): continue
        if not any(marker in path for marker in ("{image_id}","{inspection_id}","{analysis_id}","{region_id}")): continue
        for key,value in {"image_id":"1","inspection_id":"1","analysis_id":"1","region_id":"1","x":"0","y":"0","note_id":"guess","drawing_id":"guess","guide_id":"guess"}.items(): path=path.replace("{"+key+"}",value)
        for method in route.methods:
            response=alice.request(method,path,json={})
            # Multipart endpoints need a real upload for FastAPI to evaluate dependencies.
            assert response.status_code==404,(method,path,response.text)
            assert admin.request(method,path,json={}).status_code==404,(method,path)
            count+=1
    assert count>=30
    bob=factory("bob")
    assert bob.get("/api/images/1/preview").status_code==200
    assert bob.get("/api/analyses/1/matrix.csv").status_code==200
    assert bob.get("/api/images/1/workspace").status_code==200
    assert alice.get("/api/inspections").json()==[]
    assert len(bob.get("/api/inspections").json())==1
    # A matching tower code must not leak another user's circuit or ownership.
    created=alice.post("/api/inspections",json={"tower_code":"PRIVATE","circuit":"Alice circuit","owner_id":3})
    assert created.status_code==201
    assert created.json()["circuit"]=="Alice circuit"
    assert bob.get(f"/api/inspections/{created.json()['id']}/images").status_code==404

def test_library_files_and_search_are_private(workspace):
    factory,_,_=workspace
    alice=factory("alice");bob=factory("bob")
    created=alice.post("/api/library/documents",files={"file":("secret.txt",b"Alice private transformer evidence","text/plain")})
    assert created.status_code==201,created.text
    document_id=created.json()["id"]
    assert len(alice.get("/api/library/documents").json())==1
    assert bob.get("/api/library/documents").json()==[]
    assert bob.get(f"/api/library/documents/{document_id}/file").status_code==404
    assert bob.delete(f"/api/library/documents/{document_id}").status_code==404
    assert bob.put(f"/api/library/documents/{document_id}/text",json={"text":"overwrite"}).status_code==404
    assert bob.post("/api/library/search",json={"query":"transformer"}).json()["results"]==[]


def test_admin_can_review_all_saved_work_but_cannot_edit_it(workspace):
    factory,engine,_=workspace
    admin=factory("admin");alice=factory("alice");guest=factory()
    paths=("/api/admin/workspaces", "/api/admin/inspections", "/api/admin/inspections/1/images",
           "/api/admin/images/1/preview", "/api/admin/images/1/review", "/api/admin/images/1/report")
    for path in paths:
        assert guest.get(path).status_code==401
        assert alice.get(path).status_code==403
    owners=admin.get(paths[0]).json()
    assert next(item for item in owners if item["username"]=="bob")["image_count"]==1
    assert next(item for item in owners if item["username"]=="alice")["inspection_count"]==0
    result=admin.get(paths[1]).json()
    assert result["total"]==1 and result["items"][0]["owner"]["username"]=="bob"
    assert admin.get(paths[1],params={"owner_id":2}).json()["total"]==0
    assert admin.get(paths[1],params={"q":"BOB.JPG"}).json()["total"]==1
    assert admin.get(paths[1],params={"q":"%"}).json()["total"]==0
    assert admin.get(paths[1],params={"offset":1}).json()["items"]==[]
    assert admin.get(paths[2]).json()[0]["preview_url"]=="/api/admin/images/1/preview"
    with Session(engine) as db:
        image=db.get(ThermalImage,1)
        image.metadata_json={**image.metadata_json,"notes":[{"id":"note","text":"Saved evidence","x":.1,"y":.2}],
                             "workspace":{"insulator_label":"inner","notes":[]}}
        db.commit()
    review=admin.get(paths[4])
    assert review.status_code==200,review.text
    assert review.json()["workspace"]["notes"][0]["text"]=="Saved evidence"
    assert review.json()["workspace"]["insulator_label"]=="inner"
    assert review.json()["regions"][0]["name"]=="Bob region"
    rendered=admin.get(paths[5])
    assert rendered.status_code==200,rendered.text
    assert rendered.headers["content-type"]=="image/png"
    assert "no-store" in rendered.headers["cache-control"]
    assert Image.open(io.BytesIO(rendered.content)).size==(20,20)
    assert admin.put("/api/images/1/workspace",json={}).status_code==404
    assert admin.delete("/api/regions/1").status_code==404
    assert admin.post("/api/admin/images/1/report",json={}).status_code==405
    assert admin.get("/api/admin/images/999/review").status_code==404
    assert admin.get("/api/admin/inspections/999/images").status_code==404
    # Archived work remains reviewable; deleting its account does not transfer it.
    assert admin.delete("/api/admin/users/3").status_code==200
    assert admin.get(paths[4]).json()["owner"]["status"]=="Deleted"
    assert admin.get(paths[1]).json()["items"][0]["owner"]["id"]==3
    assert alice.get("/api/images/1/preview").status_code==404

def test_admin_management_forced_password_and_session_revocation(workspace):
    factory,_,_=workspace
    admin=factory("admin");alice=factory("alice")
    payload={"username":"newuser","display_name":"New User","password":PASSWORD,"role":"user"}
    assert alice.post("/api/admin/users",json=payload).status_code==403
    assert alice.get("/api/admin/users").status_code==403
    assert alice.put("/api/settings/branding",json={}).status_code==403
    created=admin.post("/api/admin/users",json=payload);assert created.status_code==201
    uid=created.json()["id"]
    new=factory("newuser")
    assert new.get("/api/inspections").status_code==403
    changed=new.post("/api/auth/password",json={"current_password":PASSWORD,"new_password":"New-Private-Password-456"})
    assert changed.status_code==200,changed.text
    assert new.get("/api/inspections").json()==[]
    assert admin.put(f"/api/admin/users/{uid}",json={**payload,"password":None,"is_active":False}).status_code==200
    assert new.get("/api/auth/me").status_code==401
    assert admin.put(f"/api/admin/users/{uid}",json=payload).status_code==200
    new=factory("newuser")
    assert admin.delete(f"/api/admin/users/{uid}").status_code==200
    assert new.get("/api/auth/me").status_code==401
    assert admin.delete("/api/admin/users/1").status_code==409
    assert admin.put("/api/admin/users/1",json={**payload,"username":"admin","role":"user","password":None}).status_code==409

def test_expired_sessions_and_login_throttle(workspace):
    factory,engine,_=workspace
    alice=factory("alice")
    with Session(engine) as db:
        for session in db.scalars(select(UserSession)).all(): session.expires_at=datetime.utcnow()-timedelta(seconds=1)
        db.commit()
    assert alice.get("/api/auth/me").status_code==401
    for _ in range(10):
        assert alice.post("/api/auth/login",json={"username":"unknown","password":"wrong"}).status_code==401
    assert alice.post("/api/auth/login",json={"username":"unknown","password":"wrong"}).status_code==429

def test_existing_sqlite_migration_preserves_images_and_bootstrap(tmp_path,monkeypatch):
    database_url=f"sqlite:///{tmp_path/'migration.db'}"
    monkeypatch.setattr(settings,"database_url",database_url)
    monkeypatch.setattr(settings,"storage_root",tmp_path)
    config=Config(str(Path(__file__).parents[1]/"alembic.ini"))
    config.set_main_option("script_location",str(Path(__file__).parents[1]/"alembic"))
    command.upgrade(config,"0001")
    engine=create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO towers (id,tower_code) VALUES (1,'OLD')"))
        connection.execute(text("INSERT INTO inspections (id,tower_id) VALUES (1,1)"))
        connection.execute(text("INSERT INTO thermal_images (id,inspection_id,original_name,storage_name,sha256,classification) VALUES (1,1,'original.jpg','source.jpg','abc','ordinary_image')"))
    command.upgrade(config,"head")
    from app import bootstrap_admin
    monkeypatch.setattr(bootstrap_admin,"SessionLocal",lambda:Session(engine))
    credentials=tmp_path/"initial-login.txt"
    bootstrap_admin.bootstrap("owner",credentials)
    with Session(engine) as db:
        owner=db.scalar(select(User))
        assert owner.role=="admin" and owner.must_change_password
        assert db.get(Inspection,1).owner_id==owner.id
        assert db.get(Tower,1).owner_id==owner.id
        assert db.get(ThermalImage,1).storage_name=="source.jpg"
    assert "Username: owner" in credentials.read_text()
    with pytest.raises(RuntimeError): bootstrap_admin.bootstrap("intruder",tmp_path/"second.txt")
    engine.dispose()
