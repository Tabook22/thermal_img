"""Small server-authored action summaries; never store request bodies or credentials."""
import json
import logging
from datetime import datetime
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from .models import ActivityEvent, ActivityVisit, ThermalImage, User

logger = logging.getLogger(__name__)

def add_event(db, user_id, action, category, summary, *, image=None, outcome="success", source="server", at=None):
    event=ActivityEvent(user_id=user_id,action=action,category=category,summary=summary[:300],outcome=outcome,source=source,
                        occurred_at=at or datetime.utcnow(),image_id=image.id if image else None,
                        image_name=image.original_name if image else None,inspection_id=image.inspection_id if image else None)
    db.add(event)
    return event

def end_visits(db, user_id, reason, session_hash=None):
    stmt=select(ActivityVisit).where(ActivityVisit.user_id==user_id,ActivityVisit.ended_at.is_(None))
    if session_hash: stmt=stmt.where(ActivityVisit.session_hash==session_hash)
    now=datetime.utcnow()
    for visit in db.scalars(stmt).all():
        visit.ended_at=now;visit.end_reason=reason;visit.visible=False
        if reason!="Signed out":
            add_event(db,user_id,"visit_revoked","access",f"Visit ended: {reason}")

# Exclude automatic polling, thumbnails, and pixel hover requests.
GET_ACTIONS={
    "/api/images/{image_id}/workspace":("image_open","image","Opened image workspace"),
    "/api/analyses/{analysis_id}/matrix.csv":("matrix_export","export","Downloaded temperature matrix"),
    "/api/admin/images/{image_id}/review":("admin_image_review","review","Reviewed user image"),
    "/api/admin/images/{image_id}/report":("admin_report_view","review","Viewed saved image report"),
    "/api/library/documents/{document_id}/file":("library_file_view","library","Opened library file"),
    "/api/library/documents/{document_id}/text":("library_text_view","library","Opened library document"),
}

def action_for(path, method):
    if method=="GET": return GET_ACTIONS.get(path)
    if method not in {"POST","PUT","DELETE","PATCH"} or path.startswith("/api/activity/"): return None
    fixed={
        "/api/auth/login":("sign_in","access","Signed in"),
        "/api/auth/logout":("sign_out","access","Signed out"),
        "/api/auth/password":("password_change","account","Changed password"),
        "/api/inspections":("inspection_create","inspection","Created inspection"),
        "/api/inspections/{inspection_id}/images":("image_upload","image","Uploaded image"),
        "/api/inspections/{inspection_id}/packages":("package_import","image","Imported editable inspection package"),
        "/api/images/{image_id}/analyses":("analysis_request","measurement","Requested temperature analysis"),
        "/api/images/{image_id}/workspace":("draft_save","image","Saved image workspace"),
        "/api/images/{image_id}/enhancement/preview":("enhancement_preview","enhancement","Previewed enhancement adjustments"),
        "/api/images/{image_id}/enhancement/auto":("auto_enhance","enhancement","Applied automatic enhancement"),
        "/api/images/{image_id}/enhancement":("enhancement_save","enhancement","Saved enhancement settings"),
        "/api/images/{image_id}/exports/report":("report_export","export","Exported report image"),
        "/api/images/{image_id}/exports/package":("package_export","export","Exported editable inspection package"),
        "/api/images/{image_id}/guide-images":("guide_upload","annotation","Added supporting image"),
        "/api/images/{image_id}/guide-image":("guide_upload","annotation","Added supporting image"),
        "/api/images/{image_id}/capture-note":("capture_note","annotation","Added camera metadata note"),
        "/api/internet/search":("internet_search","research","Searched online references"),
        "/api/library/search":("library_search","library","Searched reference library"),
    }
    if path in fixed:return fixed[path]
    verb={"POST":"Added","PUT":"Updated","PATCH":"Updated","DELETE":"Deleted"}[method]
    for segment,category,name in (("/notes","annotation","note"),("/drawings","annotation","drawing"),
        ("/minimum","measurement","minimum temperature selection"),("/hotspots","measurement","hotspot calculation"),
        ("/regions","measurement","measurement region"),("/admin/users","account","user account"),
        ("/settings/","settings","application settings"),("/library/","library","library item")):
        if segment in path:return (f"{category}_{method.lower()}",category,f"{verb} {name}")
    return None

def record_request(request, response=None, status=200):
    db=getattr(request.state,"audit_db",None);uid=getattr(request.state,"audit_user_id",None)
    if db is None or uid is None:return
    path=request.scope["route"].path
    action=action_for(path,request.method)
    if not action:return
    try:
        if status>=400:db.rollback()
        image_id=getattr(request.state,"audit_image_id",None)
        if status<400 and response and action[0] in {"image_upload","package_import"}:
            data=json.loads(response.body);image_id=data.get("id")
        image=db.get(ThermalImage,image_id) if image_id and status<400 else None
        summary=action[2] if status<400 else f"Action unsuccessful: {action[2]} (HTTP {status})"
        if status<400 and path.startswith("/api/admin/users"):
            target_id=request.path_params.get("user_id")
            if not target_id and response:target_id=json.loads(response.body).get("id")
            target=db.get(User,target_id) if target_id else None
            if target:summary+=f" · @{target.username}"
        add_event(db,uid,action[0],action[1],summary,image=image,outcome="success" if status<400 else "failed")
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not persist activity event")

class ActivityRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handler(request):
            try:
                response=await original(request)
            except (HTTPException,RequestValidationError) as exc:
                await run_in_threadpool(record_request,request,None,getattr(exc,"status_code",422))
                raise
            except Exception:
                await run_in_threadpool(record_request,request,None,500)
                raise
            await run_in_threadpool(record_request,request,response,response.status_code)
            return response
        return handler
