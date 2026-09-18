import hashlib

import cv2
import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.enhancement import EnhancementSettings, render_enhancement
from app.insulator_focus import InsulatorFocus, enhance_insulator, focus_mask
from app.main import EnhancementRequest, enhancement_preview, get_enhancement, save_enhancement, settings
from app.models import AnalysisVersion, Base, ThermalImage
from app.thermal import statistics


def focus(**kwargs):
    return InsulatorFocus(points=[{"x": .3, "y": .1}, {"x": .7, "y": .1},
                                 {"x": .7, "y": .9}, {"x": .3, "y": .9}], **kwargs)


def faint_insulator():
    light = np.full((160, 120), 32, np.uint8)
    cv2.rectangle(light, (56, 10), (64, 150), 40, -1)
    for y in range(20, 150, 12):
        cv2.ellipse(light, (60, y), (19, 3), 0, 0, 360, 48, -1)
    light = cv2.GaussianBlur(light, (0, 0), .8)
    return cv2.cvtColor(light, cv2.COLOR_GRAY2RGB)


def test_focus_enhances_captured_disc_edges_and_preserves_every_outside_pixel():
    rgb = faint_insulator()
    original = rgb.copy()
    selected = focus()
    output, info = enhance_insulator(rgb, selected)
    mask = focus_mask(rgb.shape, selected).astype(bool)
    assert np.array_equal(output[~mask], rgb[~mask])
    assert np.array_equal(rgb, original)
    before_edges = np.abs(np.diff(rgb[:, 50:71, 0].astype(float), axis=0)).mean()
    after_edges = np.abs(np.diff(output[:, 50:71, 0].astype(float), axis=0)).mean()
    assert after_edges > before_edges * 1.1
    assert info["pixels"] == int(mask.sum())
    assert output.shape == rgb.shape


def test_rotated_selection_leaves_background_and_invalid_pixels_untouched():
    rgb = faint_insulator()
    selected = InsulatorFocus(points=[{"x": .2, "y": .15}, {"x": .4, "y": .05},
                                      {"x": .85, "y": .8}, {"x": .65, "y": .9}])
    valid = np.ones(rgb.shape[:2], bool)
    valid[65:75, 50:60] = False
    output, _ = enhance_insulator(rgb, selected, valid)
    mask = focus_mask(rgb.shape, selected).astype(bool) & valid
    assert np.array_equal(rgb[~mask], output[~mask])


def test_uniform_area_does_not_invent_disc_patterns():
    rgb = np.full((100, 100, 3), 34, np.uint8)
    output, info = enhance_insulator(rgb, focus(clarity=1, detail=1, shadows=1))
    assert np.array_equal(rgb, output)
    assert "cannot recover" in info["warning"]


def test_zero_strengths_are_exact_and_background_dimming_is_opt_in():
    rgb = faint_insulator()
    selected = focus(clarity=0, detail=0, shadows=0)
    output, _ = enhance_insulator(rgb, selected)
    assert np.array_equal(output, rgb)
    selected.background_dim = .5
    output, _ = enhance_insulator(rgb, selected)
    mask = focus_mask(rgb.shape, selected).astype(bool)
    assert np.array_equal(output[mask], rgb[mask])
    assert np.all(output[~mask] <= rgb[~mask])


def test_invalid_geometry_and_nan_are_rejected():
    for points in [[{"x": 0, "y": 0}] * 3,
                   [{"x": 0, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}, {"x": 1, "y": 0}],
                   [{"x": float("nan"), "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}]]:
        with pytest.raises(ValidationError):
            InsulatorFocus(points=points)


def test_rendering_and_saving_focus_preserve_original_file_metadata_and_matrix(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    rgb = faint_insulator()
    exif = Image.Exif()
    exif[306] = "2026:09:17 02:15:55"
    Image.fromarray(rgb).save(tmp_path / "original.jpg", exif=exif)
    Image.fromarray(rgb).save(tmp_path / "preview.png")
    matrix = np.linspace(20, 40, 160 * 120, dtype=np.float32).reshape(160, 120)
    valid = np.ones(matrix.shape, bool)
    np.savez(tmp_path / "matrix.npz", temperatures=matrix, valid_mask=valid)
    digest = lambda name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    before = {name: digest(name) for name in ["original.jpg", "preview.png", "matrix.npz"]}
    measurements = statistics(matrix, valid)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ThermalImage(id=1, inspection_id=1, original_name="original.jpg", storage_name="original.jpg",
                            sha256=before["original.jpg"], classification="supported_radiometric",
                            metadata_json={"preview_path": "preview.png", "capture_metadata": {"date": "2026-09-17"}}))
        db.add(AnalysisVersion(id=1, image_id=1, version=1, status="completed", matrix_path="matrix.npz",
                               width=120, height=160, stats_json=measurements))
        db.commit()
        options = EnhancementSettings(focus=focus())
        result = enhancement_preview(1, EnhancementRequest(settings=options, analysis_id=1), db)
        assert result["focus_info"]["pixels"] > 0
        assert not result["quantitative_legend"]
        save_enhancement(1, options, db)
        assert get_enhancement(1, db).focus == options.focus
        assert db.get(ThermalImage, 1).metadata_json["capture_metadata"] == {"date": "2026-09-17"}
        assert db.get(AnalysisVersion, 1).stats_json == measurements
    assert {name: digest(name) for name in before} == before
    with np.load(tmp_path / "matrix.npz") as data:
        assert np.array_equal(data["temperatures"], matrix)
        assert np.array_equal(data["valid_mask"], valid)


def test_concave_freehand_focus_preserves_unselected_pixels():
    from app.insulator_focus import InsulatorFocus, enhance_insulator, focus_mask
    rgb = np.tile(np.arange(120, dtype=np.uint8), (100, 1))
    rgb = np.repeat(rgb[:, :, None], 3, axis=2)
    focus = InsulatorFocus(points=[{"x":.2,"y":.1},{"x":.8,"y":.1},{"x":.5,"y":.5},{"x":.8,"y":.9},{"x":.2,"y":.9}])
    before = rgb.copy()
    result, _ = enhance_insulator(rgb, focus)
    mask = focus_mask(rgb.shape, focus)
    assert np.array_equal(result[mask == 0], before[mask == 0])
    assert np.array_equal(rgb, before)


def test_adaptive_focus_is_deterministic_and_preserves_source_and_background():
    rgb = faint_insulator()
    before = rgb.copy()
    selection = focus(adaptive=True)
    first, _ = enhance_insulator(rgb, selection)
    second, _ = enhance_insulator(rgb, selection)
    mask = focus_mask(rgb.shape, selection)
    assert np.array_equal(first, second)
    assert np.array_equal(rgb, before)
    assert np.array_equal(first[mask == 0], before[mask == 0])
    assert np.any(first[mask == 1] != before[mask == 1])


def test_color_matching_reduces_broad_shift_and_preserves_hue():
    y, x = np.mgrid[:120, :100]
    value = (60 + y * .4 + 8 * np.sin(y / 3)).astype(np.uint8)
    rgb = np.stack([value, value // 4, value * 2], axis=2)
    matched, _ = enhance_insulator(rgb, focus(match_surroundings=True))
    unmatched, _ = enhance_insulator(rgb, focus(match_surroundings=False))
    mask = focus_mask(rgb.shape, focus()).astype(bool)
    assert np.array_equal(matched[~mask], rgb[~mask])
    original_hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(float)
    matched_hsv = cv2.cvtColor(matched, cv2.COLOR_RGB2HSV).astype(float)
    assert np.max(np.abs(original_hsv[..., 0] - matched_hsv[..., 0])) <= 1
    before = rgb.astype(float)
    assert abs(np.mean(matched[mask] - before[mask])) < abs(np.mean(unmatched[mask] - before[mask]))
