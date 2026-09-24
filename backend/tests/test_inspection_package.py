import asyncio
import io
import hashlib
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from fastapi import UploadFile
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.inspection_package import ExportWorkspace, validate_archive
from app.main import export_editable_package, import_editable_package
from app.models import AnalysisVersion, Base, Inspection, Region, ThermalImage, Tower


def test_package_preserves_source_matrix_and_restores_workspace(tmp_path: Path):
    previous_root = settings.storage_root
    settings.storage_root = tmp_path
    try:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        original = tmp_path / "originals/source.jpg"
        preview = tmp_path / "previews/source.jpg"
        matrix_path = tmp_path / "matrices/source.npz"
        for path in (original, preview, matrix_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        pixels = np.zeros((24, 32, 3), dtype=np.uint8); pixels[:, :, 0] = 90
        Image.fromarray(pixels).save(original); Image.fromarray(pixels).save(preview)
        guide = tmp_path / "guides/reference.png"; guide.parent.mkdir(parents=True, exist_ok=True)
        second_guide = tmp_path / "guides/detail.png"
        Image.fromarray(np.full((10, 16, 3), 180, dtype=np.uint8)).save(guide)
        Image.fromarray(np.full((12, 8, 3), 120, dtype=np.uint8)).save(second_guide)
        temperatures = np.linspace(20, 45, 24 * 32, dtype=np.float32).reshape(24, 32)
        valid = np.ones_like(temperatures, dtype=bool)
        np.savez_compressed(matrix_path, temperatures=temperatures, valid_mask=valid)
        digest = hashlib.sha256(original.read_bytes()).hexdigest()

        with Session(engine) as db:
            tower = Tower(tower_code="TEST"); db.add(tower); db.flush()
            first = Inspection(tower_id=tower.id); second = Inspection(tower_id=tower.id); db.add_all([first, second]); db.flush()
            image = ThermalImage(inspection_id=first.id, original_name="source.jpg", storage_name="originals/source.jpg", sha256=digest, classification="supported_radiometric", metadata_json={"preview_path":"previews/source.jpg","source_preserved":True,"guide_images":[{"id":"guide-1","path":"guides/reference.png","name":"Reference"},{"id":"guide-2","path":"guides/detail.png","name":"Detail"}]})
            db.add(image); db.flush()
            analysis = AnalysisVersion(image_id=image.id, version=1, status="completed", sdk_version="test", matrix_path="matrices/source.npz", width=32, height=24, parameters_json={}, parameters_provenance={}, stats_json={"minimum_c":20.0,"maximum_c":45.0,"mean_c":32.5,"valid_pixels":768,"minimum_location":{"x":0,"y":0},"maximum_location":{"x":31,"y":23}}, warnings_json=[])
            db.add(analysis); db.flush()
            db.add(Region(analysis_id=analysis.id,name="Insulator",kind="rectangle",geometry_json={"points":[{"x":2,"y":2},{"x":20,"y":20}],"minimum_selection":None},stats_json=analysis.stats_json,is_reference=False)); db.commit()
            workspace = ExportWorkspace(insulator_label="inner", insulator_label_x=.35, insulator_label_y=.2, insulator_label_width=.3, guide_overlays=[{"id":"guide-1","x":.5,"y":.1,"width":.25,"height":.3,"zoom":1.5},{"id":"guide-2","x":.1,"y":.5,"width":.2,"height":.25,"zoom":2}], probes=[{"x":10,"y":10,"temperature_c":30.0}], notes=[{"id":"note-1","text":"Inspect","x":.1,"y":.1}])
            workspace = ExportWorkspace.model_validate({**workspace.model_dump(),"crop":{"x":.25,"y":.25,"width":.5,"height":.5}})
            response = export_editable_package(image.id, workspace, db)
            package_path = Path(response.path)
            with ZipFile(package_path) as archive:
                manifest = validate_archive(archive)
                assert archive.read(manifest["files"]["original"]) == original.read_bytes()
                with np.load(archive.open(manifest["files"]["matrix"]), allow_pickle=False) as saved:
                    np.testing.assert_array_equal(saved["temperatures"], temperatures)
                    np.testing.assert_array_equal(saved["valid_mask"], valid)
                assert archive.read(manifest["files"]["report"]).startswith(b"\x89PNG")
                assert Image.open(io.BytesIO(archive.read(manifest["files"]["report"]))).size == (16,12)
                assert archive.read(manifest["files"]["guides"]["guide-1"]).startswith(b"\x89PNG")
                assert archive.read(manifest["files"]["guides"]["guide-2"]).startswith(b"\x89PNG")

            with package_path.open("rb") as stream:
                restored = asyncio.run(import_editable_package(second.id, UploadFile(file=stream, filename="saved.thermalpkg"), db))
            restored_image = db.get(ThermalImage, restored["id"])
            assert restored_image.sha256 == digest
            assert (tmp_path / restored_image.storage_name).read_bytes() == original.read_bytes()
            assert restored_image.metadata_json["workspace"]["probes"][0]["temperature_c"] == 30.0
            assert restored_image.metadata_json["workspace"]["insulator_label"] == "inner"
            assert restored_image.metadata_json["workspace"]["crop"] == workspace.crop.model_dump()
            assert restored_image.metadata_json["workspace"]["insulator_label_x"] == .35
            assert restored_image.metadata_json["workspace"]["insulator_label_width"] == .3
            assert restored_image.metadata_json["workspace"]["guide_overlays"][0]["width"] == .25
            assert restored_image.metadata_json["workspace"]["guide_overlays"][1]["zoom"] == 2
            assert len(restored_image.metadata_json["guide_images"]) == 2
            assert all((tmp_path / item["path"]).is_file() for item in restored_image.metadata_json["guide_images"])
            restored_analysis = db.scalar(select(AnalysisVersion).where(AnalysisVersion.image_id == restored_image.id))
            with np.load(tmp_path / restored_analysis.matrix_path) as saved:
                np.testing.assert_array_equal(saved["temperatures"], temperatures)
            assert db.scalar(select(Region).where(Region.analysis_id == restored_analysis.id)).name == "Insulator"
    finally:
        settings.storage_root = previous_root
