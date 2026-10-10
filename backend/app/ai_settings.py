"""Administrator-managed AI credentials, persisted outside code and image exports."""
import os
import re
import tempfile
import threading
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key
from fastapi import APIRouter, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from .audit import ActivityRoute
from .auth import active_user
from .config import settings
from .ai_enhancement import request_slot

_write_lock = threading.Lock()


def credential_path() -> Path:
    return settings.storage_root / "ai-settings" / ".env"


def read_api_key() -> str:
    """Read on use so every worker and subsequent restart sees saved settings."""
    path = credential_path()
    try:
        if path.exists():
            return (dotenv_values(path, interpolate=False).get("OPENAI_API_KEY") or "").strip()
    except (OSError, UnicodeError):
        raise HTTPException(503, {"message": "AI settings could not be read. Ask the server administrator to check storage permissions."}) from None
    return (settings.openai_api_key or "").strip()


def persist_api_key(key: str):
    path = credential_path()
    temporary = None
    try:
        with _write_lock:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt": path.parent.chmod(0o700)
            descriptor, name = tempfile.mkstemp(prefix=".env-", dir=path.parent)
            temporary = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                if path.exists(): output.write(path.read_text(encoding="utf-8"))
            set_key(str(temporary), "OPENAI_API_KEY", key, quote_mode="always")
            temporary.chmod(0o600)
            with temporary.open("r+b") as content: os.fsync(content.fileno())
            os.replace(temporary, path)
    except (OSError, UnicodeError):
        raise HTTPException(503, {"message": "The key was not saved. Check the server's private storage permissions and try again."}) from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass  # Do not replace the safe error with a filesystem traceback.


class CredentialRoute(ActivityRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                # FastAPI's default validation response includes input values.
                raise HTTPException(422, {"message": "Enter a valid OpenAI API key beginning with sk-, without spaces or extra lines."}) from None
        return handler


router = APIRouter(prefix="/api/admin/settings/ai", route_class=CredentialRoute)


class KeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value):
        key = value.get_secret_value().strip()
        if not re.fullmatch(r"sk-[A-Za-z0-9_-]{16,1000}", key):
            raise ValueError("Invalid API key")
        return SecretStr(key)


@router.get("")
def ai_settings_status():
    return {"configured": bool(read_api_key()), "provider": "OpenAI",
            "model": settings.openai_enhancement_model, "saved_in_env": credential_path().is_file()}


@router.put("")
def save_ai_settings(body: KeyInput):
    persist_api_key(body.api_key.get_secret_value())
    return ai_settings_status()


@router.post("/test")
def test_ai_connection():
    key = read_api_key()
    if not key: raise HTTPException(422, {"message": "Save an API key first."})
    try:
        with request_slot(active_user().id):
            response = httpx.post("https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {key}"}, timeout=25,
                json={"model": settings.openai_enhancement_model, "store": False,
                      "input": "Reply with OK.", "max_output_tokens": 32})
        if response.status_code in (401, 403):
            raise HTTPException(422, {"message": "OpenAI rejected the key or model access. Check the key's project permissions, then try again."})
        if response.status_code == 429:
            raise HTTPException(422, {"message": "OpenAI reports a usage or rate limit. Check API billing and limits, then try again."})
        if response.status_code != 200 or response.json().get("status") != "completed":
            raise HTTPException(502, {"message": "The AI connection test did not complete. Check model access or try again later."})
        return {"connected": True, "message": "Connected to OpenAI. AI enhancement is ready.", "model": settings.openai_enhancement_model}
    except RuntimeError:
        raise HTTPException(429, {"message": "An AI request is already running. Try again when it finishes."}) from None
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, {"message": "Unable to verify the AI connection. Your saved key is unchanged; try again shortly."}) from None
