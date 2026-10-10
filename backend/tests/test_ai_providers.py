import base64
import io
import json

import httpx
import numpy as np
import pytest
from PIL import Image

from app.ai_enhancement import AIEnhancementRequest, Proposal, propose
from app.ai_providers import PROVIDERS, ProviderError, request_text, provider_schema
from app.ai_settings import read_connection, read_api_key, credential_path
from test_private_workspaces import workspace
from test_ai_enhancement import proposal

KEYS = {"openai": "sk-proj-TEST_ONLY_OpenAI123456789", "anthropic": "sk-ant-TEST_ONLY_Claude123456789", "gemini": "AIzaTEST_ONLY_Gemini123456789"}
URL = "/api/admin/settings/ai"


def response_for(provider, text):
    if provider == "openai":
        return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}
    if provider == "anthropic":
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]}


@pytest.mark.parametrize("provider", list(PROVIDERS))
def test_vision_requests_use_only_selected_origin_and_key(provider, monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json=response_for(provider, json.dumps(proposal())))
    monkeypatch.setattr("app.ai_providers.httpx.post", post)
    source = np.full((60,80,3), 170, dtype=np.uint8)
    message, result = propose(source, AIEnhancementRequest(prompt="Keep the insulator"), KEYS[provider], PROVIDERS[provider]["default_model"], provider)
    assert result.focus and np.all(source == 170)
    url, kwargs = calls[0]
    assert KEYS[provider] not in url and KEYS[provider] not in json.dumps(kwargs["json"])
    assert kwargs["follow_redirects"] is False and kwargs["timeout"] == 70
    assert len(calls) == 1
    if provider == "openai":
        assert url == "https://api.openai.com/v1/responses"
        assert kwargs["headers"] == {"Authorization": "Bearer " + KEYS[provider]}
        encoded = kwargs["json"]["input"][0]["content"][1]["image_url"].split(",")[1]
    elif provider == "anthropic":
        assert url == "https://api.anthropic.com/v1/messages"
        assert kwargs["headers"]["x-api-key"] == KEYS[provider]
        assert "Authorization" not in kwargs["headers"]
        assert kwargs["json"]["output_config"]["format"]["type"] == "json_schema"
        encoded = kwargs["json"]["messages"][0]["content"][0]["source"]["data"]
    else:
        assert url == f"https://generativelanguage.googleapis.com/v1beta/models/{PROVIDERS[provider]['default_model']}:generateContent"
        assert kwargs["headers"] == {"x-goog-api-key": KEYS[provider]}
        assert kwargs["json"]["generationConfig"]["responseFormat"]["text"]["mimeType"] == "application/json"
        encoded = kwargs["json"]["contents"][0]["parts"][0]["inlineData"]["data"]
    preview = Image.open(io.BytesIO(base64.b64decode(encoded)))
    assert preview.size == (80,60) and not preview.getexif()


def test_keys_models_and_active_provider_persist_separately(workspace, monkeypatch):
    admin = workspace[0]("admin")
    bob = workspace[0]("bob")
    for provider in PROVIDERS:
        response = admin.put(URL, json={"provider": provider, "api_key": KEYS[provider], "model": PROVIDERS[provider]["default_model"]})
        assert response.status_code == 200, response.text
        assert response.json()["provider"] == provider
        assert read_connection() == (provider, KEYS[provider], PROVIDERS[provider]["default_model"])
        assert bob.get('/api/ai-enhancement/status').json()["provider"] == provider
        assert all(key not in response.text for key in KEYS.values())
    # Switching uses that provider's existing key; no cross-provider fallback.
    response = admin.put(URL, json={"provider": "anthropic", "model": "claude-sonnet-custom"})
    assert response.status_code == 200
    assert read_connection() == ("anthropic", KEYS["anthropic"], "claude-sonnet-custom")
    assert read_api_key() == KEYS["openai"]  # Reference search remains OpenAI.
    assert all(p["configured"] for p in admin.get(URL).json()["providers"])
    # An already-open editor must not silently send images to a changed company.
    calls = []
    monkeypatch.setattr("app.ai_providers.httpx.post", lambda *a, **k: calls.append(a))
    response = bob.post('/api/images/1/enhancement/ai', json={"prompt": "Keep insulator", "provider": "gemini"})
    assert response.status_code == 409 and not calls
    response = bob.post('/api/images/1/enhancement/ai', json={"prompt": "Keep insulator", "provider": "anthropic", "model": "old-model"})
    assert response.status_code == 409 and not calls
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json=response_for("anthropic", json.dumps(proposal())))
    monkeypatch.setattr("app.ai_providers.httpx.post", post)
    assert bob.post('/api/images/1/enhancement/ai', json={"prompt": "Keep insulator", "provider": "anthropic"}).status_code == 200
    assert calls[0][1]["headers"]["x-api-key"] == KEYS["anthropic"]
    assert calls[0][1]["json"]["model"] == "claude-sonnet-custom"


@pytest.mark.parametrize("provider", list(PROVIDERS))
def test_provider_connection_test_uses_saved_model_without_image(workspace, monkeypatch, provider):
    admin = workspace[0]("admin")
    model = PROVIDERS[provider]["default_model"]
    assert admin.put(URL, json={"provider":provider,"model":model,"api_key":KEYS[provider]}).status_code == 200
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, json=response_for(provider, "OK"))
    monkeypatch.setattr("app.ai_providers.httpx.post", post)
    result = admin.post(URL + '/test')
    assert result.status_code == 200 and result.json()["model"] == model
    assert result.json()["provider"] == provider
    assert "image" not in json.dumps(calls[0]["json"]) and calls[0]["timeout"] == 25


@pytest.mark.parametrize("body", [
    {"provider":"openai","api_key":KEYS["anthropic"]},
    {"provider":"anthropic","api_key":KEYS["openai"]},
    {"provider":"gemini","api_key":KEYS["openai"]},
    {"provider":"unknown","api_key":KEYS["openai"]},
    {"provider":"gemini","model":"x/../../bad?key=abc","api_key":KEYS["gemini"]},
    {"provider":"openai","model":KEYS["openai"],"api_key":KEYS["openai"]},
])
def test_provider_mismatches_and_unsafe_models_are_rejected(workspace, body):
    result = workspace[0]("admin").put(URL, json=body)
    assert result.status_code == 422
    assert not credential_path().exists()
    assert all(key not in result.text for key in KEYS.values())


def test_new_provider_requires_its_own_key(workspace):
    client = workspace[0]("admin")
    assert client.put(URL, json={"api_key":KEYS["openai"]}).status_code == 200
    assert client.put(URL, json={"provider":"gemini"}).status_code == 422
    assert read_connection()[0] == "openai"


@pytest.mark.parametrize("provider", list(PROVIDERS))
def test_malformed_or_incomplete_provider_output_is_safe(provider, monkeypatch):
    for payload in ([], {}, {"candidates": []}, {"content": None}, response_for(provider, "")):
        monkeypatch.setattr("app.ai_providers.httpx.post", lambda *a, **k: httpx.Response(200, json=payload))
        with pytest.raises(ProviderError):
            request_text(provider, KEYS[provider], PROVIDERS[provider]["default_model"], "test")
    monkeypatch.setattr("app.ai_providers.httpx.post", lambda *a, **k: httpx.Response(302, headers={"Location":"https://evil.example"}))
    with pytest.raises(ProviderError):
        request_text(provider, KEYS[provider], PROVIDERS[provider]["default_model"], "test")


@pytest.mark.parametrize("provider", list(PROVIDERS))
def test_all_provider_proposals_enforce_geometry_bounds(provider, monkeypatch):
    invalid = proposal()
    invalid["focus"]["points"][0]["x"] = 7
    monkeypatch.setattr("app.ai_providers.httpx.post", lambda *a, **k: httpx.Response(200, json=response_for(provider, json.dumps(invalid))))
    with pytest.raises(ValueError):
        propose(np.zeros((20,20,3), dtype=np.uint8), AIEnhancementRequest(prompt="Keep insulator"), KEYS[provider], PROVIDERS[provider]["default_model"], provider)
    # Claude schema transformation changes only provider-facing constraints.
    schema = Proposal.model_json_schema()
    adjusted = provider_schema(schema, "anthropic")
    assert schema["properties"]["contrast"]["minimum"] == .5
    assert "minimum" not in adjusted["properties"]["contrast"]
