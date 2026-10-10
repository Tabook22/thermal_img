"""Credential management must be private, persistent, and effective immediately."""
import json
import os

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ai_settings
from app.config import settings
from app.models import ActivityEvent
from test_private_workspaces import workspace
from test_ai_enhancement import mock_provider, proposal

URL = "/api/admin/settings/ai"
# Synthetic fixture; never contact the provider with this value.
KEY = "sk-proj-TEST_ONLY_NotARealCredential123456789"


def test_admin_only_and_csrf(workspace):
    factory, _, path = workspace
    for user, code in ((None, 401), ("alice", 403)):
        client = factory(user)
        for method, suffix in (("GET", ""), ("PUT", ""), ("POST", "/test")):
            response = client.request(method, URL + suffix, json={"api_key": KEY})
            assert response.status_code == code
            assert KEY not in response.text
    admin = factory("admin")
    for headers in ({"X-Thermal-Request": ""}, {"Origin": "https://evil.example"}):
        assert admin.put(URL, json={"api_key": KEY}, headers=headers).status_code == 403
    assert not (path / "ai-settings/.env").exists()


def test_save_persists_activates_and_never_returns_or_audits_secret(workspace, monkeypatch):
    factory, engine, _ = workspace
    monkeypatch.setattr(settings, "openai_api_key", None)
    admin = factory("admin")
    bob = factory("bob")
    assert admin.get(URL).json()["configured"] is False
    assert bob.get("/api/ai-enhancement/status").json()["available"] is False
    response = admin.put(URL, json={"api_key": "  " + KEY + "  "})
    assert response.status_code == 200, response.text
    assert response.json()["configured"] and response.json()["saved_in_env"]
    assert "no-store" in response.headers["cache-control"]
    assert KEY not in response.text and KEY not in admin.get(URL).text
    assert ai_settings.read_api_key() == KEY
    assert f"OPENAI_API_KEY='{KEY}'" in ai_settings.credential_path().read_text()
    if os.name != "nt":
        assert ai_settings.credential_path().stat().st_mode & 0o777 == 0o600
        assert ai_settings.credential_path().parent.stat().st_mode & 0o777 == 0o700
    # The new file takes priority even when the process environment has an older value.
    monkeypatch.setattr(settings, "openai_api_key", "old-environment-value")
    assert ai_settings.read_api_key() == KEY
    assert bob.get("/api/ai-enhancement/status").json()["available"] is True
    calls = mock_provider(monkeypatch, proposal())
    response = bob.post("/api/images/1/enhancement/ai", json={"prompt": "Focus on insulator"})
    assert response.status_code == 200, response.text
    assert calls[0]["headers"]["Authorization"] == "Bearer " + KEY
    with Session(engine) as db:
        events = db.scalars(select(ActivityEvent)).all()
        assert any(e.action == "ai_key_update" for e in events)
        assert all(KEY not in e.summary for e in events)


@pytest.mark.parametrize("body", [
    {"api_key": KEY + "\nOTHER_SECRET=bad"},
    {"api_key": KEY, "unexpected": KEY},
    {"api_key": {"secret": KEY}},
    {"api_key": "not-valid"},
])
def test_validation_never_echoes_input(workspace, body):
    client = workspace[0]("admin")
    response = client.put(URL, json=body)
    assert response.status_code == 422
    assert KEY not in response.text and "OTHER_SECRET" not in response.text
    assert not ai_settings.credential_path().exists()
    response = client.put(URL, content='{"api_key":"' + KEY, headers={"Content-Type": "application/json"})
    assert response.status_code == 422 and KEY not in response.text


def test_replacement_preserves_other_values_and_failed_write_keeps_old_key(workspace, monkeypatch):
    client = workspace[0]("admin")
    ai_settings.persist_api_key(KEY)
    path = ai_settings.credential_path()
    path.write_text(path.read_text() + "# preserved\nUNRELATED='keep'\n", encoding="utf-8")
    replacement = KEY + "New"
    assert client.put(URL, json={"api_key": replacement}).status_code == 200
    assert ai_settings.read_api_key() == replacement
    assert "# preserved\nUNRELATED='keep'" in path.read_text()
    before = path.read_bytes()
    def fail(*args):
        raise PermissionError(KEY)
    monkeypatch.setattr(ai_settings.os, "replace", fail)
    response = client.put(URL, json={"api_key": KEY})
    assert response.status_code == 503 and KEY not in response.text
    assert path.read_bytes() == before
    assert list(path.parent.glob(".env-*")) == []


@pytest.mark.parametrize("provider_status, expected", [(200, 200), (401, 422), (403, 422), (429, 422), (500, 502)])
def test_connection_is_explicit_bounded_and_redacts_provider_errors(workspace, monkeypatch, provider_status, expected):
    client = workspace[0]("admin")
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(provider_status, json={"status": "completed", "secret": KEY, "output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}]})
    monkeypatch.setattr("app.ai_providers.httpx.post", post)
    assert client.put(URL, json={"api_key": KEY}).status_code == 200
    assert not calls  # Saving never sends the key to a provider without testing/editing.
    response = client.post(URL + "/test")
    assert response.status_code == expected, response.text
    assert KEY not in response.text
    url, kwargs = calls[0]
    assert url == "https://api.openai.com/v1/responses"
    assert kwargs["headers"]["Authorization"] == "Bearer " + KEY
    assert kwargs["timeout"] == 25
    assert kwargs["json"]["store"] is False
    assert "image" not in json.dumps(kwargs["json"])
    assert kwargs["json"]["model"] == settings.openai_enhancement_model


def test_missing_key_and_network_error(workspace, monkeypatch):
    client = workspace[0]("admin")
    monkeypatch.setattr(settings, "openai_api_key", None)
    assert client.post(URL + "/test").status_code == 422
    ai_settings.persist_api_key(KEY)
    def fail(*args, **kwargs):
        raise httpx.ReadTimeout(KEY)
    monkeypatch.setattr("app.ai_providers.httpx.post", fail)
    response = client.post(URL + "/test")
    assert response.status_code == 502 and KEY not in response.text
    assert ai_settings.read_api_key() == KEY


def test_model_choices_preserve_saved_custom_model_and_key(workspace):
    client = workspace[0]("admin")
    custom = "account-specific-vision-model"
    assert client.put(URL, json={"api_key": KEY, "model": custom}).status_code == 200
    before = ai_settings.credential_path().read_bytes()
    status = client.get(URL).json()
    assert status["model"] == custom
    for provider in status["providers"]:
        choices = [model["id"] for model in provider["models"]]
        assert len(set(choices)) == len(choices) and len(choices) > 1
        assert provider["default_model"] in choices
    assert ai_settings.credential_path().read_bytes() == before
    # Selecting a suggested model reuses the stored key, without sending it again.
    alternative = next(p for p in status["providers"] if p["id"] == "openai")["models"][1]["id"]
    response = client.put(URL, json={"provider": "openai", "model": alternative})
    assert response.status_code == 200 and response.json()["model"] == alternative
    assert ai_settings.read_api_key() == KEY and KEY not in response.text
