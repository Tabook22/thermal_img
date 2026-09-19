import numpy as np
import pytest
from app.thermal import DecodeError, hotspots, region_mask, statistics

def test_deterministic_stats_and_invalid_pixels():
    matrix=np.array([[5,1,1],[9,np.nan,9]],dtype=np.float32); valid=np.isfinite(matrix)
    result=statistics(matrix,valid)
    assert result["minimum_location"]=={"x":1,"y":0}; assert result["maximum_location"]=={"x":0,"y":1}; assert result["valid_pixels"]==5

def test_empty_region():
    with pytest.raises(DecodeError): statistics(np.ones((2,2)),np.zeros((2,2),bool))

def test_rectangle_and_hotspot_components():
    matrix=np.array([[0,0,0,0],[0,5,5,0],[0,5,0,9],[0,0,0,9]],dtype=np.float32); roi=region_mask(matrix.shape,"rectangle",[{"x":0,"y":0},{"x":3,"y":3}])
    result=hotspots(matrix,np.ones_like(roi),roi,4,2)
    assert [x["pixel_area"] for x in result]==[5]  # diagonal adjacency uses 8-connectivity
    assert result[0]["peak_c"]==9

def test_coordinate_mapping_formula():
    # Viewer CSS point -> native pixel, independent of display scale.
    native_w,native_h,shown_w,shown_h=640,512,1280,1024
    assert (int(870/shown_w*native_w),int(680/shown_h*native_h))==(435,340)

def test_circle_region_mask():
    mask=region_mask((20,20),"circle",[{"x":10,"y":10},{"x":15,"y":10}])
    assert mask[10,10] and mask[10,15] and not mask[0,0]


def test_line_region_samples_each_calibrated_pixel_on_the_path():
    mask = region_mask((8, 8), "line", [{"x": 1, "y": 1}, {"x": 6, "y": 6}])
    assert mask.sum() == 6
    assert all(mask[i, i] for i in range(1, 7))
    assert not mask[1, 2]
