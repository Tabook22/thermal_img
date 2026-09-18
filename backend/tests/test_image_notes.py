from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import create_image_note, delete_image_note, list_image_notes, update_image_note
from app.models import Base, ThermalImage
from app.schemas import ImageNoteInput


def test_sticky_notes_persist_without_replacing_image_metadata():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ThermalImage(id=1, inspection_id=1, original_name="thermal.JPG",
                            storage_name="originals/unchanged.JPG", sha256="a" * 64,
                            classification="supported_radiometric",
                            metadata_json={"preview_path": "previews/unchanged.jpg"}))
        db.commit()

        body = ImageNoteInput(text="Check upper fitting", x=.25, y=.4,
                              font="serif", font_size=20, color="yellow")
        created = create_image_note(1, body, db)
        assert created["text"] == "Check upper fitting"
        assert list_image_notes(1, db) == [created]

        changed = update_image_note(1, created["id"], ImageNoteInput(
            text="Inspect clamp", x=.5, y=.3, font="mono", font_size=8, color="blue",
            background_color="#123456", text_color="#ffffff", width=280, height=140,
            visible=False, bold=True, italic=True, underline=True), db)
        assert list_image_notes(1, db) == [changed]
        assert (changed["background_color"], changed["text_color"], changed["width"], changed["height"]) == ("#123456", "#ffffff", 280, 140)
        assert changed["font_size"] == 8 and changed["visible"] is False
        assert changed["bold"] and changed["italic"] and changed["underline"]
        assert db.get(ThermalImage, 1).metadata_json["preview_path"] == "previews/unchanged.jpg"
        assert db.get(ThermalImage, 1).storage_name == "originals/unchanged.JPG"

        delete_image_note(1, created["id"], db)
        assert list_image_notes(1, db) == []
