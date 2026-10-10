"""Small provider adapters. Fixed origins; credentials are sent only in headers."""
import re
from typing import Literal

import httpx

Provider = Literal["openai", "anthropic", "gemini"]
PROVIDERS = {
    "openai": {"name": "OpenAI", "default_model": "gpt-4.1", "key_env": "OPENAI_API_KEY"},
    "anthropic": {"name": "Anthropic (Claude)", "default_model": "claude-sonnet-5-5", "key_env": "ANTHROPIC_API_KEY"},
    "gemini": {"name": "Google (Gemini)", "default_model": "gemini-3.8-flash", "key_env": "GEMINI_API_KEY"},
}


def valid_model(model):
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", model)) and not model.startswith(("sk-", "AIza"))


class ProviderError(ValueError):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def provider_schema(value, provider):
    """Anthropic omits unsupported constraints; Pydantic enforces them on return."""
    if isinstance(value, list):
        return [provider_schema(item, provider) for item in value]
    if not isinstance(value, dict):
        return value
    unsupported = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "minItems", "maxItems"} if provider == "anthropic" else set()
    result = {key: provider_schema(item, provider) for key, item in value.items() if key not in unsupported}
    limits = {key: item for key, item in value.items() if key in unsupported}
    if limits:
        result["description"] = (result.get("description", "") + f" Constraints: {limits}").strip()
    return result


def request_text(provider, key, model, prompt, *, instructions="", image=None, schema=None, timeout=70, max_tokens=5000):
    if provider not in PROVIDERS or not valid_model(model):
        raise ProviderError("Choose a valid AI provider and model in Settings.", 422)
    name = PROVIDERS[provider]["name"]
    if provider == "openai":
        url = "https://api.openai.com/v1/responses"
        headers = {"Authorization": f"Bearer {key}"}
        content = [{"type": "input_text", "text": prompt}]
        if image:
            content.append({"type": "input_image", "image_url": "data:image/jpeg;base64," + image, "detail": "high"})
        body = {"model": model, "store": False, "max_output_tokens": max_tokens,
                "instructions": instructions, "input": [{"role": "user", "content": content}]}
        if schema:
            body["text"] = {"format": {"type": "json_schema", "name": "thermal_display_proposal", "strict": True, "schema": schema}}
    elif provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        content = []
        if image:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image}})
        content.append({"type": "text", "text": prompt})
        body = {"model": model, "max_tokens": max_tokens, "system": instructions,
                "messages": [{"role": "user", "content": content}]}
        if schema:
            body["output_config"] = {"format": {"type": "json_schema", "schema": provider_schema(schema, provider)}}
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"x-goog-api-key": key}
        parts = [{"text": prompt}]
        if image:
            parts.insert(0, {"inlineData": {"mimeType": "image/jpeg", "data": image}})
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"maxOutputTokens": max_tokens}}
        if instructions:
            body["systemInstruction"] = {"parts": [{"text": instructions}]}
        if schema:
            body["generationConfig"]["responseFormat"] = {"text": {"mimeType": "application/json", "schema": schema}}
    try:
        response = httpx.post(url, headers=headers, json=body, timeout=timeout, follow_redirects=False)
        if response.status_code in (401, 403):
            raise ProviderError(f"{name} rejected the key or model access. Check the key and project permissions in Settings.", 422)
        if response.status_code == 429:
            raise ProviderError(f"{name} reports a usage or rate limit. Check API billing and limits, then try again.", 422)
        if response.status_code in (400, 404):
            raise ProviderError(f"{name} rejected the request. Check that the model ID supports images and structured output, and that the key belongs to this provider.", 422)
        if response.status_code != 200:
            raise ProviderError(f"{name} could not complete the request. Try again later.")
        payload = response.json()
        if provider == "openai":
            complete = payload.get("status") == "completed"
            text = "".join(part.get("text", "") for item in payload.get("output", []) if item.get("type") == "message"
                           for part in item.get("content", []) if part.get("type") == "output_text")
        elif provider == "anthropic":
            complete = payload.get("stop_reason") == "end_turn"
            text = "".join(part.get("text", "") for part in payload.get("content", []) if part.get("type") == "text")
        else:
            candidate = (payload.get("candidates") or [{}])[0]
            complete = candidate.get("finishReason") == "STOP"
            text = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", []) if not part.get("thought"))
        if not complete or not text.strip():
            raise ProviderError(f"{name} did not complete a response. Try a shorter request or another supported model.")
        return text
    except httpx.TimeoutException:
        raise ProviderError(f"{name} took too long. Your image and saved settings are unchanged; try again.") from None
    except httpx.HTTPError:
        raise ProviderError(f"Unable to reach {name}. Your image and saved settings are unchanged.") from None
    except (TypeError, AttributeError, KeyError, ValueError) as exc:
        if isinstance(exc, ProviderError):
            raise
        raise ProviderError(f"{name} returned an unreadable response. Try again later.") from None
