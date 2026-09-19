from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from pydantic import BaseModel, Field

_lock = threading.Lock()


class BrandingSettings(BaseModel):
    application_title: str = Field("Tower Thermal", min_length=1, max_length=80)
    application_subtitle: str = Field("Inspector", min_length=1, max_length=50)
    application_version: str = Field("1.0", min_length=1, max_length=30)
    company_name: str = Field("Sky Green Line", min_length=1, max_length=100)
    department: str = Field("Technical Department", min_length=1, max_length=100)
    copyright_text: str = Field("© 2026 Sky Green Line. All rights reserved.", min_length=1, max_length=240)


def _root(storage_root: Path) -> Path:
    path = storage_root / "branding"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_branding(storage_root: Path) -> BrandingSettings:
    path = _root(storage_root) / "settings.json"
    if not path.is_file():
        return BrandingSettings()
    try:
        return BrandingSettings.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError):
        return BrandingSettings()


def save_branding(storage_root: Path, value: BrandingSettings) -> BrandingSettings:
    root = _root(storage_root)
    path, temporary = root / "settings.json", root / "settings.tmp"
    with _lock:
        temporary.write_text(json.dumps(value.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    return value


def logo_path(storage_root: Path, kind: str) -> Path:
    if kind not in {"company", "application"}:
        raise ValueError("Logo kind must be company or application")
    return _root(storage_root) / f"{kind}-logo.png"


def store_logo(storage_root: Path, kind: str, uploaded: Path) -> Path:
    target = logo_path(storage_root, kind)
    temporary = target.with_suffix(".tmp.png")
    try:
        with Image.open(uploaded) as source:
            source.verify()
        with Image.open(uploaded) as source:
            if source.width < 16 or source.height < 16 or source.width > 5000 or source.height > 5000:
                raise ValueError("Logo dimensions must be between 16 and 5000 pixels")
            image = source.convert("RGBA")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            image.save(temporary, "PNG", optimize=True)
        temporary.replace(target)
        return target
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Logo is not a readable PNG or JPEG image") from exc
    finally:
        temporary.unlink(missing_ok=True)


def public_branding(storage_root: Path) -> dict:
    value = load_branding(storage_root).model_dump()
    revision = int(datetime.now(timezone.utc).timestamp())
    for kind in ("company", "application"):
        path = logo_path(storage_root, kind)
        value[f"{kind}_logo_url"] = f"/api/settings/assets/{kind}-logo?v={path.stat().st_mtime_ns}" if path.is_file() else None
    value["revision"] = revision
    return value
