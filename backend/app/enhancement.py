"""Reversible display processing. Never write to source pixels or temperature arrays."""
from __future__ import annotations

import base64
from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .insulator_focus import InsulatorFocus, enhance_insulator


DJI_PALETTES = ("white_hot", "fulgurite", "iron_red", "hot_iron", "medical", "arctic",
                "rainbow1", "rainbow2", "tint", "black_hot")
PaletteName = Literal["original", "white_hot", "fulgurite", "iron_red", "hot_iron", "medical",
                      "arctic", "rainbow1", "rainbow2", "tint", "black_hot",
                      "iron", "inferno", "gray"]


class EnhancementSettings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    # Legacy iron/inferno/gray values remain readable for saved inspections.
    palette: PaletteName = "original"
    low: float | None = None
    high: float | None = None
    brightness: float = Field(default=0, ge=-50, le=50)
    contrast: float = Field(default=1, ge=.5, le=2)
    gamma: float = Field(default=1, ge=.4, le=2.5)
    saturation: float = Field(default=1, ge=0, le=2)
    local_contrast: float = Field(default=0, ge=0, le=1)
    denoise: float = Field(default=0, ge=0, le=1)
    sharpen: float = Field(default=0, ge=0, le=1)
    red: float = Field(default=1, ge=0, le=2)
    yellow: float = Field(default=1, ge=0, le=2)
    green: float = Field(default=1, ge=0, le=2)
    cyan: float = Field(default=1, ge=0, le=2)
    blue: float = Field(default=1, ge=0, le=2)
    purple: float = Field(default=1, ge=0, le=2)
    highlight: bool = False
    highlight_low: float | None = None
    highlight_high: float | None = None
    focus: InsulatorFocus | None = None

    @model_validator(mode="after")
    def ordered_ranges(self):
        for low, high in [(self.low, self.high), (self.highlight_low, self.highlight_high)]:
            if (low is None) != (high is None):
                raise ValueError("Enter both ends of the temperature range")
            if low is not None and high - low < .01:
                raise ValueError("The upper temperature must exceed the lower temperature by at least 0.01°C")
        if self.highlight and self.highlight_low is None:
            raise ValueError("Choose a temperature band to highlight")
        return self


PALETTE_STOPS: dict[str, list[tuple[int, int, int]]] = {
    # Low temperature to high temperature. Names and order follow dirp_pseudo_color_e.
    "white_hot": [(0, 0, 0), (255, 255, 255)],
    "black_hot": [(255, 255, 255), (0, 0, 0)],
    "fulgurite": [(24, 0, 8), (92, 0, 9), (198, 17, 5), (255, 112, 0), (255, 238, 18), (255, 255, 255)],
    "iron_red": [(0, 0, 14), (31, 4, 68), (105, 9, 104), (188, 25, 62), (246, 92, 19), (255, 210, 52), (255, 255, 226)],
    "hot_iron": [(0, 10, 10), (0, 55, 42), (0, 135, 92), (237, 218, 13), (244, 54, 7), (255, 255, 255)],
    "medical": [(4, 0, 35), (37, 0, 119), (0, 98, 255), (0, 224, 192), (104, 255, 0), (255, 233, 0), (255, 32, 20), (255, 0, 188), (255, 255, 255)],
    "arctic": [(0, 6, 40), (0, 47, 173), (0, 197, 255), (102, 255, 255), (255, 255, 255), (255, 231, 0), (255, 49, 0)],
    "rainbow1": [(0, 0, 40), (37, 0, 163), (0, 94, 255), (0, 218, 255), (0, 245, 80), (245, 255, 0), (255, 90, 0), (255, 0, 87), (255, 255, 255)],
    "rainbow2": [(0, 0, 255), (0, 190, 255), (0, 255, 48), (255, 255, 0), (255, 0, 0)],
    "tint": [(0, 0, 0), (100, 100, 100), (214, 214, 214), (255, 255, 255), (255, 210, 210), (255, 40, 23)],
}
LEGACY_PALETTES = {"gray": "white_hot", "iron": "iron_red", "inferno": "fulgurite"}


def palette_rgb(gray: np.ndarray, name: str, official_luts: dict[str, np.ndarray] | None = None) -> np.ndarray:
    name = LEGACY_PALETTES.get(name, name)
    if official_luts is not None and name in official_luts:
        lut = official_luts[name]
    else:
        stops = PALETTE_STOPS[name]
        positions = np.linspace(0, 1, len(stops))
        lut = np.stack([np.interp(np.linspace(0, 1, 256), positions, np.array(stops)[:, c]) for c in range(3)], axis=1).astype(np.uint8)
    return lut[gray]


def global_adjust(rgb: np.ndarray, s: EnhancementSettings) -> np.ndarray:
    values = np.clip((rgb.astype(np.float32) / 255 - .5) * s.contrast + .5 + s.brightness / 100, 0, 1)
    values = np.power(values, 1 / s.gamma)
    hsv = cv2.cvtColor(values.astype(np.float32), cv2.COLOR_RGB2HSV)
    hue = hsv[..., 0]
    # Smooth circular interpolation avoids visible seams between color bands.
    levels = [s.red, s.yellow, s.green, s.cyan, s.blue, s.purple, s.red]
    multiplier = np.interp(hue, np.arange(7) * 60, levels)
    hsv[..., 1] = np.clip(hsv[..., 1] * s.saturation * multiplier, 0, 1)
    return np.rint(np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0, 1) * 255).astype(np.uint8)


def render_enhancement(rgb: np.ndarray, s: EnhancementSettings, matrix=None, valid=None,
                       official_luts: dict[str, np.ndarray] | None = None) -> dict:
    has_matrix = matrix is not None and valid is not None
    mask = (valid & np.isfinite(matrix)) if has_matrix else None
    if has_matrix and not mask.any():
        raise ValueError("No valid temperature pixels are available")
    if (s.palette != "original" or s.highlight) and not has_matrix:
        raise ValueError("Temperature palettes and highlighting require a completed radiometric analysis")
    low = high = None
    result = rgb.copy()
    if s.palette != "original":
        low = s.low if s.low is not None else float(matrix[mask].min())
        high = s.high if s.high is not None else float(matrix[mask].max())
        high = max(high, low + .01)
        normalized = np.clip((np.where(mask, matrix, low) - low) / (high - low), 0, 1)
        result = palette_rgb(np.rint(normalized * 255).astype(np.uint8), s.palette, official_luts)
        result[~mask] = 0
        result = cv2.resize(result, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
    if s.denoise:
        result = cv2.bilateralFilter(result, 5, 5 + 35 * s.denoise, 2 + 3 * s.denoise)
    if s.local_contrast:
        lab = cv2.cvtColor(result, cv2.COLOR_RGB2LAB)
        enhanced = cv2.createCLAHE(clipLimit=2, tileGridSize=(8, 8)).apply(lab[..., 0])
        lab[..., 0] = cv2.addWeighted(lab[..., 0], 1 - s.local_contrast, enhanced, s.local_contrast, 0)
        result = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    if s.sharpen:
        result = cv2.addWeighted(result, 1 + s.sharpen, cv2.GaussianBlur(result, (0, 0), 1), -s.sharpen, 0)
    result = global_adjust(result, s)
    focus_info = None
    if s.focus is not None:
        result, focus_info = enhance_insulator(result, s.focus, mask)
    if s.highlight:
        band = mask & (matrix >= s.highlight_low) & (matrix <= s.highlight_high)
        band = cv2.resize(band.astype(np.uint8), (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)
        muted = cv2.cvtColor(cv2.cvtColor(result, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
        result[~band] = (muted[~band] * .35).astype(np.uint8)
    # Invalid thermal pixels remain visibly masked even after spatial processing.
    if s.palette != "original":
        display_mask = cv2.resize(mask.astype(np.uint8), (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)
        result[~display_mask] = 0
    ok, png = cv2.imencode(".png", cv2.cvtColor(result, cv2.COLOR_RGB2BGR))
    if not ok:
        raise ValueError("Could not render the enhanced image")
    legend = []
    if s.palette != "original":
        ramp = np.arange(256, dtype=np.uint8)[None, :]
        colors = global_adjust(palette_rgb(ramp, s.palette, official_luts), s)[0]
        legend = ["#%02x%02x%02x" % tuple(int(c) for c in colors[i]) for i in range(0, 256, 17)]
    return {"preview": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
            "low": low, "high": high, "legend": legend,
            "width": int(rgb.shape[1]), "height": int(rgb.shape[0]), "focus_info": focus_info,
            "quantitative_legend": not bool(s.local_contrast or s.denoise or s.sharpen or s.highlight or s.focus)}


def auto_settings(rgb: np.ndarray, matrix=None, valid=None) -> EnhancementSettings:
    options = dict(local_contrast=.2, denoise=.15, sharpen=.15)
    if matrix is not None and valid is not None:
        values = matrix[valid & np.isfinite(matrix)]
        if not values.size:
            raise ValueError("No valid temperature pixels are available")
        # Preserve rare hot pixels in the display span rather than clipping faults.
        low, high = float(np.percentile(values, .5)), float(values.max())
        return EnhancementSettings(palette="iron_red", low=float(low), high=float(max(high, low + .1)), **options)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    p5, p95 = np.percentile(gray, [5, 95])
    return EnhancementSettings(contrast=float(np.clip(180 / max(p95 - p5, 1), 1, 1.5)),
                               brightness=float(np.clip((127 - np.median(gray)) / 255 * 35, -15, 15)), **options)
