"""Per-user activity browsing and bounded, best-effort browser presence."""
import csv
import hashlib
import io
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .audit import add_event
from .database import get_db
from .models import ActivityEvent, ActivityVisit, Inspection, ThermalImage, User

router=APIRouter(prefix="/api/activity")
Page=Literal["workspace","upload","history","about","settings","help","users","account","admin-work","activity"]
PAGES={"workspace":"Analysis","upload":"Upload","history":"Inspections","about":"About","settings":"Settings", "help":"Help Me","users":"Users","account":"Change password","admin-work":"All user work","activity":"Activity log"}

def actor():
    from .auth import active_user
    return active_user()

def scope(user_id):
    user=actor()
    if user.role!="admin" and user_id is not None and user_id!=user.id:
        raise HTTPException(403,"You can view only your own activity")
    return user_id if user.role=="admin" else user.id

def owned_image(db, image_id):
    if image_id is None:return None
    image=db.get(ThermalImage,image_id)
    inspection=db.get(Inspection,image.inspection_id) if image else None
    if not inspection or inspection.owner_id!=actor().id:
        raise HTTPException(404,"Image not found in your workspace")
    return image

def expire_visits(db, user_id=None):
    cutoff=datetime.utcnow()-timedelta(minutes=5)
    stmt=select(ActivityVisit).where(ActivityVisit.ended_at.is_(None),ActivityVisit.last_seen_at<cutoff)
    if user_id is not None:stmt=stmt.where(ActivityVisit.user_id==user_id)
    for visit in db.scalars(stmt).all():
        visit.ended_at=visit.last_seen_at;visit.end_reason="Connection lost or inactive (estimated)";visit.visible=False
        add_event(db,visit.user_id,"visit_timeout","access","Visit stopped responding; end time is last contact (estimated)",source="presence",at=visit.last_seen_at)

class Presence(BaseModel):
    visit_id: UUID
    sequence: int = Field(ge=1,le=2_000_000_000)
    page: Page = "workspace"
    image_id: int | None = Field(None,ge=1)
    visible: bool = True
    ending: bool = False

@router.post("/presence")
def presence(body:Presence, request:Request, db:Session=Depends(get_db)):
    user=actor();image=owned_image(db,body.image_id);now=datetime.utcnow()
    expire_visits(db,user.id)
    key=hashlib.sha256(request.cookies.get("thermal_session","").encode()).hexdigest()
    visit=db.get(ActivityVisit,str(body.visit_id))
    if visit and (visit.user_id!=user.id or visit.session_hash!=key):
        raise HTTPException(404,"Visit not found")
    if visit and visit.ended_at:
        db.commit();return {"restart":True}
    if visit and body.sequence<=visit.sequence:
        db.commit();return {"recorded":False}
    if not visit:
        visit=ActivityVisit(id=str(body.visit_id),user_id=user.id,session_hash=key,started_at=now,last_seen_at=now,
                            page=body.page,visible=body.visible,foreground_seconds=0,sequence=0)
        db.add(visit)
        add_event(db,user.id,"visit_start","access",f"Opened application · {PAGES[body.page]}",source="presence")
    else:
        gap=max(0,(now-visit.last_seen_at).total_seconds())
        if visit.visible and gap<=90:visit.foreground_seconds+=gap
        if visit.page!=body.page:
            add_event(db,user.id,"page_view","navigation",f"Opened {PAGES[body.page]}",source="browser",image=image)
    visit.last_seen_at=now;visit.page=body.page;visit.image_id=body.image_id;visit.visible=body.visible;visit.sequence=body.sequence
    if body.ending:
        visit.ended_at=now;visit.end_reason="Page closed or reloaded (browser reported)";visit.visible=False
        add_event(db,user.id,"visit_close","access","Page closed or reloaded (browser reported)",source="browser",image=image)
    db.commit();return {"recorded":True}

class BrowserEvent(BaseModel):
    action: Literal["tool_selected","local_edit","undo","redo","image_close","display_change"]
    image_id: int | None = Field(None,ge=1)
    detail: str = Field("",max_length=100)

TOOLS={"select","rectangle","circle","line-temperature","point","spot","note","delete","draw-freehand","draw-line","draw-ellipse","draw-arrow","bend-arrow"}
LOCAL_EDITS={"Add temperature marker","Move temperature marker","Delete temperature marker","Move insulator label","Resize insulator label",
             "Add inner insulator label","Add outer insulator label","Remove inner insulator label","Remove outer insulator label",
             "Move supporting image","Resize supporting image","Zoom supporting image","Remove supporting image"}
DISPLAY={"Temperature marker visibility","Measurement filter","Image zoom","Show original image","Compare enhancement"}

@router.post("/events",status_code=201)
def browser_event(body:BrowserEvent, db:Session=Depends(get_db)):
    image=owned_image(db,body.image_id)
    valid=TOOLS if body.action=="tool_selected" else LOCAL_EDITS if body.action=="local_edit" else DISPLAY if body.action=="display_change" else {""}
    if body.detail not in valid:raise HTTPException(422,"Unknown activity detail")
    summaries={"tool_selected":f"Selected tool: {body.detail}","local_edit":body.detail,"undo":"Undo last action","redo":"Redo last action",
               "image_close":"Closed image workspace","display_change":f"Adjusted {body.detail.lower()}"}
    add_event(db,actor().id,body.action,"editing",summaries[body.action],image=image,source="browser")
    db.commit();return {"recorded":True}

def utc(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value and value.tzinfo else value

def bounds(since,until):
    end=utc(until) or datetime.utcnow()+timedelta(seconds=1)
    start=utc(since) or end-timedelta(days=7)
    if start>=end:raise HTTPException(422,"Start date must be before end date")
    return start,end

def event_query(uid,start,end,category):
    stmt=select(ActivityEvent,User).join(User,User.id==ActivityEvent.user_id).where(ActivityEvent.occurred_at>=start,ActivityEvent.occurred_at<end)
    if uid is not None:stmt=stmt.where(ActivityEvent.user_id==uid)
    if category:stmt=stmt.where(ActivityEvent.category==category)
    return stmt

def stamp(value):return value.isoformat()+"Z" if value else None

def event_view(event,user):
    return {"id":event.id,"user_id":user.id,"username":user.username,"display_name":user.display_name,"at":stamp(event.occurred_at),
            "category":event.category,"action":event.action,"summary":event.summary,"outcome":event.outcome,"source":event.source,
            "image_id":event.image_id,"image_name":event.image_name,"inspection_id":event.inspection_id}

@router.get("/log")
def activity_log(user_id:int|None=None,since:datetime|None=None,until:datetime|None=None,category:str=Query("",max_length=30),
                 offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=Depends(get_db)):
    uid=scope(user_id);start,end=bounds(since,until);expire_visits(db,uid);db.commit()
    stmt=event_query(uid,start,end,category)
    selected=stmt.subquery()
    total=db.scalar(select(func.count()).select_from(selected))
    rows=db.execute(stmt.order_by(ActivityEvent.occurred_at.desc(),ActivityEvent.id.desc()).offset(offset).limit(limit)).all()
    # Overview is for the selected user and date range; category filters only the timeline.
    overview=event_query(uid,start,end,"").subquery()
    signins=db.scalar(select(func.count()).select_from(overview).where(overview.c.action=="sign_in",overview.c.outcome=="success"))
    image_count=db.scalar(select(func.count(func.distinct(overview.c.image_id))).where(overview.c.outcome=="success"))
    actions=db.scalar(select(func.count()).select_from(overview))
    focus=db.execute(select(overview.c.category,func.count()).group_by(overview.c.category).order_by(func.count().desc())).all()
    top_images=db.execute(select(overview.c.image_id,overview.c.image_name,func.count()).where(overview.c.image_id.is_not(None),overview.c.outcome=="success").group_by(overview.c.image_id,overview.c.image_name).order_by(func.count().desc()).limit(5)).all()
    visits=select(ActivityVisit,User).join(User,User.id==ActivityVisit.user_id).where(ActivityVisit.started_at>=start,ActivityVisit.started_at<end)
    if uid is not None:visits=visits.where(ActivityVisit.user_id==uid)
    visit_rows=db.execute(visits.order_by(ActivityVisit.started_at.desc()).limit(30)).all()
    durations=db.scalar(select(func.sum(visits.subquery().c.foreground_seconds))) or 0
    return {"total":total,"events":[event_view(e,u) for e,u in rows],
            "summary":{"sign_ins":signins,"images":image_count,"actions":actions,"foreground_seconds":round(durations),
                       "focus":[{"category":c,"count":n} for c,n in focus],
                       "top_images":[{"id":i,"name":name,"actions":n} for i,name,n in top_images]},
            "visits":[{"id":v.id,"username":u.username,"display_name":u.display_name,"started_at":stamp(v.started_at),"last_seen_at":stamp(v.last_seen_at),
                       "ended_at":stamp(v.ended_at),"end_reason":v.end_reason,"foreground_seconds":round(v.foreground_seconds),"page":PAGES.get(v.page,v.page),
                       "status":v.end_reason or ("Online · visible tab" if v.visible else "Online · background tab")} for v,u in visit_rows]}

def csv_safe(value):
    text=str(value or "")
    return "'"+text if text.lstrip().startswith(("=","+","-","@")) or text.startswith(("\t","\r","\n")) else text

@router.get("/export")
def export_log(user_id:int|None=None,since:datetime|None=None,until:datetime|None=None,category:str=Query("",max_length=30),
               format:Literal["csv","txt"]="csv",db:Session=Depends(get_db)):
    uid=scope(user_id);start,end=bounds(since,until);expire_visits(db,uid);db.commit()
    stmt=event_query(uid,start,end,category)
    if db.scalar(select(func.count()).select_from(stmt.subquery()))>100000:
        raise HTTPException(422,"Choose a smaller date range (maximum 100,000 events per export)")
    out=io.StringIO();writer=csv.writer(out) if format=="csv" else None
    if writer:writer.writerow(["Date and time (UTC)","Username","Name","Category","Action","Result","Image","Source"])
    else:out.write(f"Thermal activity log\nUTC {stamp(start)} to {stamp(end)} (exclusive)\n\n")
    for event,user in db.execute(stmt.order_by(ActivityEvent.occurred_at,ActivityEvent.id)):
        if writer:writer.writerow([csv_safe(v) for v in (stamp(event.occurred_at),user.username,user.display_name,event.category,event.summary,event.outcome,event.image_name,event.source)])
        else:out.write(f"{stamp(event.occurred_at)} | @{user.username} | {event.summary} | {event.outcome} | {event.image_name or '—'} | {event.source}\n")
    add_event(db,actor().id,"activity_export","account","Downloaded activity log");db.commit()
    filename=f"thermal-activity-{uid if uid is not None else 'all'}-{start:%Y%m%d}.{format}"
    return Response(out.getvalue().encode("utf-8-sig" if writer else "utf-8"),media_type="text/csv" if writer else "text/plain",
                    headers={"Content-Disposition":f'attachment; filename="{filename}"'})
