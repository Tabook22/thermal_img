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


class GuideOverlay(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    x: float = Field(0.62, ge=0, le=1)
    y: float = Field(0.08, ge=0, le=1)
    width: float = Field(0.3, ge=0.08, le=0.8)
    height: float = Field(0.3, ge=0.08, le=0.8)
    zoom: float = Field(1, ge=1, le=5)


class ExportDrawing(ImageDrawingInput):
    id: str = Field(max_length=64)


class ExportNote(ImageNoteInput):
    id: str = Field(max_length=64)


class ImageCrop(BaseModel):
    x: float = Field(ge=0, lt=1, allow_inf_nan=False)
    y: float = Field(ge=0, lt=1, allow_inf_nan=False)
    width: float = Field(gt=0, le=1, allow_inf_nan=False)
    height: float = Field(gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def within_image(self):
        if self.x + self.width > 1 + 1e-9 or self.y + self.height > 1 + 1e-9:
            raise ValueError("Crop must stay inside the original image")
        return self


class ExportWorkspace(BaseModel):
    crop: ImageCrop | None = None
    enhancement: EnhancementSettings = Field(default_factory=EnhancementSettings)
    insulator_label: Literal["inner", "outer"] | None = None
    insulator_label_x: float = Field(0.81, ge=0, le=1)
    insulator_label_y: float = Field(0.025, ge=0, le=1)
    insulator_label_width: float = Field(0.17, ge=0.06, le=0.55)
    guide_overlay: dict | None = None
    guide_overlays: list[GuideOverlay] = Field(default_factory=list, max_length=20)
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
    guide_images: dict[str, Image.Image] | None = None,
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

    for placement in workspace.guide_overlays:
        source = (guide_images or {}).get(placement.id)
        if source is None:
            continue
        box_width=max(24,round(width*placement.width));box_height=max(20,round(height*placement.height))
        left=min(width-box_width,round(width*placement.x));top=min(height-box_height,round(height*placement.y))
        guide=source.convert("RGBA");fit=min(box_width/max(1,guide.width),box_height/max(1,guide.height))*placement.zoom
        scaled=(max(1,round(guide.width*fit)),max(1,round(guide.height*fit)));guide=guide.resize(scaled,Image.Resampling.LANCZOS)
        viewport=Image.new("RGBA",(box_width,box_height),(0,0,0,0));viewport.alpha_composite(guide,((box_width-guide.width)//2,(box_height-guide.height)//2))
        overlay.alpha_composite(viewport,(left,top));draw.rectangle((left,top,left+box_width,top+box_height),outline="white",width=max(1,round(width/500)))

    if workspace.insulator_label:
        label = workspace.insulator_label.title()
        badge_width = min(width, max(34, round(width * workspace.insulator_label_width)))
        badge_height = min(height, max(16, round(badge_width / 2.2)))
        badge_font = _font(max(7, round(badge_width * .18)))
        left = min(width - badge_width, round(width * workspace.insulator_label_x))
        top = min(height - badge_height, round(height * workspace.insulator_label_y))
        right, bottom = left + badge_width, top + badge_height
        pad = max(2, round(badge_width * .05)); icon_width = max(6, round(badge_width * .13))
        border = max(1, round(badge_width / 100)); inset = max(3, round(badge_height * .14))
        draw.rounded_rectangle((left, top, right, bottom), radius=max(2, round(badge_width / 32)), fill=(8, 16, 24, 210), outline="white", width=border)
        cx = left + pad + icon_width / 2
        draw.line((cx, top + inset, cx, bottom - inset), fill="#e8eef0", width=border)
        disc_width = icon_width * .78
        for index in range(7):
            cy = top + inset + index * (badge_height - inset * 2) / 6
            thickness = max(1, badge_height / 35)
            draw.ellipse((cx-disc_width/2, cy-thickness, cx+disc_width/2, cy+thickness), fill="#cbd4d8", outline="#ffffff")
        draw.text((left + pad * 2 + icon_width, (top + bottom) / 2), label, font=badge_font, fill="white", anchor="lm")

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
        if region.get("kind") == "line" and len(coords) >= 2:
            draw.line(coords[:2], fill="#f5e65a", width=max(2, round(width/420)))
            midpoint=((coords[0][0]+coords[1][0])/2,(coords[0][1]+coords[1][1])/2)
            mean=(region.get("statistics") or {}).get("mean_c")
            if mean is not None: _label(draw,(midpoint[0]+7,midpoint[1]+7),f"{region.get('name','Line')} AVG {mean:.1f}°C","#f5e65a",small)
        elif region.get("kind") == "circle" and len(coords) >= 2:
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
    if workspace.crop:
        crop = workspace.crop
        left, top = math.floor(crop.x * width), math.floor(crop.y * height)
        right = min(width, max(left + 1, math.ceil((crop.x + crop.width) * width)))
        bottom = min(height, max(top + 1, math.ceil((crop.y + crop.height) * height)))
        output = output.crop((left, top, right, bottom))
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
    members: list[str] = []
    for value in (manifest.get("files") or {}).values():
        if isinstance(value, str):
            members.append(value)
        elif isinstance(value, dict):
            members.extend(member for member in value.values() if isinstance(member, str))
    for member in members:
        if member not in names:
            raise ValueError(f"Inspection package is missing {member}")
    return manifest


def write_package(
    path: Path,
    manifest: dict,
    original: Path,
    report: bytes,
    matrix_path: Path | None,
    guide_paths: dict[str, Path] | None = None,
) -> None:
    files = manifest["files"]
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(original, files["original"])
        archive.writestr(files["report"], report)
        if matrix_path is not None and files.get("matrix"):
            archive.write(matrix_path, files["matrix"])
        for guide_id, guide_path in (guide_paths or {}).items():
            member = (files.get("guides") or {}).get(guide_id)
            if member:
                archive.write(guide_path, member)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("README.txt", "This package preserves the untouched source image, calibrated temperature matrix, annotations, regions, and enhancement settings. Re-open the .thermalpkg file in Tower Thermal Inspector. report.png is a flattened visual for reports and is not a radiometric source file.\n")
