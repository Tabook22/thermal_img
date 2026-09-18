"""Local display enhancement of user-selected insulator pixels; no reconstruction."""
from __future__ import annotations

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FocusPoint(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class InsulatorFocus(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    points: list[FocusPoint] = Field(min_length=3, max_length=256)
    adaptive: bool = False
    match_surroundings: bool = True
    clarity: float = Field(default=.65, ge=0, le=1)
    detail: float = Field(default=.5, ge=0, le=1)
    shadows: float = Field(default=.25, ge=0, le=1)
    background_dim: float = Field(default=0, ge=0, le=.8)

    @model_validator(mode="after")
    def nonempty_polygon(self):
        p = np.array([(v.x, v.y) for v in self.points], dtype=np.float32)
        if abs(cv2.contourArea(p)) < .00001:
            raise ValueError("Select a larger insulator area")
        # Concave freehand outlines are valid; crossing edges are not.
        def cross(a, b, c):
            return float((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))
        for i in range(len(p)):
            a, b = p[i], p[(i+1) % len(p)]
            for j in range(i+2, len(p)):
                if i == 0 and j == len(p)-1:
                    continue
                c, d = p[j], p[(j+1) % len(p)]
                if cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0:
                    raise ValueError("Trace an outline without crossing its edges")
        return self


def focus_mask(shape, focus: InsulatorFocus):
    height, width = shape[:2]
    points = np.rint([(p.x * (width - 1), p.y * (height - 1)) for p in focus.points]).astype(np.int32)
    mask = np.zeros((height, width), np.uint8)
    cv2.fillPoly(mask, [points], 1)
    return mask


def enhance_insulator(rgb: np.ndarray, focus: InsulatorFocus, valid=None):
    mask = focus_mask(rgb.shape, focus)
    if valid is not None:
        mask &= cv2.resize(valid.astype(np.uint8), (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError("The selected area has no valid image pixels")
    left, top, right, bottom = int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)
    # Local processing uses a margin so the selected border does not create edges.
    x0, y0, x1, y1 = max(0, left - 12), max(0, top - 12), min(rgb.shape[1], right + 12), min(rgb.shape[0], bottom + 12)
    crop = rgb[y0:y1, x0:x1]
    inside = mask[y0:y1, x0:x1].astype(bool)
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)
    light = lab[..., 0].astype(np.float32)
    samples = light[inside]
    low, high = np.percentile(samples, [2, 98])
    spread = float(high - low)
    warning = None
    if spread < 3:
        warning = "Very little visible contrast in this area. Enhancement cannot recover missing disc detail."
    elif min(right - left, bottom - top) < 8:
        warning = "This area contains very few pixels. Zoom enlarges the view but does not add captured detail."

    # Adaptive processing is display-only and estimates noise from selected pixels.
    detail_strength = focus.detail
    clarity_strength = focus.clarity
    working = light
    if focus.adaptive and spread >= 3:
        residual = light - cv2.GaussianBlur(light, (0, 0), .7)
        noise_estimate = float(np.median(np.abs(residual[inside] - np.median(residual[inside]))) * 1.4826)
        smoothed = cv2.bilateralFilter(light, 5, max(2., min(12., noise_estimate * 2)), 2.)
        working = light * .4 + smoothed * .6
        # Keep sharpening conservative when residual noise dominates contrast.
        reliability = float(np.clip(1 - noise_estimate / max(spread * .15, 1), .15, 1))
        detail_strength *= reliability
        clarity_strength *= .6 + .4 * reliability
        if reliability < .4:
            warning = "Limited clean detail: automatic sharpening has been reduced to avoid emphasizing noise."
    corrected = working.copy()
    if spread >= 3:
        # Modest local tone expansion, limited to avoid blowing out hot pixels.
        gain = min(2.2, max(1., 170 / spread))
        centered = (light - (low + high) / 2) * gain + (low + high) / 2
        corrected += np.clip(centered - light, -45, 45) * clarity_strength * .65
        tiles = (max(2, min(8, crop.shape[1] // 24)), max(2, min(8, crop.shape[0] // 24)))
        adaptive = cv2.createCLAHE(clipLimit=1.6, tileGridSize=tiles).apply(lab[..., 0]).astype(np.float32)
        corrected += np.clip(adaptive - light, -32, 32) * clarity_strength * .45
        # Lift dark captured detail while tapering the adjustment near highlights.
        luminance = light / 255
        corrected += focus.shadows * 55 * (1 - luminance) ** 2
        fine = working - cv2.GaussianBlur(working, (0, 0), .7)
        coarse = working - cv2.GaussianBlur(working, (0, 0), 1.7)
        noise = float(np.median(np.abs(fine[inside] - np.median(fine[inside]))) * 1.4826)
        threshold = max(.7, min(6., noise * .8))
        soften = lambda detail: np.sign(detail) * np.maximum(np.abs(detail) - threshold, 0)
        edge_detail = soften(fine) + .45 * soften(coarse)
        corrected += np.clip(edge_detail * detail_strength * 1.8, -16, 16)
    if focus.clarity == focus.detail == focus.shadows == 0 or spread < 3:
        enhanced = crop.copy()
    else:
        if focus.match_surroundings:
            # Remove broad exposure shifts that reveal the shape of the selection.
            # Retain only local detail changes, without transferring background colors.
            delta = corrected - light
            scale = max(2., min(8., min(right-left, bottom-top) * .08))
            delta -= cv2.GaussianBlur(delta, (0, 0), scale)
            delta = np.clip(delta, -12, 12)
            # Scaling all RGB channels together preserves the source hue/saturation.
            peak = crop.max(axis=2).astype(np.float32)
            target = np.clip(peak + delta, 0, 255)
            ratio = np.divide(target, peak, out=np.ones_like(peak), where=peak > 0)
            enhanced = np.rint(np.clip(crop.astype(np.float32) * ratio[..., None], 0, 255)).astype(np.uint8)
        else:
            lab[..., 0] = np.rint(np.clip(corrected, 0, 255)).astype(np.uint8)
            enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    # Feather inward only: with dimming off, every pixel outside the area is exact.
    padded = np.pad(mask, 1)
    distance = cv2.distanceTransform(padded, cv2.DIST_L2, 3)[1:-1, 1:-1]
    feather = max(1., min(6., min(right - left, bottom - top) * .05))
    if focus.match_surroundings:
        feather = max(3., min(20., min(right-left, bottom-top) * .18))
        weight = np.clip((distance - 1) / feather, 0, 1)
        weight = weight * weight * (3 - 2 * weight)
    else:
        weight = np.clip(distance / feather, 0, 1)
    weight = weight[y0:y1, x0:x1, None]
    output = rgb.copy()
    output[y0:y1, x0:x1] = np.rint(crop * (1 - weight) + enhanced * weight).astype(np.uint8)
    if focus.background_dim:
        output[mask == 0] = np.rint(rgb[mask == 0].astype(np.float32) * (1 - focus.background_dim)).astype(np.uint8)
    return output, {"warning": warning, "bounds": [left, top, right, bottom], "pixels": int(len(xs))}
