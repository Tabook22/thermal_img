import base64

import cv2
import numpy as np
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.enhancement import EnhancementSettings, auto_settings, render_enhancement
from app.main import get_enhancement, save_enhancement
from app.models import Base, ThermalImage
from app.thermal import statistics


def decode(result):
    png = base64.b64decode(result["preview"].split(",", 1)[1])
    return cv2.cvtColor(cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def test_default_render_is_pixel_identical_and_does_not_modify_input():
    rgb = np.random.default_rng(7).integers(0, 256, (32, 40, 3), dtype=np.uint8)
    original = rgb.copy()
    assert np.array_equal(decode(render_enhancement(rgb, EnhancementSettings())), original)
    assert np.array_equal(rgb, original)


@pytest.mark.parametrize("palette", ["iron", "inferno", "arctic", "gray"])
def test_all_enhancements_preserve_temperature_values_and_coordinates(palette):
    matrix = np.linspace(20, 60, 1280, dtype=np.float32).reshape(32, 40)
    matrix[0, 0] = np.nan
    valid = np.isfinite(matrix)
    before = statistics(matrix, valid)
    original = matrix.copy()
    matrix.setflags(write=False)
    valid.setflags(write=False)
    rgb = np.zeros((64, 80, 3), dtype=np.uint8)
    settings = EnhancementSettings(palette=palette, low=25, high=45, local_contrast=.4,
                                   sharpen=.5, denoise=.3, blue=0, red=2, highlight=True,
                                   highlight_low=35, highlight_high=55)
    result = render_enhancement(rgb, settings, matrix, valid)
    output = decode(result)
    assert output.shape == rgb.shape
    assert np.array_equal(output[0, 0], [0, 0, 0])
    assert np.array_equal(matrix, original, equal_nan=True)
    assert statistics(matrix, valid) == before
    assert result["low"] == 25 and result["high"] == 45
    assert not result["quantitative_legend"]


def test_linear_temperature_palette_has_correct_legend_endpoints():
    matrix = np.array([[20, 30, 40]], dtype=np.float32)
    result = render_enhancement(np.zeros((1, 3, 3), np.uint8),
                                EnhancementSettings(palette="gray", low=20, high=40),
                                matrix, np.ones_like(matrix, dtype=bool))
    assert result["quantitative_legend"]
    assert result["legend"][0] == "#000000" and result["legend"][-1] == "#ffffff"
    assert np.array_equal(decode(result)[0, :, 0], [0, 128, 255])


def test_selective_desaturation_removes_blue_but_preserves_red():
    rgb = np.array([[[0, 0, 255], [255, 0, 0]]], dtype=np.uint8)
    result = decode(render_enhancement(rgb, EnhancementSettings(blue=0)))
    assert result[0, 0, 0] == result[0, 0, 1] == result[0, 0, 2]
    assert np.array_equal(result[0, 1], rgb[0, 1])


def test_highlight_dims_only_pixels_outside_band():
    rgb = np.full((1, 2, 3), 200, dtype=np.uint8)
    matrix = np.array([[25, 50]], dtype=np.float32)
    options = EnhancementSettings(highlight=True, highlight_low=40, highlight_high=60)
    result = decode(render_enhancement(rgb, options, matrix, np.ones_like(matrix, dtype=bool)))
    assert np.array_equal(result[0, 1], rgb[0, 1])
    assert result[0, 0].max() < 100


def test_invalid_ranges_and_missing_matrix_fail_clearly():
    for options in [{"low": 40, "high": 20}, {"low": 20}, {"highlight": True}, {"brightness": float("nan")}]:
        with pytest.raises(ValidationError):
            EnhancementSettings(**options)
    with pytest.raises(ValueError, match="radiometric"):
        render_enhancement(np.zeros((10, 10, 3), np.uint8), EnhancementSettings(palette="iron"))


def test_auto_handles_flat_matrix_without_dividing_by_zero():
    rgb = np.full((32, 40, 3), 80, dtype=np.uint8)
    matrix = np.full((32, 40), 27., dtype=np.float32)
    valid = np.ones_like(matrix, dtype=bool)
    automatic = auto_settings(rgb, matrix, valid)
    assert automatic.high > automatic.low
    assert decode(render_enhancement(rgb, automatic, matrix, valid)).shape == rgb.shape
    assert auto_settings(rgb).palette == "original"


def test_auto_preserves_rare_hotspot_in_display_range():
    rgb = np.zeros((32, 40, 3), dtype=np.uint8)
    matrix = np.full((32, 40), 25., dtype=np.float32)
    matrix[10, 20] = 85.
    automatic = auto_settings(rgb, matrix, np.ones_like(matrix, dtype=bool))
    assert automatic.high == 85.


def test_settings_are_saved_per_image_without_changing_notes():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for image_id in [1, 2]:
            db.add(ThermalImage(id=image_id, inspection_id=1, original_name="thermal.JPG",
                                storage_name=f"originals/{image_id}.JPG", sha256="a" * 64,
                                classification="ordinary_image", metadata_json={"notes": [{"id": "keep"}]}))
        db.commit()
        options = EnhancementSettings(contrast=1.4, purple=.2)
        save_enhancement(1, options, db)
        assert get_enhancement(1, db) == options
        assert get_enhancement(2, db) == EnhancementSettings()
        assert db.get(ThermalImage, 1).metadata_json["notes"] == [{"id": "keep"}]
