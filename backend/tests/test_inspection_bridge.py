import hashlib
import io
from PIL import Image
from datetime import datetime,timedelta
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import InspectionImageLink,ThermalImage
from app import inspection_bridge as bridge
from app.main import decoder
from test_private_workspaces import workspace

def test_import_resume_save_and_private_workspace(workspace,monkeypatch):
    factory,engine,root=workspace
    bob=factory('bob');alice=factory('alice')
    content=(root/'previews/bob.jpg').read_bytes();sent=[]
    async def remote(action,**kwargs):
        if action=='claim':return httpx.Response(200,json={'image_id':91,'user_id':7,'visit_id':34,'title':'T94 · TH Full','image_type':'TH Full','filename':'source.jpg','sha256':hashlib.sha256(content).hexdigest(),'return_path':'/visits/34','expires_at':(datetime.utcnow()+timedelta(hours=12)).isoformat()+'Z'})
        if action=='source':return httpx.Response(200,content=content)
        sent.append(kwargs['files']['file'][1]);return httpx.Response(200,json={'saved':True})
    monkeypatch.setattr(bridge,'bridge_request',remote);monkeypatch.setattr(decoder,'available',lambda:False)
    result=bob.post('/api/inspection-bridge/open',json={'ticket':'a'*43});assert result.status_code==200,result.text
    data=result.json();image_id=data['image']['id']
    assert 'ticket' not in str(data) and data['link']['return_path']=='/visits/34'
    assert alice.get(f'/api/inspection-bridge/images/{image_id}').status_code==404
    assert alice.post(f'/api/inspection-bridge/images/{image_id}/save',json={}).status_code==404
    crop={'x':.25,'y':.25,'width':.5,'height':.5}
    assert bob.post(f'/api/inspection-bridge/images/{image_id}/save',json={'insulator_label':'inner','crop':crop}).status_code==200
    assert sent[0].startswith(b'\x89PNG')
    assert Image.open(io.BytesIO(sent[0])).size==(10,10)
    resumed=bob.post('/api/inspection-bridge/open',json={'ticket':'b'*43}).json()
    assert resumed['image']['id']==image_id
    assert bob.get(f'/api/images/{image_id}/workspace').json()['insulator_label']=='inner'
    assert bob.get(f'/api/images/{image_id}/workspace').json()['crop']==crop
    with Session(engine) as db:
        image=db.get(ThermalImage,image_id);assert (root/image.storage_name).read_bytes()==content
        link=db.scalar(select(InspectionImageLink));link.expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert bob.post(f'/api/inspection-bridge/images/{image_id}/save',json={'insulator_label':'outer'}).status_code==410
    assert bob.get(f'/api/images/{image_id}/workspace').json()['insulator_label']=='outer'

def test_remote_error_preserves_local_draft(workspace,monkeypatch):
    factory,engine,_=workspace;bob=factory('bob')
    with Session(engine) as db:
        db.add(InspectionImageLink(owner_id=3,image_id=1,external_user_id=7,external_image_id=91,source_sha256='a'*64,ticket='a'*43,title='Test',return_path='/visits/34',expires_at=datetime.utcnow()+timedelta(hours=1)));db.commit()
    async def offline(*args,**kwargs):raise HTTPException(409,'Image changed')
    monkeypatch.setattr(bridge,'bridge_request',offline)
    result=bob.post('/api/inspection-bridge/images/1/save',json={'insulator_label':'inner'})
    assert result.status_code==409
    assert bob.get('/api/images/1/workspace').json()['insulator_label']=='inner'
