from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class InspectionCreate(BaseModel):
    tower_code: str = Field(min_length=1, max_length=100)
    circuit: str | None = None; phase: str | None = None; insulator_identifier: str | None = None; direction: str | None = None
    capture_time: datetime | None = None; inspector_notes: str | None = None; ambient_conditions: dict | None = None; electrical_load: str | None = None

class MeasurementParameters(BaseModel):
    emissivity: float | None = Field(None, ge=.1, le=1); reflected_temperature: float | None = Field(None, ge=-40, le=100)
    distance: float | None = Field(None, ge=1, le=300); humidity: float | None = Field(None, ge=1, le=100); atmospheric_temperature: float | None = Field(None, ge=-40, le=80)

class AnalysisStart(BaseModel): parameters: MeasurementParameters = MeasurementParameters()

class Point(BaseModel): x: int = Field(ge=0); y: int = Field(ge=0)
class ImageNoteInput(BaseModel):
    text: str = Field(max_length=2000)
    x: float = Field(ge=0,le=1)
    y: float = Field(ge=0,le=1)
    font: Literal["sans","serif","mono"] = "sans"
    font_size: int = Field(16,ge=8,le=36)
    color: Literal["yellow","blue","pink"] = "yellow"
    background_color: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    text_color: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    width: int = Field(165, ge=120, le=700)
    height: int = Field(70, ge=70, le=600)
    visible: bool = True
    bold: bool = False
    italic: bool = False
    underline: bool = False

class DrawingPoint(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)

class ImageDrawingInput(BaseModel):
    kind: Literal["freehand", "line", "ellipse", "arrow"]
    points: list[DrawingPoint] = Field(min_length=2, max_length=1000)
    control: DrawingPoint | None = None
    color: str = Field("#ff7b2b", pattern=r"^#[0-9a-fA-F]{6}$")
    stroke_width: float = Field(4, ge=1, le=20)

    @model_validator(mode="after")
    def valid_geometry(self):
        if self.kind != "freehand" and len(self.points) != 2:
            raise ValueError("Line, ellipse, and arrow need exactly two endpoints")
        if self.kind != "arrow" and self.control is not None:
            raise ValueError("Only arrows can have a bend control point")
        return self

class RegionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100); kind: str = Field(pattern="^(rectangle|polygon|circle)$"); points: list[Point]; is_reference: bool = False
    minimum_point: Point | None = None
    @model_validator(mode="after")
    def valid_points(self):
        need = 2 if self.kind in ("rectangle", "circle") else 3
        if len(self.points) < need: raise ValueError(f"{self.kind} requires at least {need} points")
        return self
class HotspotRequest(BaseModel): threshold_c: float; minimum_area: int = Field(1, ge=1, le=100000); reference_region_id: int | None = None
