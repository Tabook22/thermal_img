import io
import math
import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError
from app.inspection_package import ExportWorkspace, MaximumRing, render_report_png


def test_ring_keeps_maximum_inside_and_rejects_invalid_input():
    ring=MaximumRing(dx=.2,dy=.2,radius=.05)
    assert math.hypot(ring.dx,ring.dy)==pytest.approx(.05*.85)
    with pytest.raises(ValidationError): MaximumRing(radius=float('nan'))
    with pytest.raises(ValidationError): ExportWorkspace(maximum_rings={'unexpected':{}})


def test_report_ring_is_hollow_and_does_not_change_measurements():
    rgb=np.full((256,256,3),80,dtype=np.uint8)
    matrix=np.full((256,256),27.4,dtype=np.float32)
    valid=np.ones_like(matrix,dtype=bool)
    stats={'maximum_location':{'x':100,'y':100},'maximum_c':27.4}
    workspace=ExportWorkspace(maximum_rings={'full':{'dx':.03,'dy':0,'radius':.16}},temperature_visibility={'maximum':True,'minimum':False})
    result=np.asarray(Image.open(io.BytesIO(render_report_png(rgb,matrix,valid,workspace,[],stats))))
    baseline=np.asarray(Image.open(io.BytesIO(render_report_png(rgb,matrix,valid,ExportWorkspace(temperature_visibility={'maximum':False,'minimum':False}),[],stats))))
    np.testing.assert_array_equal(result[110,110],baseline[110,110])
    assert np.any(np.all(result[:,:,:3]==[255,80,60],axis=2))
    np.testing.assert_array_equal(matrix,np.full((256,256),27.4,dtype=np.float32))
    assert stats=={'maximum_location':{'x':100,'y':100},'maximum_c':27.4}
