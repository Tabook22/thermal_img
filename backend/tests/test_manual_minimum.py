import numpy as np
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import main
from app.models import AnalysisVersion, Base, Region
from app.schemas import Point, RegionCreate


def test_manual_minimum_is_measured_inside_region_and_can_reset(monkeypatch):
    matrix = np.array([[10, 11, 12], [20, 21, 22], [30, 31, 32]], dtype=np.float32)
    valid = np.ones_like(matrix, dtype=bool)
    monkeypatch.setattr(main, "load_matrix", lambda _: (matrix, valid))
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AnalysisVersion(id=1, image_id=1, version=1, status="completed"))
        db.add(Region(id=1, analysis_id=1, name="Insulator 1", kind="rectangle",
                      geometry_json={"points": [{"x": 0, "y": 0}, {"x": 1, "y": 2}]},
                      stats_json={"minimum_c": 10.0, "maximum_c": 31.0}, is_reference=False))
        db.commit()

        with pytest.raises(HTTPException) as outside:
            main.set_region_minimum(1, Point(x=2, y=1), db)
        assert outside.value.status_code == 422

        selected = main.set_region_minimum(1, Point(x=1, y=1), db)
        assert selected["minimum_selection"] == {"x": 1, "y": 1, "temperature_c": 21.0}
        assert main.list_regions(1, db)[0]["statistics"]["minimum_c"] == 10.0

        updated = main.update_region(1, RegionCreate(name="Insulator 1", kind="rectangle",
            points=[Point(x=0, y=0), Point(x=1, y=2)]), db)
        assert updated["minimum_selection"]["temperature_c"] == 21.0

        moved = main.update_region(1, RegionCreate(name="Insulator 1", kind="rectangle",
            points=[Point(x=1, y=0), Point(x=2, y=2)], minimum_point=Point(x=2, y=1)), db)
        assert moved["minimum_selection"] == {"x": 2, "y": 1, "temperature_c": 22.0}
        assert moved["statistics"]["minimum_c"] == 11.0

        excluded = main.update_region(1, RegionCreate(name="Insulator 1", kind="rectangle",
            points=[Point(x=0, y=0), Point(x=1, y=2)]), db)
        assert excluded["minimum_selection"] is None

        assert main.reset_region_minimum(1, db)["minimum_selection"] is None
        assert main.list_regions(1, db)[0]["minimum_selection"] is None

        filtered = main.range_statistics(1, 20.0, 30.0, db)
        assert filtered["full"]["valid_pixels"] == 4
        assert filtered["full"]["minimum_c"] == 20.0
        assert filtered["full"]["maximum_c"] == 30.0
        assert filtered["regions"]["1"]["valid_pixels"] == 3

        empty = main.range_statistics(1, 40.0, 50.0, db)
        assert empty["full"]["valid_pixels"] == 0
        assert empty["regions"]["1"]["minimum_c"] is None


def test_missing_analysis_and_empty_region_are_client_errors(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        with pytest.raises(HTTPException) as missing:
            main.pixel(999, 0, 0, db)
        assert missing.value.status_code == 404

        matrix = np.full((2, 2), np.nan, dtype=np.float32)
        valid = np.isfinite(matrix)
        monkeypatch.setattr(main, "load_matrix", lambda _: (matrix, valid))
        db.add(AnalysisVersion(id=2, image_id=1, version=1, status="completed"))
        db.commit()
        with pytest.raises(HTTPException) as empty:
            main.create_region(2, RegionCreate(name="Empty", kind="rectangle",
                points=[Point(x=0, y=0), Point(x=1, y=1)]), db)
        assert empty.value.status_code == 422
        assert empty.value.detail["code"] == "empty_region"


def test_line_temperature_region_is_created_and_recalculated(monkeypatch):
    matrix = np.arange(25, dtype=np.float32).reshape(5, 5)
    valid = np.ones_like(matrix, dtype=bool)
    monkeypatch.setattr(main, "load_matrix", lambda _: (matrix, valid))
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AnalysisVersion(id=3, image_id=1, version=1, status="completed"))
        db.commit()

        created = main.create_region(3, RegionCreate(
            name="Line 1", kind="line",
            points=[Point(x=0, y=0), Point(x=4, y=4)],
        ), db)
        assert created["kind"] == "line"
        assert created["statistics"]["minimum_c"] == 0.0
        assert created["statistics"]["maximum_c"] == 24.0
        assert created["statistics"]["mean_c"] == 12.0
        assert created["statistics"]["valid_pixels"] == 5

        updated = main.update_region(created["id"], RegionCreate(
            name="Line 1", kind="line",
            points=[Point(x=0, y=4), Point(x=4, y=0)],
        ), db)
        assert updated["statistics"]["minimum_location"] == {"x": 4, "y": 0}
        assert updated["statistics"]["maximum_location"] == {"x": 0, "y": 4}
        assert updated["statistics"]["mean_c"] == 12.0
