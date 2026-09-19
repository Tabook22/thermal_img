from __future__ import annotations

import base64
import io
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Literal
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, model_validator

from .enhancement import EnhancementSettings, render_enhancement
from .schemas import ImageDrawingInput, ImageNoteInput

PACKAGE_FORMAT = "tower-thermal-inspection-package"
PACKAGE_VERSION = 1


class ExportProbe(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    temperature_c: float


class MarkerVisibility(BaseModel):
    maximum: bool = True
    minimum: bool = True


class ExportDrawing(ImageDrawingInput):
    id: str = Field(max_length=64)


class ExportNote(ImageNoteInput):
    id: str = Field(max_length=64)


class ExportWorkspace(BaseModel):
    enhancement: EnhancementSettings = Field(default_factory=EnhancementSettings)
    probes: list[ExportProbe] = Field(default_factory=list, max_length=500)
    drawings: list[ExportDrawing] = Field(default_factory=list, max_length=500)
    notes: list[ExportNote] = Field(default_factory=list, max_length=500)
    temperature_visibility: MarkerVisibility = Field(default_factory=MarkerVisibility)
    range_mode: Literal["Auto", "Manual"] = "Auto"
    range_min: float = Field(-20, ge=-1000, le=1000)
    range_max: float = Field(150, ge=-1000, le=1000)

    @model_validator(mode="after")
    def valid_range(self):
        if not math.isfinite(self.range_min) or not math.isfinite(self.range_max) or self.range_min >= self.range_max:
            raise ValueError("Temperature range minimum must be below maximum")
        return self


def safe_stem(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(name).stem).strip("-")[:80] or "thermal-inspection"


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _label(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, fill: str, font) -> None:
    x, y = xy
    box = draw.textbbox((x, y), text, font=font, stroke_width=2)
    draw.rounded_rectangle((box[0] - 5, box[1] - 3, box[2] + 5, box[3] + 3), radius=4, fill=(8, 16, 21, 220))
    draw.text((x, y), text, font=font, fill=fill, stroke_width=1, stroke_fill="#071015")


def render_report_png(
    rgb: np.ndarray,
    matrix: np.ndarray | None,
    valid: np.ndarray | None,
    workspace: ExportWorkspace,
    regions: list[dict],
    analysis_stats: dict | None,
    official_luts: dict[str, np.ndarray] | None = None,
) -> bytes:
    rendered = render_enhancement(rgb, workspace.enhancement, matrix, valid, official_luts)
    encoded = rendered["preview"].split(",", 1)[-1]
    image = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    native_h, native_w = matrix.shape if matrix is not None else (height, width)
    sx, sy = width / native_w, height / native_h
    font = _font(max(12, round(width / 65)))
    small = _font(max(10, round(width / 80)))

    def pixel(point: dict) -> tuple[float, float]:
        return ((float(point["x"]) + .5) * sx, (float(point["y"]) + .5) * sy)

    def marker(point: dict | None, value: float | None, letter: str, color: str) -> None:
        if not point or value is None:
            return
        x, y = pixel(point)
        radius = max(8, width / 80)
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill="#0b151a", outline=color, width=max(2, round(width/320)))
        draw.text((x, y), letter, font=small, fill="white", anchor="mm")
        _label(draw, (x+radius+5, y-radius), f"{value:.1f}°C", color, small)

    for region in regions:
        points = region.get("points") or []
        if not points:
            continue
        coords = [pixel(p) for p in points]
        if region.get("kind") == "circle" and len(coords) >= 2:
            (cx, cy), (ex, ey) = coords[:2]
            radius = math.hypot(ex-cx, ey-cy)
            draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline="#ffd35a", width=max(2, round(width/320)))
        elif region.get("kind") == "rectangle" and len(coords) >= 2:
            (x1, y1), (x2, y2) = coords[:2]
            draw.rectangle((min(x1,x2), min(y1,y2), max(x1,x2), max(y1,y2)), outline="#ffd35a", width=max(2, round(width/320)))
        else:
            draw.line(coords + [coords[0]], fill="#ffd35a", width=max(2, round(width/320)), joint="curve")
        _label(draw, (coords[0][0], max(2, coords[0][1]-font.size-8)), region.get("name", "Area"), "#ffd35a", small)
        stat = region.get("statistics") or {}
        if workspace.temperature_visibility.maximum:
            marker(stat.get("maximum_location"), stat.get("maximum_c"), "H", "#ff7b2b")
        if workspace.temperature_visibility.minimum:
            chosen = region.get("minimum_selection") or stat.get("minimum_location")
            value = chosen.get("temperature_c") if isinstance(chosen, dict) and "temperature_c" in chosen else stat.get("minimum_c")
            marker(chosen, value, "L", "#35b9ff")

    if not regions and analysis_stats:
        if workspace.temperature_visibility.maximum:
            marker(analysis_stats.get("maximum_location"), analysis_stats.get("maximum_c"), "H", "#ff7b2b")
        if workspace.temperature_visibility.minimum:
            marker(analysis_stats.get("minimum_location"), analysis_stats.get("minimum_c"), "L", "#35b9ff")

    for probe in workspace.probes:
        marker({"x": probe.x, "y": probe.y}, probe.temperature_c, "+", "#ffffff")

    def normalized(point) -> tuple[float, float]:
        return (point.x * width, point.y * height)

    for item in workspace.drawings:
        pts = [normalized(p) for p in item.points]
        color, line_width = item.color, max(1, round(item.stroke_width * width / 800))
        if item.kind == "ellipse":
            draw.ellipse((pts[0][0], pts[0][1], pts[1][0], pts[1][1]), outline=color, width=line_width)
        else:
            line = pts
            if item.kind == "arrow" and item.control:
                a, c, b = pts[0], normalized(item.control), pts[1]
                line = [((1-t)**2*a[0]+2*(1-t)*t*c[0]+t*t*b[0], (1-t)**2*a[1]+2*(1-t)*t*c[1]+t*t*b[1]) for t in np.linspace(0,1,25)]
            draw.line(line, fill=color, width=line_width, joint="curve")
            if item.kind == "arrow":
                a, b = line[-2], line[-1]
                angle = math.atan2(b[1]-a[1], b[0]-a[0]); length=max(10,line_width*4)
                wings=[(b[0]-length*math.cos(angle-d),b[1]-length*math.sin(angle-d)) for d in (.55,-.55)]
                draw.polygon([b,*wings],fill=color)

    for note in workspace.notes:
        if not note.visible:
            continue
        x, y = note.x*width, note.y*height
        note_font = _font(max(9, round(note.font_size*width/800)))
        text = note.text[:500]
        box = draw.multiline_textbbox((x, y), text, font=note_font, spacing=3)
        background = note.background_color or {"yellow":"#f6d65b","blue":"#58b9e8","pink":"#e98aaa"}[note.color]
        draw.rounded_rectangle((box[0]-7,box[1]-5,box[2]+7,box[3]+5),radius=5,fill=background)
        draw.multiline_text((x,y),text,font=note_font,fill=note.text_color or "#111820",spacing=3)

    output = Image.alpha_composite(image, overlay).convert("RGB")
    buffer = io.BytesIO(); output.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def validate_archive(archive: ZipFile, max_uncompressed: int = 750 * 1024 * 1024) -> dict:
    entries = archive.infolist()
    if len(entries) > 50 or sum(item.file_size for item in entries) > max_uncompressed:
        raise ValueError("Inspection package is too large")
    names = {item.filename for item in entries}
    for item in entries:
        path = PurePosixPath(item.filename)
        if path.is_absolute() or ".." in path.parts or item.flag_bits & 1:
            raise ValueError("Inspection package contains an unsafe entry")
    if "manifest.json" not in names:
        raise ValueError("Inspection package has no manifest")
    raw = archive.read("manifest.json")
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Inspection package manifest is too large")
    manifest = json.loads(raw)
    if manifest.get("format") != PACKAGE_FORMAT or manifest.get("version") != PACKAGE_VERSION:
        raise ValueError("Unsupported inspection package format or version")
    for member in (manifest.get("files") or {}).values():
        if member and member not in names:
            raise ValueError(f"Inspection package is missing {member}")
    return manifest


def write_package(path: Path, manifest: dict, original: Path, report: bytes, matrix_path: Path | None) -> None:
    files = manifest["files"]
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(original, files["original"])
        archive.writestr(files["report"], report)
        if matrix_path is not None and files.get("matrix"):
            archive.write(matrix_path, files["matrix"])
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("README.txt", "This package preserves the untouched source image, calibrated temperature matrix, annotations, regions, and enhancement settings. Re-open the .thermalpkg file in Tower Thermal Inspector. report.png is a flattened visual for reports and is not a radiometric source file.\n")
