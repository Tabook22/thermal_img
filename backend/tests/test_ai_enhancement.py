import base64
import io
import json

import numpy as np
import pytest
from PIL import Image
from sqlalchemy.orm import Session

from app.ai_enhancement import AIEnhancementRequest, propose, request_slot
from app.config import settings
from app.enhancement import EnhancementSettings, render_enhancement
from app.inspection_package import ExportWorkspace, render_report_png
from app.models import ThermalImage
from test_private_workspaces import workspace

POINTS=[{"x":.3,"y":.1},{"x":.7,"y":.1},{"x":.7,"y":.9},{"x":.3,"y":.9}]


def proposal(**overrides):
    return dict(message="Review this approximate insulator outline.",apply=True,
        focus={"points":[dict(p) for p in POINTS]},background_dim=1,clarity=0,detail=0,shadows=0,
        concealed_areas=[],brightness=0,contrast=1,denoise=0,sharpen=0,palette="original",**overrides)


def mock_provider(monkeypatch,plan):
    calls=[]
    def post(url,**kwargs):
        calls.append(kwargs)
        class Response:
            status_code=200
            def json(self):
                return {"status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":json.dumps(plan)}]}]}
        return Response()
    monkeypatch.setattr("app.ai_enhancement.httpx.post",post)
    return calls


def test_provider_receives_only_visual_preview_and_validated_settings(monkeypatch):
    calls=mock_provider(monkeypatch,proposal())
    source=np.full((60,80,3),170,np.uint8)
    message,result=propose(source,AIEnhancementRequest(prompt="Hide the background"),"private-key","gpt-4.1")
    payload=calls[0]["json"]
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert "private-key" not in json.dumps(payload)
    image_url=payload["input"][0]["content"][1]["image_url"]
    image=Image.open(io.BytesIO(base64.b64decode(image_url.split(",")[1])))
    assert not image.getexif()
    assert result.focus.background_dim==1
    assert np.all(source==170)


def test_masks_preserve_source_matrix_and_round_trip_report():
    source=np.full((60,80,3),170,np.uint8)
    matrix=np.full((60,80),27.4,dtype=np.float32);valid=np.ones_like(matrix,dtype=bool)
    value=EnhancementSettings(focus={"points":POINTS,"background_dim":1,"clarity":0,"detail":0,"shadows":0})
    workspace=ExportWorkspace(enhancement=value)
    restored=ExportWorkspace.model_validate_json(workspace.model_dump_json())
    report=np.asarray(Image.open(io.BytesIO(render_report_png(source,matrix,valid,restored,[],{}))))
    assert np.all(report[20,1,:3]==0)
    assert np.all(report[20,40,:3]==170)
    assert np.all(source==170)
    assert np.all(matrix==np.float32(27.4))
    separate=EnhancementSettings(concealed_areas=[{"points":POINTS}])
    rendered=render_enhancement(source,separate,matrix,valid)
    pixels=np.asarray(Image.open(io.BytesIO(base64.b64decode(rendered["preview"].split(",")[1]))))
    assert np.all(pixels[20,40]==0) and np.all(pixels[20,1]==170)
    assert not rendered["quantitative_legend"]


def test_endpoint_never_saves_proposal_and_is_private(workspace,monkeypatch):
    factory,engine,path=workspace
    monkeypatch.setattr(settings,"openai_api_key","test-only")
    calls=mock_provider(monkeypatch,proposal())
    before=(path/"matrix.npz").read_bytes()
    body={"prompt":"Hide background","analysis_id":1}
    for name in (None,"alice","admin"):
        response=factory(name).post('/api/images/1/enhancement/ai',json=body)
        assert response.status_code==(401 if name is None else 404)
    assert not calls
    bob=factory("bob")
    response=bob.post('/api/images/1/enhancement/ai',json=body)
    assert response.status_code==200,response.text
    with Session(engine) as db:
        assert "enhancement" not in db.get(ThermalImage,1).metadata_json
    assert before==(path/"matrix.npz").read_bytes()
    assert bob.post('/api/images/1/enhancement/ai',json={**body,"analysis_id":999}).status_code==404
    assert len(calls)==1
    monkeypatch.setattr(settings,"openai_api_key",None)
    assert bob.get('/api/ai-enhancement/status').json()["available"] is False
    assert bob.post('/api/images/1/enhancement/ai',json=body).status_code==503


def test_invalid_ai_outline_and_refusal_leave_workspace_unchanged(workspace,monkeypatch):
    factory,_,_=workspace
    monkeypatch.setattr(settings,"openai_api_key","test-only")
    client=factory("bob")
    plan=proposal();plan["focus"]["points"][0]={"x":4,"y":0}
    mock_provider(monkeypatch,plan)
    response=client.post('/api/images/1/enhancement/ai',json={"prompt":"Hide mountains"})
    assert response.status_code==502
    assert "valid outline" in response.text
    plan=proposal();plan["apply"]=False
    mock_provider(monkeypatch,plan)
    assert client.post('/api/images/1/enhancement/ai',json={"prompt":"Hide mountains"}).json()["settings"] is None


def test_concurrency_slot_releases_after_failure():
    with request_slot(99):
        with pytest.raises(RuntimeError):
            with request_slot(99): pass
    with pytest.raises(ValueError):
        with request_slot(99): raise ValueError("test")
    with request_slot(99): pass
