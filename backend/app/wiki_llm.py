"""Local Ollama adapter for document-to-wiki synthesis."""
from __future__ import annotations

import json
import os

import httpx


class LocalModelUnavailable(RuntimeError):
    pass


def generate_json(system: str, user: str) -> dict:
    base = os.getenv("WIKI_OLLAMA_URL") or os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434"
    model = os.getenv("WIKI_OLLAMA_MODEL", "qwen3:4b")
    try:
        response = httpx.post(base.rstrip("/") + "/api/chat", json={
            "model": model, "stream": False, "format": "json", "think": False,
            "options": {"temperature": 0.1, "num_predict": 1600},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }, timeout=180)
        response.raise_for_status()
        content = response.json()["message"]["content"]
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("Model did not return a JSON object")
        return result
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise LocalModelUnavailable(f"Local model {model} is unavailable or returned an invalid response: {exc}") from exc
