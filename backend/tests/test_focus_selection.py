import base64
import hashlib
import io
from zipfile import ZipFile

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from app.enhancement import EnhancementSettings, render_enhancement
from app.insulator_focus import InsulatorFocus, focus_mask
from app.models import AnalysisVersion, ThermalImage
from test_private_workspaces import workspace

POINTS=[{'x':.3,'y':.1},{'x':.7,'y':.1},{'x':.7,'y':.9},{'x':.3,'y':.9}]

def pixels(render):
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(render['preview'].split(',')[1]))))

def test_brush_holes_and_added_fittings_control_measurements_without_changing_source():
    rgb=np.full((200,200,3),[210,70,160],np.uint8)
    matrix=np.full((100,100),25,np.float32);matrix[50,50]=60;matrix[50,20]=42;matrix[2,2]=99
    before=matrix.copy()
    selection=InsulatorFocus(points=POINTS,preserve_original=True,background_mode='blue',background_dim=1,
        strokes=[{'points':[{'x':.5,'y':.5}],'radius':.04,'erase':True},
                 {'points':[{'x':.2,'y':.5},{'x':.31,'y':.5}],'radius':.02,'erase':False}])
    options=EnhancementSettings(focus=selection,brightness=40,contrast=1.7,
                               concealed_areas=[InsulatorFocus(points=POINTS,background_mode='blue')])
    result=render_enhancement(rgb,options,matrix,np.ones_like(matrix,bool));output=pixels(result)
    mask=focus_mask(rgb.shape,selection).astype(bool)
    assert np.array_equal(output[mask],rgb[mask])
    assert not mask[100,100] and mask[100,40]
    assert result['focus_info']['statistics']['maximum_c']==42
    assert result['focus_info']['statistics']['maximum_location']=={'x':20,'y':50}
    assert np.array_equal(matrix,before)
    assert np.all(rgb==[210,70,160])

def test_feather_preserves_selected_pixels_and_thin_fittings_at_two_resolutions():
    selection=InsulatorFocus(points=POINTS,preserve_original=True,background_mode='solid',background_dim=1,feather=.006,
        strokes=[{'points':[{'x':.5,'y':.1},{'x':.5,'y':.01}],'radius':.005,'erase':False}])
    for width in (100,400):
        rgb=np.full((width,width,3),[220,100,10],np.uint8)
        render=render_enhancement(rgb,EnhancementSettings(focus=selection));output=pixels(render)
        mask=focus_mask(rgb.shape,selection).astype(bool)
        assert np.array_equal(output[mask],rgb[mask])
        assert np.all(output[0,0]==[8,19,40])
        assert mask[round(.02*(width-1)),round(.5*(width-1))]
        assert 'statistics' not in render['focus_info']

def test_visual_jpeg_export_full_size_original_download_and_package_without_matrix(workspace):
    factory,engine,path=workspace
    source=path/'source.jpg'
    Image.new('RGB',(1920,1280),(100,30,80)).save(source)
    before=source.read_bytes();digest=hashlib.sha256(before).hexdigest()
    with Session(engine) as db:
        item=db.get(ThermalImage,1);item.storage_name='source.jpg';item.sha256=digest
        # Existing failed analyses must not fabricate a matrix for an ordinary JPEG.
        db.get(AnalysisVersion,1).status='failed';db.commit()
    client=factory('bob')
    focus={'points':POINTS,'strokes':[{'points':[{'x':.5,'y':.5}],'radius':.02,'erase':True}],
           'background_mode':'blue','background_dim':1,'preserve_original':True}
    body={'enhancement':{'focus':focus}}
    response=client.post('/api/images/1/exports/enhanced',json=body)
    assert response.status_code==200,response.text
    out=Image.open(io.BytesIO(response.content));assert out.size==(1920,1280)
    assert 'Visually processed' in out.info['Processing']
    selected=focus_mask((1280,1920),InsulatorFocus(**focus)).astype(bool)
    assert np.array_equal(np.asarray(out)[selected],np.asarray(Image.open(source))[selected])
    assert client.get('/api/images/1/original').content==before
    unavailable=client.post('/api/images/1/exports/enhanced',json={'enhancement':{'palette':'iron_red'}})
    assert unavailable.status_code==422
    assert factory('alice').get('/api/images/1/original').status_code==404
    assert factory('alice').post('/api/images/1/exports/enhanced',json=body).status_code==404
    package=client.post('/api/images/1/exports/package',json=body)
    assert package.status_code==200,package.text
    with ZipFile(io.BytesIO(package.content)) as archive:
        import json
        manifest=json.loads(archive.read('manifest.json'))
        assert manifest['analysis'] is None and manifest['files']['matrix'] is None
        assert archive.read(manifest['files']['original'])==before
    restored=client.post('/api/inspections/1/packages',files={'file':('sample.thermalpkg',package.content)})
    assert restored.status_code==201,restored.text
    saved=client.get(f"/api/images/{restored.json()['id']}/enhancement").json()
    assert saved['focus']['strokes']==focus['strokes'] and saved['focus']['preserve_original']
    assert source.read_bytes()==before
