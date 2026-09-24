import io

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from app.inspection_package import ExportWorkspace, render_report_png


def test_crop_matches_annotated_report_slice_without_changing_source_data():
    rgb = np.arange(80 * 100 * 3, dtype=np.uint8).reshape(80, 100, 3)
    matrix = np.linspace(20, 50, 8000).reshape(80, 100)
    original_rgb, original_matrix = rgb.copy(), matrix.copy()
    valid = np.ones_like(matrix, dtype=bool)
    workspace = ExportWorkspace(notes=[{"id":"note", "text":"Hotspot", "x":.3, "y":.3}],
                                probes=[{"x":40,"y":30,"temperature_c":32}])
    full = Image.open(io.BytesIO(render_report_png(rgb,matrix,valid,workspace,[],None)))
    cropped_workspace = ExportWorkspace.model_validate({**workspace.model_dump(),"crop":{"x":.2,"y":.25,"width":.5,"height":.5}})
    cropped = Image.open(io.BytesIO(render_report_png(rgb,matrix,valid,cropped_workspace,[],None)))
    assert cropped.size == (50,40)
    np.testing.assert_array_equal(np.asarray(cropped),np.asarray(full.crop((20,20,70,60))))
    np.testing.assert_array_equal(rgb,original_rgb)
    np.testing.assert_array_equal(matrix,original_matrix)


@pytest.mark.parametrize('crop',[
    {"x":-.1,"y":0,"width":.5,"height":.5},
    {"x":.9,"y":0,"width":.5,"height":.5},
    {"x":0,"y":.9,"width":.5,"height":.5},
    {"x":0,"y":0,"width":0,"height":.5},
    {"x":float('nan'),"y":0,"width":.5,"height":.5},
])
def test_rejects_invalid_crop(crop):
    with pytest.raises(ValidationError):
        ExportWorkspace(crop=crop)


def test_tiny_edge_crop_keeps_at_least_one_pixel():
    crop={"x":.999,"y":.999,"width":.001,"height":.001}
    png=render_report_png(np.zeros((10,10,3),dtype=np.uint8),None,None,ExportWorkspace(crop=crop),[],None)
    assert Image.open(io.BytesIO(png)).size==(1,1)
