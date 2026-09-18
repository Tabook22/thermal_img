from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import create_image_drawing, delete_image_drawing, list_image_drawings, update_image_drawing
from app.models import Base, ThermalImage
from app.schemas import ImageDrawingInput


def test_drawings_persist_and_arrow_bend_can_be_updated():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ThermalImage(id=1, inspection_id=1, original_name="thermal.JPG",
                            storage_name="originals/thermal.JPG", sha256="a" * 64,
                            classification="ordinary_image", metadata_json={"notes": [{"id": "keep"}]}))
        db.commit()
        body = ImageDrawingInput(kind="arrow", points=[{"x": .1, "y": .2}, {"x": .8, "y": .7}])
        created = create_image_drawing(1, body, db)
        assert list_image_drawings(1, db) == [created]
        curved = update_image_drawing(1, created["id"], ImageDrawingInput(
            kind="arrow", points=body.points, control={"x": .65, "y": .1},
            color="#00ffff", stroke_width=6), db)
        assert curved["control"] == {"x": .65, "y": .1}
        assert list_image_drawings(1, db) == [curved]
        assert db.get(ThermalImage, 1).metadata_json["notes"] == [{"id": "keep"}]
        delete_image_drawing(1, created["id"], db)
        assert list_image_drawings(1, db) == []
