"""Explicit read-only oversight routes; normal workspace routes retain ownership checks."""
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .audit import ActivityRoute
from .database import get_db
from .inspection_package import ExportWorkspace, safe_stem
from .models import AnalysisVersion, Inspection, Region, ThermalImage, Tower, User

router = APIRouter(prefix="/api/admin",route_class=ActivityRoute)


def owner_view(user):
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "status": "Deleted" if user.is_deleted else "Active" if user.is_active else "Disabled"}


@router.get("/workspaces")
def workspaces(db: Session = Depends(get_db)):
    inspection_counts = dict(db.execute(select(Inspection.owner_id, func.count(Inspection.id)).group_by(Inspection.owner_id)).all())
    image_counts = dict(db.execute(select(Inspection.owner_id, func.count(ThermalImage.id)).join(ThermalImage).group_by(Inspection.owner_id)).all())
    return [{**owner_view(user), "inspection_count": inspection_counts.get(user.id, 0), "image_count": image_counts.get(user.id, 0)}
            for user in db.scalars(select(User).order_by(User.display_name, User.id)).all()]


@router.get("/inspections")
def inspections(owner_id: int | None = None, q: str = Query("", max_length=200),
                offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    counts = select(ThermalImage.inspection_id, func.count(ThermalImage.id).label("image_count")).group_by(ThermalImage.inspection_id).subquery()
    stmt = select(Inspection, Tower, User, func.coalesce(counts.c.image_count, 0)).join(Tower, Tower.id == Inspection.tower_id).join(User, User.id == Inspection.owner_id).outerjoin(counts, counts.c.inspection_id == Inspection.id)
    if owner_id is not None:
        stmt = stmt.where(Inspection.owner_id == owner_id)
    if q.strip():
        term = q.strip()
        matching_images = select(ThermalImage.inspection_id).where(ThermalImage.original_name.icontains(term, autoescape=True))
        stmt = stmt.where(Tower.tower_code.icontains(term, autoescape=True) | Tower.circuit.icontains(term, autoescape=True) |
                          User.username.icontains(term, autoescape=True) | User.display_name.icontains(term, autoescape=True) |
                          Inspection.id.in_(matching_images))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(Inspection.created_at.desc(), Inspection.id.desc()).offset(offset).limit(limit)).all()
    return {"total": total, "items": [{"id": item.id, "tower_code": tower.tower_code, "circuit": tower.circuit,
            "phase": item.phase, "created_at": item.created_at, "notes": item.inspector_notes,
            "owner": owner_view(owner), "image_count": count} for item, tower, owner, count in rows]}


@router.get("/inspections/{inspection_id}/images")
def images(inspection_id: int, db: Session = Depends(get_db)):
    from .main import list_images
    result = list_images(inspection_id, db)
    for item in result:
        item["preview_url"] = f"/api/admin/images/{item['id']}/preview"
    return result


@router.get("/images/{image_id}/preview")
def original_preview(image_id: int, db: Session = Depends(get_db)):
    from .main import get_preview
    return get_preview(image_id, db)


def saved_workspace(image_id: int, db: Session):
    from .main import image_workspace
    workspace = image_workspace(image_id, db).model_dump()
    metadata = db.get(ThermalImage, image_id).metadata_json or {}
    # Individual edits may have been saved after the last full workspace snapshot.
    for key in ("enhancement", "drawings", "notes"):
        if key in metadata:
            workspace[key] = metadata[key]
    return ExportWorkspace.model_validate(workspace)


@router.get("/images/{image_id}/review")
def review(image_id: int, db: Session = Depends(get_db)):
    from .main import analysis_dict, region_dict
    image = db.get(ThermalImage, image_id)
    inspection = db.get(Inspection, image.inspection_id)
    owner = db.get(User, inspection.owner_id)
    latest = db.scalar(select(AnalysisVersion).where(AnalysisVersion.image_id == image_id).order_by(AnalysisVersion.version.desc()).limit(1))
    completed = db.scalar(select(AnalysisVersion).where(AnalysisVersion.image_id == image_id, AnalysisVersion.status == "completed").order_by(AnalysisVersion.version.desc()).limit(1))
    regions = [region_dict(item) for item in db.scalars(select(Region).where(Region.analysis_id == completed.id)).all()] if completed else []
    return {"id": image.id, "name": image.original_name, "created_at": image.created_at, "owner": owner_view(owner),
            "classification": image.classification, "analysis": analysis_dict(latest) if latest else None,
            "report_analysis": analysis_dict(completed) if completed else None, "regions": regions,
            "workspace": saved_workspace(image_id, db), "capture_metadata": (image.metadata_json or {}).get("capture_metadata"),
            "preview_url": f"/api/admin/images/{image.id}/preview", "report_url": f"/api/admin/images/{image.id}/report"}


@router.get("/images/{image_id}/report")
def saved_report(image_id: int, db: Session = Depends(get_db)):
    from .main import export_material
    image, _, _, _, report = export_material(image_id, saved_workspace(image_id, db), db)
    filename = f"{safe_stem(image.original_name)}-review.png"
    return StreamingResponse(io.BytesIO(report), media_type="image/png",
                             headers={"Content-Disposition": f'inline; filename="{filename}"'})
