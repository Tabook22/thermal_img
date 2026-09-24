"""Links an authorized inspection evidence image to a private thermal workspace."""
import hashlib
import io
import re
from datetime import datetime
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import active_user
from .audit import add_event
from .config import settings
from .database import get_db
from .models import InspectionImageLink, ThermalImage, AnalysisVersion
from .inspection_package import ExportWorkspace

router=APIRouter(prefix="/api/inspection-bridge")

class OpenTicket(BaseModel):
    ticket:str=Field(min_length=32,max_length=100,pattern=r"^[A-Za-z0-9_-]+$")

async def bridge_request(action,**kwargs):
    if len(settings.inspection_bridge_secret)<32:raise HTTPException(503,"Inspection connection is not configured")
    try:
        async with httpx.AsyncClient(timeout=90,follow_redirects=False) as client:
            result=await client.post(settings.inspection_origin.rstrip('/')+'/api/thermal-bridge/'+action,
                headers={'X-Thermal-Service-Key':settings.inspection_bridge_secret},**kwargs)
    except httpx.HTTPError:
        raise HTTPException(502,"The inspection application could not be reached. Your thermal work is kept; try saving again.")
    if not result.is_success:
        try:message=result.json().get('detail','Inspection connection failed')
        except ValueError:message='Inspection connection failed. Please try again.'
        raise HTTPException(result.status_code if result.status_code in (400,403,404,409,410,413,503) else 502,message)
    if len(result.content)>settings.max_upload_mb*1024*1024:raise HTTPException(413,"Inspection image is too large")
    return result

def link_view(link):
    return {'title':link.title,'return_path':link.return_path,'external_image_id':link.external_image_id,'expires_at':link.expires_at.isoformat()+'Z'}

def image_view(image,db):
    from .main import analysis_dict
    latest=db.scalar(select(AnalysisVersion).where(AnalysisVersion.image_id==image.id).order_by(AnalysisVersion.version.desc()).limit(1))
    return {'id':image.id,'name':image.original_name,'classification':image.classification,'sha256':image.sha256,
            'preview_url':f'/api/images/{image.id}/preview','latest_analysis':analysis_dict(latest) if latest else None}

@router.post('/open')
async def open_inspection(body:OpenTicket,background:BackgroundTasks,db:Session=Depends(get_db)):
    from .main import create_inspection, upload_image, start_analysis, decoder
    from .schemas import InspectionCreate, AnalysisStart
    info=(await bridge_request('claim',json=body.model_dump())).json()
    if not re.fullmatch(r'/visits/[1-9][0-9]*',info['return_path']):raise HTTPException(502,'Invalid inspection return address')
    owner=active_user()
    link=db.scalar(select(InspectionImageLink).where(InspectionImageLink.owner_id==owner.id,
        InspectionImageLink.external_user_id==info['user_id'],InspectionImageLink.external_image_id==info['image_id'],InspectionImageLink.source_sha256==info['sha256']))
    if link:
        image=db.get(ThermalImage,link.image_id)
    else:
        content=(await bridge_request('source',json=body.model_dump())).content
        if hashlib.sha256(content).hexdigest()!=info['sha256']:raise HTTPException(409,'Source image changed during transfer. Open it again from the inspection.')
        inspection=create_inspection(InspectionCreate(tower_code=f"Inspection visit {info['visit_id']}",inspector_notes=info['title']),db)
        uploaded=await upload_image(inspection['id'],UploadFile(filename=info['filename'],file=io.BytesIO(content)),db)
        image=db.get(ThermalImage,uploaded['id'])
        link=InspectionImageLink(owner_id=owner.id,image_id=image.id,external_user_id=info['user_id'],external_image_id=info['image_id'],source_sha256=info['sha256'])
        db.add(link)
    link.ticket=body.ticket;link.title=info['title'];link.return_path=info['return_path'];link.expires_at=datetime.fromisoformat(info['expires_at'].replace('Z','+00:00')).replace(tzinfo=None)
    db.commit()
    if not db.scalar(select(AnalysisVersion.id).where(AnalysisVersion.image_id==image.id)) and decoder.available():
        start_analysis(image.id,AnalysisStart(),background,db)
    add_event(db,owner.id,'inspection_import','image','Opened image from inspection application',image=image);db.commit()
    return {'image':image_view(image,db),'link':link_view(link)}

@router.get('/images/{image_id}')
def context(image_id:int,db:Session=Depends(get_db)):
    link=db.scalar(select(InspectionImageLink).where(InspectionImageLink.image_id==image_id,InspectionImageLink.owner_id==active_user().id))
    return {'link':link_view(link) if link else None,'image':image_view(db.get(ThermalImage,image_id),db)}

@router.post('/images/{image_id}/save')
async def save_back(image_id:int,body:ExportWorkspace,db:Session=Depends(get_db)):
    from .main import save_image_workspace, export_material
    link=db.scalar(select(InspectionImageLink).where(InspectionImageLink.image_id==image_id,InspectionImageLink.owner_id==active_user().id))
    if not link:raise HTTPException(404,'This image is not linked to an inspection')
    # Save editable work before attempting the external write, including on conflict/offline.
    save_image_workspace(image_id,body,db)
    if link.expires_at<datetime.utcnow():raise HTTPException(410,'Editing link expired. Your work is saved. Click Process thermal image again in the inspection to resume it.')
    image,_,_,_,report=export_material(image_id,body,db)
    result=(await bridge_request('save',data={'ticket':link.ticket},files={'file':('processed.png',report,'image/png')})).json()
    add_event(db,active_user().id,'inspection_save','export','Saved processed image back to inspection',image=image);db.commit()
    return {'saved':True,'return_path':link.return_path,'external_image_id':link.external_image_id}
