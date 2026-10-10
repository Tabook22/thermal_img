"""Administrator-managed AI credentials, persisted outside code and image exports."""
import os
import re
import tempfile
import threading
from pathlib import Path

from dotenv import dotenv_values, set_key
from fastapi import APIRouter, HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

from .audit import ActivityRoute
from .auth import active_user
from .config import settings
from .ai_enhancement import request_slot
from .ai_providers import PROVIDERS, Provider, ProviderError, request_text, valid_model

_write_lock = threading.Lock()


def credential_path() -> Path:
    return settings.storage_root / "ai-settings" / ".env"


def read_values():
    path = credential_path()
    try:
        if path.exists():
            return dotenv_values(path, interpolate=False)
    except (OSError, UnicodeError):
        raise HTTPException(503, {"message": "AI settings could not be read. Ask the server administrator to check storage permissions."}) from None
    return {}


def connection_from(values, provider=None):
    provider = provider or values.get("AI_PROVIDER") or "openai"
    if provider not in PROVIDERS:
        raise HTTPException(503, {"message": "Choose a supported AI provider in Settings."})
    config = PROVIDERS[provider]
    env = config["key_env"]
    fallback_key = getattr(settings, env.lower(), None)
    key = (values.get(env, fallback_key) or "").strip()
    model_env = provider.upper() + "_ENHANCEMENT_MODEL"
    model = (values.get(model_env) or getattr(settings, model_env.lower(), None) or config["default_model"]).strip()
    if not valid_model(model):
        raise HTTPException(503, {"message": "Choose a valid AI model ID in Settings."})
    return provider, key, model


def read_connection(provider=None):
    """Read provider, model and key together so a concurrent save cannot mix them."""
    return connection_from(read_values(), provider)


def read_api_key() -> str:
    # The existing reference web-search feature continues to use OpenAI only.
    return read_connection("openai")[1]


def persist_api_key(key: str):
    persist_values({"OPENAI_API_KEY": key})


def persist_values(values):
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
            for name, value in values.items():
                set_key(str(temporary), name, value, quote_mode="always")
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
                raise HTTPException(422, {"message": "Check the provider, model ID, and API key. Use a key from the selected provider, without spaces or extra lines."}) from None
        return handler


router = APIRouter(prefix="/api/admin/settings/ai", route_class=CredentialRoute)


class KeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Provider = "openai"
    model: str | None = None
    api_key: SecretStr | None = None

    @model_validator(mode="after")
    def validate_fields(self):
        if self.model is not None:
            self.model = self.model.strip()
            if not valid_model(self.model):
                raise ValueError("Invalid model")
        if self.api_key is not None:
            key = self.api_key.get_secret_value().strip()
            pattern = {"openai": r"sk-(?!ant-)[A-Za-z0-9_-]{16,1000}",
                       "anthropic": r"sk-ant-[A-Za-z0-9_-]{16,1000}",
                       "gemini": r"AIza[A-Za-z0-9_-]{16,1000}"}[self.provider]
            if not re.fullmatch(pattern, key):
                raise ValueError("Invalid API key")
            self.api_key = SecretStr(key)
        return self


@router.get("")
def ai_settings_status():
    values = read_values()
    provider, key, model = connection_from(values)
    choices = []
    for id, config in PROVIDERS.items():
        _, saved_key, saved_model = connection_from(values, id)
        choices.append({"id": id, "name": config["name"], "configured": bool(saved_key),
                        "model": saved_model, "default_model": config["default_model"]})
    return {"configured": bool(key), "provider": provider, "provider_name": PROVIDERS[provider]["name"],
            "model": model, "saved_in_env": credential_path().is_file(), "providers": choices}


@router.put("")
def save_ai_settings(body: KeyInput):
    _, previous_key, previous_model = read_connection(body.provider)
    if not body.api_key and not previous_key:
        raise HTTPException(422, {"message": "Enter an API key for the selected provider before saving."})
    values = {"AI_PROVIDER": body.provider, body.provider.upper() + "_ENHANCEMENT_MODEL": body.model or previous_model}
    if body.api_key:
        values[PROVIDERS[body.provider]["key_env"]] = body.api_key.get_secret_value()
    persist_values(values)
    return ai_settings_status()


@router.post("/test")
def test_ai_connection():
    provider, key, model = read_connection()
    if not key: raise HTTPException(422, {"message": "Save an API key first."})
    try:
        with request_slot(active_user().id):
            request_text(provider, key, model, "Reply with OK.", timeout=25, max_tokens=2048)
        return {"connected": True, "message": f"Connected to {PROVIDERS[provider]['name']} using {model}.", "provider": provider, "model": model}
    except RuntimeError:
        raise HTTPException(429, {"message": "An AI request is already running. Try again when it finishes."}) from None
    except ProviderError as exc:
        raise HTTPException(exc.status, {"message": str(exc)}) from None
