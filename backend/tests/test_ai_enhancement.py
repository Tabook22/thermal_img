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
        background_mode="dim",concealed_mode="dim",concealed_areas=[],brightness=0,contrast=1,denoise=0,sharpen=0,palette="original",**overrides)


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


def test_blue_context_preserves_target_texture_measurements_and_report(monkeypatch):
    from app.insulator_focus import focus_mask
    y, x = np.mgrid[:160, :240]
    light = ((x + y) % 200 + 30).astype(np.uint8)
    source = np.stack([light, light // 2, light // 4], axis=-1)
    before = source.copy()
    matrix = np.linspace(20, 80, 160 * 240, dtype=np.float32).reshape(160, 240)
    matrix_before = matrix.copy()
    valid = np.ones(matrix.shape, bool)
    plan = proposal()
    plan["background_mode"] = "blue"
    mock_provider(monkeypatch, plan)
    _, options = propose(source, AIEnhancementRequest(prompt="Suppress background heat colors"), "test", "gpt-4.1")
    restored = ExportWorkspace.model_validate_json(ExportWorkspace(enhancement=options, temperature_visibility={"maximum":False,"minimum":False}).model_dump_json())
    mask = focus_mask(source.shape, restored.enhancement.focus).astype(bool)
    preview = render_enhancement(source, restored.enhancement, matrix, valid)
    rendered = np.asarray(Image.open(io.BytesIO(base64.b64decode(preview["preview"].split(",")[1]))))
    assert np.array_equal(rendered[mask], source[mask])
    assert np.all(rendered[~mask, 2] > rendered[~mask, 1])
    assert np.all(rendered[~mask, 1] > rendered[~mask, 0])
    assert np.ptp(rendered[~mask, 2]) > 10  # Texture remains visible, not a flat fill.
    assert not preview["quantitative_legend"]
    report_image = Image.open(io.BytesIO(render_report_png(source, matrix, valid, restored, [], {})))
    assert np.array_equal(np.asarray(report_image), rendered)
    assert "Visually processed" in report_image.info["Processing"]
    assert np.array_equal(source, before)
    assert np.array_equal(matrix, matrix_before)


def test_separate_blue_area_leaves_rest_of_scene_exact(monkeypatch):
    from app.insulator_focus import focus_mask
    plan = proposal()
    plan.update(focus=None, concealed_mode="blue", concealed_areas=[{"points": POINTS}])
    mock_provider(monkeypatch, plan)
    source = np.full((60, 80, 3), [200, 80, 10], np.uint8)
    _, options = propose(source, AIEnhancementRequest(prompt="Only suppress mountain heat colors"), "test", "gpt-4.1")
    rendered = render_enhancement(source, options)
    pixels = np.asarray(Image.open(io.BytesIO(base64.b64decode(rendered["preview"].split(",")[1]))))
    mask = focus_mask(source.shape, options.concealed_areas[0]).astype(bool)
    assert np.array_equal(pixels[~mask], source[~mask])
    assert np.all(pixels[mask, 2] > pixels[mask, 0])


def test_natural_result_preserves_hotspots_and_feathers_only_outside(monkeypatch):
    from app.insulator_focus import focus_mask, natural_context
    plan = proposal()
    plan.update(background_mode="natural", clarity=.6, detail=.4)
    mock_provider(monkeypatch, plan)
    source = np.full((400, 1000, 3), [160, 40, 90], np.uint8)
    source[150:170, 500:520] = [255, 240, 20]
    source[:, :100] = [2, 0, 24]
    before = source.copy()
    matrix = np.full((400, 1000), 25, np.float32)
    matrix[150:170, 500:520] = 45
    original_matrix = matrix.copy()
    _, settings = propose(source, AIEnhancementRequest(prompt="Smooth natural background"), "test", "gpt-4.1")
    restored = ExportWorkspace.model_validate_json(ExportWorkspace(enhancement=settings, temperature_visibility={"maximum":False,"minimum":False}).model_dump_json())
    rendered = render_enhancement(source, restored.enhancement, matrix, np.ones_like(matrix, bool))
    output = np.asarray(Image.open(io.BytesIO(base64.b64decode(rendered["preview"].split(",")[1]))))
    mask = focus_mask(source.shape, settings.focus).astype(bool)
    assert np.array_equal(output[mask], source[mask])  # Includes every hotspot pixel.
    edge = np.flatnonzero(mask[200])[0]
    context = natural_context(source)
    assert np.array_equal(output[200, edge-10], context[200, edge-10])
    assert context[200, edge-1, 0] < output[200, edge-1, 0] < source[200, edge-1, 0]
    assert np.array_equal(output[:, :100], context[:, :100])
    assert np.max(context[:, :100]) < 30  # Dark background is not lifted to flat blue.
    assert rendered["focus_info"]["statistics"]["maximum_c"] == 45
    report = np.asarray(Image.open(io.BytesIO(render_report_png(source, matrix, np.ones_like(matrix, bool), restored, [], {}))))
    assert np.array_equal(report, output)
    assert np.array_equal(source, before) and np.array_equal(matrix, original_matrix)
