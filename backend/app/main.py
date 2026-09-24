from __future__ import annotations
import asyncio, csv, hashlib, io, json, math, os, re, shutil, uuid
from zipfile import BadZipFile, ZipFile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
import numpy as np
import pymupdf
from PIL import Image
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .config import settings
from .auth import active_user, authorize_request, private_library_root, router as auth_router
from .admin_review import router as admin_review_router
from .audit import ActivityRoute, add_event
from .activity import router as activity_router
from .inspection_bridge import router as inspection_bridge_router
from .branding import BrandingSettings, logo_path, public_branding, save_branding, store_logo
from .conversation_pdf import render_conversation_pdf, render_conversation_text
from .dji_palette import official_palette_luts
from .enhancement import EnhancementSettings, auto_settings, render_enhancement
from .database import get_db, SessionLocal
from .image_metadata import capture_note_text, extract_capture_metadata
from .image_details import original_image_details
from .inspection_package import ExportWorkspace, PACKAGE_FORMAT, PACKAGE_VERSION, render_report_png, safe_stem, validate_archive, write_package
from .knowledge_base import MAX_DOCUMENT_BYTES, MAX_MEDIA_BYTES, MEDIA, SUPPORTED, TEXT_EDITABLE, add_document, delete_document, get_document, library_root, list_documents, search_documents, update_text_document
from .models import AnalysisVersion, HotspotObservation, Inspection, Region, ThermalImage, Tower
from .schemas import AnalysisStart, HotspotRequest, ImageDrawingInput, ImageNoteInput, InspectionCreate, Point, RegionCreate
from .thermal import DecodeError, DjiCliDecoder, UnsupportedThermalImage, hotspots, image_signature, preview, region_mask, statistics
from pydantic import BaseModel, Field

app = FastAPI(title="Tower Thermal Inspector API", version="1.0.0", dependencies=[Depends(authorize_request)])
app.router.route_class=ActivityRoute
app.include_router(activity_router)
app.include_router(inspection_bridge_router)
app.include_router(auth_router)
app.include_router(admin_review_router)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def private_response_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response
settings.storage_root.mkdir(parents=True, exist_ok=True)
executor = ThreadPoolExecutor(max_workers=settings.decoder_concurrency)
decoder = DjiCliDecoder(settings.dji_irp_path or Path("missing-dji-irp"), settings.dji_sdk_version, settings.decoder_timeout_seconds)

def fail(status:int, code:str, message:str): raise HTTPException(status, {"code":code,"message":message})
def analysis_dict(a): return {"id":a.id,"image_id":a.image_id,"version":a.version,"status":a.status,"sdk_version":a.sdk_version,"width":a.width,"height":a.height,"parameters":a.parameters_json,"parameter_provenance":a.parameters_provenance,"statistics":a.stats_json,"warnings":a.warnings_json,"error":a.error}
@lru_cache(maxsize=8)
def cached_matrix(path:str):
    with np.load(path) as data:
        matrix=data["temperatures"]; valid=data["valid_mask"]
    matrix.setflags(write=False); valid.setflags(write=False)
    return matrix,valid
def load_matrix(a):
    if a is None: fail(404,"analysis_not_found","Analysis not found")
    if a.status != "completed" or not a.matrix_path: fail(409,"analysis_not_ready","Analysis is not completed")
    try:
        return cached_matrix(str(settings.storage_root/a.matrix_path))
    except (OSError, KeyError, ValueError):
        fail(409,"analysis_matrix_missing","Stored temperature matrix is missing or unreadable")

def region_statistics(matrix,valid,mask):
    try:
        return statistics(matrix,valid&mask)
    except DecodeError as exc:
        fail(422,"empty_region",str(exc))

@app.get("/api/health")
def health(): return {"status":"ok","decoder_available":decoder.available(),"sdk_version":settings.dji_sdk_version}

@app.get("/api/settings/branding")
def get_branding():
    return public_branding(settings.storage_root)

@app.put("/api/settings/branding")
def update_branding(body:BrandingSettings):
    save_branding(settings.storage_root,body)
    return public_branding(settings.storage_root)

@app.post("/api/settings/logos/{kind}")
async def upload_branding_logo(kind:Literal["company","application"],file:UploadFile=File(...)):
    suffix=Path(file.filename or "logo").suffix.lower()
    if suffix not in {".png",".jpg",".jpeg"}: fail(422,"unsupported_logo","Choose a PNG or JPEG logo")
    temporary=settings.storage_root/"branding"/f"upload-{uuid.uuid4().hex}{suffix}"; temporary.parent.mkdir(parents=True,exist_ok=True)
    size=0
    try:
        with temporary.open("wb") as output:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>5*1024*1024: fail(413,"logo_too_large","Logo must be 5 MB or smaller")
                output.write(chunk)
        try: store_logo(settings.storage_root,kind,temporary)
        except ValueError as exc: fail(422,"invalid_logo",str(exc))
        return public_branding(settings.storage_root)
    finally: temporary.unlink(missing_ok=True)

@app.get("/api/settings/assets/{kind}-logo")
def branding_logo(kind:Literal["company","application"]):
    path=logo_path(settings.storage_root,kind)
    if not path.is_file(): fail(404,"logo_not_found","Logo has not been configured")
    return FileResponse(path,media_type="image/png",headers={"Cache-Control":"no-cache"})

class LibrarySearch(BaseModel):
    query: str = Field(min_length=2, max_length=500)

class TextDocumentUpdate(BaseModel):
    text: str = Field(max_length=2_000_000)

class ConversationSource(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    locator: str | None = Field(default=None, max_length=255)
    excerpt: str | None = Field(default=None, max_length=1500)
    title: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=2048)

class ConversationMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(min_length=1, max_length=20000)
    sources: list[ConversationSource] = Field(default_factory=list, max_length=20)
    webSources: list[ConversationSource] = Field(default_factory=list, max_length=20)

class ConversationExport(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    format: Literal["pdf", "txt"] = "pdf"
    image_name: str | None = Field(default=None, max_length=255)
    messages: list[ConversationMessage] = Field(min_length=2, max_length=100)

class InternetSearch(BaseModel):
    query: str = Field(min_length=2, max_length=500)

@app.get("/api/library/documents")
def library_documents():
    return list_documents(private_library_root())

@app.post("/api/library/conversations", status_code=201)
def save_conversation(body:ConversationExport):
    if not any(message.role=="assistant" for message in body.messages):
        fail(422,"conversation_has_no_answer","Ask the assistant a question before saving the conversation")
    title=body.title.strip()
    if not title: fail(422,"conversation_title_required","Enter a title for the conversation")
    slug=re.sub(r"[^a-zA-Z0-9_-]+","-",title).strip("-")[:60] or "inspection-chat"
    suffix=f".{body.format}"
    temporary=library_root(private_library_root())/f"conversation-{uuid.uuid4().hex}{suffix}"
    filename=f"{slug}-{datetime.now():%Y%m%d-%H%M%S}{suffix}"
    try:
        messages=[message.model_dump() for message in body.messages]
        if body.format=="pdf":
            temporary.write_bytes(render_conversation_pdf(messages,body.image_name,title))
        else:
            temporary.write_text(render_conversation_text(messages,body.image_name,title),encoding="utf-8")
        return add_document(private_library_root(),temporary,filename)
    finally:
        temporary.unlink(missing_ok=True)

@app.post("/api/library/documents",status_code=201)
async def upload_library_document(file:UploadFile=File(...)):
    suffix=Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED:
        fail(422,"unsupported_document","Supported files: PDF, DOCX, XLSX, text, images, audio, and video")
    temporary=library_root(private_library_root())/f"upload-{uuid.uuid4().hex}{suffix}"
    size=0
    try:
        with temporary.open("wb") as output:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>(MAX_MEDIA_BYTES if suffix in MEDIA else MAX_DOCUMENT_BYTES): fail(413,"document_too_large","File exceeds the size limit")
                output.write(chunk)
        try: return add_document(private_library_root(),temporary,file.filename or "document")
        except (ValueError,RuntimeError,OSError,BadZipFile) as exc: fail(422,"document_unreadable",str(exc))
    finally:
        temporary.unlink(missing_ok=True)

@app.get("/api/library/documents/{document_id}/file")
def library_document_file(document_id:str):
    document=get_document(private_library_root(),document_id)
    if not document: fail(404,"document_not_found","Document not found")
    path=library_root(private_library_root())/document["stored_name"]
    suffix=path.suffix.lower()
    media_types={".mp3":"audio/mpeg",".wav":"audio/wav",".m4a":"audio/mp4",".ogg":"audio/ogg",".mp4":"video/mp4",".webm":"video/webm",".mov":"video/quicktime"}
    return FileResponse(path,filename=document["filename"],media_type=media_types.get(suffix),content_disposition_type="inline" if suffix in {".pdf",".jpg",".jpeg",".png",".txt",".md",".csv",*MEDIA} else "attachment")

@app.get("/api/library/documents/{document_id}/pages/{page_number}/preview")
def library_pdf_page_preview(document_id:str,page_number:int):
    document=get_document(private_library_root(),document_id)
    if not document: fail(404,"document_not_found","Document not found")
    path=library_root(private_library_root())/document["stored_name"]
    if path.suffix.lower()!=".pdf": fail(422,"not_pdf","This resource is not a PDF")
    with pymupdf.open(path) as pdf:
        if page_number<1 or page_number>len(pdf): fail(404,"page_not_found","PDF page not found")
        pixels=pdf[page_number-1].get_pixmap(matrix=pymupdf.Matrix(1.7,1.7),alpha=False)
        return StreamingResponse(io.BytesIO(pixels.tobytes("png")),media_type="image/png")

@app.get("/api/library/documents/{document_id}/text")
def library_document_text(document_id:str):
    document=get_document(private_library_root(),document_id)
    if not document: fail(404,"document_not_found","Document not found")
    if Path(document["stored_name"]).suffix.lower() not in TEXT_EDITABLE: fail(422,"document_not_editable","Only text files can be edited")
    path=library_root(private_library_root())/document["stored_name"]
    return {"text":path.read_text(encoding="utf-8-sig",errors="replace")}

@app.put("/api/library/documents/{document_id}/text")
def edit_library_document_text(document_id:str,body:TextDocumentUpdate):
    try: return update_text_document(private_library_root(),document_id,body.text)
    except FileNotFoundError: fail(404,"document_not_found","Document not found")
    except ValueError as exc: fail(422,"document_not_editable",str(exc))

@app.delete("/api/library/documents/{document_id}",status_code=204)
def remove_library_document(document_id:str):
    if not delete_document(private_library_root(),document_id): fail(404,"document_not_found","Document not found")

@app.post("/api/library/search")
def search_library(body:LibrarySearch):
    return {"results":search_documents(private_library_root(),body.query)}

@app.post("/api/internet/search")
def search_internet(body:InternetSearch):
    """Run an explicitly requested web search through the configured server key."""
    key=settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not key: fail(503,"internet_search_unavailable","Internet search is not configured on this server")
    try:
        import httpx
        response=httpx.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={"model":settings.openai_web_model or os.getenv("OPENAI_WEB_MODEL","gpt-4.1-mini"),"tools":[{"type":"web_search_preview"}],"instructions":"Answer clearly in Markdown with short paragraphs and useful headings or bullet lists. Do not add a duplicate list of sources; the interface displays source links separately. Web search cannot see the user's image. Never invent image details or claim you inspected the image itself.","input":body.query},timeout=45)
        if response.status_code>=400: fail(502,"internet_search_failed",f"The internet search service returned an error ({response.status_code})")
        payload=response.json(); results=[]; text=[]
        for item in payload.get("output",[]):
            if item.get("type")=="message":
                for content in item.get("content",[]):
                    if content.get("type")=="output_text":
                        text.append(content.get("text", ""))
                        for annotation in content.get("annotations",[]):
                            if annotation.get("type") in {"url_citation","web_search_result"}:
                                results.append({"title":annotation.get("title") or annotation.get("url"),"url":annotation.get("url")})
        return {"answer":"\n".join(text).strip(),"sources":results}
    except Exception as exc:
        if isinstance(exc,HTTPException): raise
        fail(502,"internet_search_failed",str(exc))

@app.post("/api/inspections", status_code=201)
def create_inspection(body: InspectionCreate, db:Session=Depends(get_db)):
    user=active_user()
    tower=db.scalar(select(Tower).where(Tower.tower_code==body.tower_code,Tower.owner_id==user.id))
    if not tower: tower=Tower(tower_code=body.tower_code,circuit=body.circuit,owner_id=user.id); db.add(tower); db.flush()
    fields=body.model_dump(exclude={"tower_code","circuit"}); item=Inspection(tower_id=tower.id,owner_id=user.id,**fields); db.add(item); db.commit()
    return {"id":item.id,"tower_code":tower.tower_code,"circuit":tower.circuit,**fields,"created_at":item.created_at}

@app.get("/api/inspections")
def list_inspections(q:str|None=None, db:Session=Depends(get_db)):
    stmt=select(Inspection,Tower).join(Tower).where(Inspection.owner_id==active_user().id)
    if q: stmt=stmt.where(Tower.tower_code.contains(q) | Tower.circuit.contains(q))
    return [{"id":i.id,"tower_code":t.tower_code,"circuit":t.circuit,"phase":i.phase,"created_at":i.created_at} for i,t in db.execute(stmt.order_by(Inspection.created_at.desc())).all()]

@app.post("/api/inspections/{inspection_id}/images", status_code=201)
async def upload_image(inspection_id:int, file:UploadFile=File(...), db:Session=Depends(get_db)):
    if not db.get(Inspection,inspection_id): fail(404,"inspection_not_found","Inspection not found")
    suffix=Path(file.filename or "upload").suffix[:10]; name=f"originals/{uuid.uuid4().hex}{suffix}"; path=settings.storage_root/name; path.parent.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(); size=0
    with path.open("wb") as out:
        while chunk:=await file.read(1024*1024):
            size+=len(chunk)
            if size>settings.max_upload_mb*1024*1024: out.close(); path.unlink(missing_ok=True); fail(413,"upload_too_large",f"Maximum upload size is {settings.max_upload_mb} MB")
            digest.update(chunk); out.write(chunk)
    sig=image_signature(path)
    if sig=="unknown": path.unlink(missing_ok=True); fail(400,"unreadable_file","Unsupported or corrupt file signature")
    preview_name=f"previews/{uuid.uuid4().hex}.jpg"; preview_path=settings.storage_root/preview_name; preview_path.parent.mkdir(parents=True,exist_ok=True)
    try: preview(path,preview_path)
    except DecodeError: path.unlink(missing_ok=True); fail(400,"unreadable_file","Corrupt or unreadable image")
    classification="pending_decoder" if sig=="jpeg" else "ordinary_image"
    capture=extract_capture_metadata(path)
    item=ThermalImage(inspection_id=inspection_id,original_name=file.filename or "upload",storage_name=name,sha256=digest.hexdigest(),classification=classification,camera_latitude=capture["latitude"],camera_longitude=capture["longitude"],metadata_json={"signature":sig,"preview_path":preview_name,"source_preserved":True,"capture_metadata":capture})
    db.add(item); db.commit(); return {"id":item.id,"name":item.original_name,"classification":classification,"sha256":item.sha256,"preview_url":f"/api/images/{item.id}/preview"}

@app.get("/api/inspections/{inspection_id}/images")
def list_images(inspection_id:int,db:Session=Depends(get_db)):
    result=[]
    for x in db.scalars(select(ThermalImage).where(ThermalImage.inspection_id==inspection_id).order_by(ThermalImage.created_at.desc())).all():
        latest=db.scalar(select(AnalysisVersion).where(AnalysisVersion.image_id==x.id).order_by(AnalysisVersion.version.desc()).limit(1))
        result.append({"id":x.id,"name":x.original_name,"classification":x.classification,"sha256":x.sha256,"preview_url":f"/api/images/{x.id}/preview","latest_analysis":analysis_dict(latest) if latest else None})
    return result

@app.get("/api/images/{image_id}/preview")
def get_preview(image_id:int,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    preview_name=(item.metadata_json or {}).get("preview_path")
    path=settings.storage_root/preview_name if preview_name else None
    if path is None or not path.is_file(): fail(404,"preview_not_found","Preview is not available")
    return FileResponse(path,media_type="image/jpeg")

class EnhancementRequest(BaseModel):
    settings: EnhancementSettings = Field(default_factory=EnhancementSettings)
    analysis_id: int | None = None


def enhancement_source(image_id:int, analysis_id:int|None, db:Session):
    from PIL import Image
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    preview_name=(item.metadata_json or {}).get("preview_path")
    if not preview_name: fail(404,"preview_not_found","Preview is not available")
    try:
        with Image.open(settings.storage_root/preview_name) as source:
            rgb=np.array(source.convert("RGB"))
    except OSError:
        fail(404,"preview_not_found","Preview is not available")
    matrix=valid=None
    if analysis_id is not None:
        analysis=db.get(AnalysisVersion,analysis_id)
        if analysis is None or analysis.image_id!=image_id:
            fail(404,"analysis_not_found","Analysis does not belong to this image")
        matrix,valid=load_matrix(analysis)
    return rgb,matrix,valid


@app.get("/api/images/{image_id}/enhancement")
def get_enhancement(image_id:int,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    return EnhancementSettings.model_validate((item.metadata_json or {}).get("enhancement",{}))


@app.put("/api/images/{image_id}/enhancement")
def save_enhancement(image_id:int,body:EnhancementSettings,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    item.metadata_json={**(item.metadata_json or {}),"enhancement":body.model_dump()}
    db.commit()
    return body


@app.post("/api/images/{image_id}/enhancement/preview")
def enhancement_preview(image_id:int,body:EnhancementRequest,db:Session=Depends(get_db)):
    rgb,matrix,valid=enhancement_source(image_id,body.analysis_id,db)
    image=db.get(ThermalImage,image_id)
    luts=official_palette_luts(settings.storage_root/image.storage_name,settings.dji_irp_path) if image else None
    try:
        return render_enhancement(rgb,body.settings,matrix,valid,luts)
    except ValueError as exc:
        fail(422,"enhancement_unavailable",str(exc))


@app.post("/api/images/{image_id}/enhancement/auto")
def enhancement_auto(image_id:int,body:EnhancementRequest,db:Session=Depends(get_db)):
    rgb,matrix,valid=enhancement_source(image_id,body.analysis_id,db)
    try:
        return auto_settings(rgb,matrix,valid)
    except ValueError as exc:
        fail(422,"enhancement_unavailable",str(exc))


@app.get("/api/images/{image_id}/details")
def image_details(image_id:int,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    source=settings.storage_root/item.storage_name
    if not source.is_file(): fail(404,"image_file_missing","Original image is missing from storage")
    capture=(item.metadata_json or {}).get("capture_metadata") or extract_capture_metadata(source)
    try:
        return original_image_details(source,capture,settings.dji_irp_path)
    except (OSError, ValueError):
        fail(400,"unreadable_file","Could not read image details")

def export_material(image_id:int,body:ExportWorkspace,db:Session):
    image=db.get(ThermalImage,image_id)
    if not image: fail(404,"image_not_found","Image not found")
    original=settings.storage_root/image.storage_name
    if not original.is_file(): fail(404,"image_file_missing","Original image is missing from storage")
    latest=db.scalar(select(AnalysisVersion).where(AnalysisVersion.image_id==image_id,AnalysisVersion.status=="completed").order_by(AnalysisVersion.version.desc()).limit(1))
    matrix=valid=None
    if latest: matrix,valid=load_matrix(latest)
    rgb,_,_=enhancement_source(image_id,None,db)
    regions=[region_dict(r) for r in db.scalars(select(Region).where(Region.analysis_id==latest.id)).all()] if latest else []
    luts=official_palette_luts(original,settings.dji_irp_path)
    metadata=image.metadata_json or {}; stored_guides=metadata.get("guide_images") or []
    guide_paths={str(item.get("id")):settings.storage_root/item["path"] for item in stored_guides if isinstance(item,dict) and item.get("id") and item.get("path")}
    legacy_name=metadata.get("guide_image_path")
    if legacy_name: guide_paths.setdefault("legacy",settings.storage_root/legacy_name)
    guide_images={}
    for placement in body.guide_overlays:
        path=guide_paths.get(placement.id)
        if path and path.is_file():
            with Image.open(path) as source: guide_images[placement.id]=source.convert("RGBA").copy()
    try: report=render_report_png(rgb,matrix,valid,body,regions,latest.stats_json if latest else None,luts,guide_images)
    except ValueError as exc: fail(422,"export_unavailable",str(exc))
    return image,latest,original,regions,report

@app.post("/api/images/{image_id}/exports/report")
def export_report_image(image_id:int,body:ExportWorkspace,db:Session=Depends(get_db)):
    image,_,_,_,report=export_material(image_id,body,db)
    filename=f"{safe_stem(image.original_name)}-report.png"
    return StreamingResponse(io.BytesIO(report),media_type="image/png",headers={"Content-Disposition":f'attachment; filename="{filename}"',"X-Thermal-Data":"flattened-display-only"})

@app.post("/api/images/{image_id}/exports/package")
def export_editable_package(image_id:int,body:ExportWorkspace,db:Session=Depends(get_db)):
    image,analysis,original,regions,report=export_material(image_id,body,db)
    export_root=settings.storage_root/"exports"; export_root.mkdir(parents=True,exist_ok=True)
    target=export_root/f"{uuid.uuid4().hex}.thermalpkg"
    original_suffix=Path(image.original_name).suffix.lower() or original.suffix.lower() or ".jpg"
    stored_guides=(image.metadata_json or {}).get("guide_images") or []
    stored_paths={str(item.get("id")):settings.storage_root/item["path"] for item in stored_guides if isinstance(item,dict) and item.get("id") and item.get("path")}
    legacy_name=(image.metadata_json or {}).get("guide_image_path")
    if legacy_name: stored_paths.setdefault("legacy",settings.storage_root/legacy_name)
    guide_paths={item.id:stored_paths[item.id] for item in body.guide_overlays if item.id in stored_paths and stored_paths[item.id].is_file()}
    files={"original":f"source/original{original_suffix}","report":"report/report.png","matrix":"data/temperature-matrix.npz" if analysis else None,"guides":{guide_id:f"support/guides/{guide_id}.png" for guide_id in guide_paths}}
    metadata=dict(image.metadata_json or {})
    for key in ("preview_path","enhancement","drawings","notes","workspace","guide_image_path","guide_images"): metadata.pop(key,None)
    manifest={
        "format":PACKAGE_FORMAT,"version":PACKAGE_VERSION,"created_at":datetime.utcnow().isoformat()+"Z",
        "source":{"original_name":image.original_name,"sha256":image.sha256,"classification":image.classification,"camera_model":image.camera_model,"camera_latitude":image.camera_latitude,"camera_longitude":image.camera_longitude,"metadata":metadata},
        "analysis":analysis_dict(analysis) if analysis else None,"regions":regions,"workspace":body.model_dump(),"files":files,
        "checksums":{"original_sha256":image.sha256,"report_sha256":hashlib.sha256(report).hexdigest(),"matrix_sha256":hashlib.sha256((settings.storage_root/analysis.matrix_path).read_bytes()).hexdigest() if analysis and analysis.matrix_path else None},
    }
    try: write_package(target,manifest,original,report,settings.storage_root/analysis.matrix_path if analysis and analysis.matrix_path else None,guide_paths)
    except Exception:
        target.unlink(missing_ok=True); raise
    filename=f"{safe_stem(image.original_name)}.thermalpkg"
    return FileResponse(target,filename=filename,media_type="application/vnd.tower-thermal-inspection+zip",background=BackgroundTask(target.unlink,missing_ok=True))

@app.get("/api/images/{image_id}/workspace")
def image_workspace(image_id:int,db:Session=Depends(get_db)):
    image=db.get(ThermalImage,image_id)
    if not image: fail(404,"image_not_found","Image not found")
    metadata=image.metadata_json or {}; saved=dict(metadata.get("workspace") or {})
    if not saved.get("guide_overlays") and saved.get("guide_overlay") and metadata.get("guide_image_path"):
        legacy=saved["guide_overlay"]
        saved["guide_overlays"]=[{"id":"legacy","x":legacy.get("x",.62),"y":legacy.get("y",.08),"width":legacy.get("width",.3),"height":legacy.get("height",legacy.get("width",.3)),"zoom":legacy.get("zoom",1)}]
    return ExportWorkspace.model_validate(saved)

@app.post("/api/images/{image_id}/guide-images",status_code=201)
async def upload_guide_images(image_id:int,file:UploadFile=File(...),db:Session=Depends(get_db)):
    image=db.get(ThermalImage,image_id)
    if not image: fail(404,"image_not_found","Image not found")
    metadata=image.metadata_json or {}; guides=list(metadata.get("guide_images") or [])
    if len(guides)>=100: fail(422,"guide_image_limit","Supporting image storage for this thermal image is full")
    content=await file.read(20*1024*1024+1)
    if not content or len(content)>20*1024*1024: fail(413,"guide_image_too_large","Guide image must be 20 MB or smaller")
    try:
        with Image.open(io.BytesIO(content)) as source: source.verify()
        with Image.open(io.BytesIO(content)) as source:
            source.thumbnail((4096,4096),Image.Resampling.LANCZOS)
            converted=source.convert("RGBA") if source.mode in ("RGBA","LA") or "transparency" in source.info else source.convert("RGB")
            guide_id=uuid.uuid4().hex; guide_name=f"guides/{guide_id}.png"; guide_path=settings.storage_root/guide_name; guide_path.parent.mkdir(parents=True,exist_ok=True)
            converted.save(guide_path,"PNG",optimize=True)
    except (OSError,ValueError):
        fail(422,"invalid_guide_image","Choose a valid PNG, JPEG, WEBP, or TIFF image")
    display_name=Path(file.filename or "guide.png").name[:255]
    guides.append({"id":guide_id,"path":guide_name,"name":display_name})
    image.metadata_json={**metadata,"guide_images":guides};db.commit()
    return {"id":guide_id,"url":f"/api/images/{image.id}/guide-images/{guide_id}","name":display_name}

@app.get("/api/images/{image_id}/guide-images/{guide_id}")
def get_guide_images(image_id:int,guide_id:str,db:Session=Depends(get_db)):
    image=db.get(ThermalImage,image_id)
    if not image: fail(404,"image_not_found","Image not found")
    item=next((item for item in ((image.metadata_json or {}).get("guide_images") or []) if isinstance(item,dict) and item.get("id")==guide_id),None)
    path=settings.storage_root/item["path"] if item and item.get("path") else None
    if path is None and guide_id=="legacy":
        legacy=(image.metadata_json or {}).get("guide_image_path")
        if legacy: path=settings.storage_root/legacy
    if not path or not path.is_file(): fail(404,"guide_image_not_found","Supporting image was not found")
    return FileResponse(path,media_type="image/png",headers={"Cache-Control":"no-store"})

@app.post("/api/images/{image_id}/guide-image",status_code=201)
async def upload_guide_image(image_id:int,file:UploadFile=File(...),db:Session=Depends(get_db)):
    image=db.get(ThermalImage,image_id)
    if not image: fail(404,"image_not_found","Image not found")
    content=await file.read(20*1024*1024+1)
    if not content or len(content)>20*1024*1024: fail(413,"guide_image_too_large","Guide image must be 20 MB or smaller")
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.verify()
        with Image.open(io.BytesIO(content)) as source:
            source.thumbnail((4096,4096),Image.Resampling.LANCZOS)
            converted=source.convert("RGBA") if source.mode in ("RGBA","LA") or "transparency" in source.info else source.convert("RGB")
            guide_name=f"guides/{uuid.uuid4().hex}.png"; guide_path=settings.storage_root/guide_name; guide_path.parent.mkdir(parents=True,exist_ok=True)
            converted.save(guide_path,"PNG",optimize=True)
    except (OSError,ValueError):
        fail(422,"invalid_guide_image","Choose a valid PNG, JPEG, WEBP, or TIFF image")
    metadata=image.metadata_json or {}; previous=metadata.get("guide_image_path")
    image.metadata_json={**metadata,"guide_image_path":guide_name};db.commit()
    if previous and previous!=guide_name:
        old=(settings.storage_root/previous).resolve()
        guides=(settings.storage_root/"guides").resolve()
        if guides in old.parents: old.unlink(missing_ok=True)
    return {"url":f"/api/images/{image.id}/guide-image","name":Path(file.filename or "guide.png").name[:255]}

@app.get("/api/images/{image_id}/guide-image")
def get_guide_image(image_id:int,db:Session=Depends(get_db)):
    image=db.get(ThermalImage,image_id)
    if not image: fail(404,"image_not_found","Image not found")
    name=(image.metadata_json or {}).get("guide_image_path"); path=settings.storage_root/name if name else None
    if not path or not path.is_file(): fail(404,"guide_image_not_found","No guide image has been added")
    return FileResponse(path,media_type="image/png",headers={"Cache-Control":"no-store"})

@app.put("/api/images/{image_id}/workspace")
def save_image_workspace(image_id:int,body:ExportWorkspace,db:Session=Depends(get_db)):
    image=db.get(ThermalImage,image_id)
    if not image: fail(404,"image_not_found","Image not found")
    image.metadata_json={**(image.metadata_json or {}),"workspace":body.model_dump(),"enhancement":body.enhancement.model_dump(),"drawings":[item.model_dump() for item in body.drawings],"notes":[item.model_dump() for item in body.notes]}
    db.commit()
    return {"saved":True,"image_id":image.id}

@app.post("/api/inspections/{inspection_id}/packages",status_code=201)
async def import_editable_package(inspection_id:int,file:UploadFile=File(...),db:Session=Depends(get_db)):
    if not db.get(Inspection,inspection_id): fail(404,"inspection_not_found","Inspection not found")
    if Path(file.filename or "").suffix.lower()!=".thermalpkg": fail(422,"unsupported_package","Choose a .thermalpkg file exported by this application")
    import_root=settings.storage_root/"imports"; import_root.mkdir(parents=True,exist_ok=True)
    temporary=import_root/f"{uuid.uuid4().hex}.thermalpkg"; written=0
    created_paths=[]
    try:
        with temporary.open("wb") as output:
            while chunk:=await file.read(1024*1024):
                written+=len(chunk)
                if written>settings.max_upload_mb*4*1024*1024: fail(413,"package_too_large","Inspection package exceeds the size limit")
                output.write(chunk)
        with ZipFile(temporary) as archive:
            manifest=validate_archive(archive); source=manifest.get("source") or {}; files=manifest["files"]
            raw_workspace=dict(manifest.get("workspace") or {})
            if not raw_workspace.get("guide_overlays") and raw_workspace.get("guide_overlay") and files.get("guide"):
                legacy=raw_workspace["guide_overlay"]
                raw_workspace["guide_overlays"]=[{"id":"legacy","x":legacy.get("x",.62),"y":legacy.get("y",.08),"width":legacy.get("width",.3),"height":legacy.get("height",legacy.get("width",.3)),"zoom":legacy.get("zoom",1)}]
                files={**files,"guides":{"legacy":files["guide"]}}
            workspace=ExportWorkspace.model_validate(raw_workspace)
            original_name=Path(source.get("original_name") or "restored-thermal.jpg").name[:255]
            suffix=Path(original_name).suffix[:10] or ".jpg"; storage_name=f"originals/{uuid.uuid4().hex}{suffix}"
            original_path=settings.storage_root/storage_name; original_path.parent.mkdir(parents=True,exist_ok=True); created_paths.append(original_path)
            digest=hashlib.sha256(); size=0
            with archive.open(files["original"]) as incoming, original_path.open("wb") as output:
                while chunk:=incoming.read(1024*1024):
                    size+=len(chunk)
                    if size>settings.max_upload_mb*1024*1024: raise ValueError("Original image exceeds the size limit")
                    digest.update(chunk); output.write(chunk)
            expected=source.get("sha256") or (manifest.get("checksums") or {}).get("original_sha256")
            if expected and digest.hexdigest()!=expected: raise ValueError("Original image checksum does not match the package manifest")
            sig=image_signature(original_path)
            if sig=="unknown": raise ValueError("Package original is not a supported image")
            preview_name=f"previews/{uuid.uuid4().hex}.jpg"; preview_path=settings.storage_root/preview_name; preview_path.parent.mkdir(parents=True,exist_ok=True); created_paths.append(preview_path); preview(original_path,preview_path)
            restored_guides=[]; guide_members=files.get("guides") or {}
            overlay_ids={item.id for item in workspace.guide_overlays}
            if not isinstance(guide_members,dict): raise ValueError("Inspection package guide list is invalid")
            for guide_id,guide_member in guide_members.items():
                if guide_id not in overlay_ids or not isinstance(guide_member,str): continue
                guide_bytes=archive.read(guide_member)
                if len(guide_bytes)>20*1024*1024: raise ValueError("Supporting image exceeds the supported size")
                with Image.open(io.BytesIO(guide_bytes)) as guide_source: guide_source.verify()
                guide_name=f"guides/{uuid.uuid4().hex}.png"; guide_path=settings.storage_root/guide_name; guide_path.parent.mkdir(parents=True,exist_ok=True);created_paths.append(guide_path);guide_path.write_bytes(guide_bytes)
                restored_guides.append({"id":guide_id,"path":guide_name,"name":f"Supporting image {len(restored_guides)+1}"})
            metadata=dict(source.get("metadata")) if isinstance(source.get("metadata"),dict) else {}
            # Package-supplied server paths must never provide access to another workspace.
            for key in ("guide_images","guide_image_path","preview_path","workspace","drawings","notes","enhancement"):
                metadata.pop(key,None)
            metadata={**metadata,"signature":sig,"preview_path":preview_name,"source_preserved":True,"imported_package":True,"enhancement":workspace.enhancement.model_dump(),"drawings":[x.model_dump() for x in workspace.drawings],"notes":[x.model_dump() for x in workspace.notes],"workspace":workspace.model_dump()}
            if restored_guides: metadata["guide_images"]=restored_guides
            image=ThermalImage(inspection_id=inspection_id,original_name=original_name,storage_name=storage_name,sha256=digest.hexdigest(),classification=source.get("classification") or ("pending_decoder" if sig=="jpeg" else "ordinary_image"),camera_model=source.get("camera_model"),camera_latitude=source.get("camera_latitude"),camera_longitude=source.get("camera_longitude"),metadata_json=metadata)
            db.add(image); db.flush(); imported_analysis=None
            saved_analysis=manifest.get("analysis"); matrix_member=files.get("matrix")
            if saved_analysis and matrix_member:
                matrix_bytes=archive.read(matrix_member)
                expected_matrix=(manifest.get("checksums") or {}).get("matrix_sha256")
                if expected_matrix and hashlib.sha256(matrix_bytes).hexdigest()!=expected_matrix: raise ValueError("Temperature matrix checksum does not match the package manifest")
                with np.load(io.BytesIO(matrix_bytes),allow_pickle=False) as data:
                    matrix=np.asarray(data["temperatures"],dtype=np.float32); valid=np.asarray(data["valid_mask"],dtype=bool)
                if matrix.ndim!=2 or matrix.shape!=valid.shape or matrix.size>50_000_000: raise ValueError("Temperature matrix has invalid dimensions")
                matrix_name=f"matrices/{uuid.uuid4().hex}.npz"; matrix_path=settings.storage_root/matrix_name; matrix_path.parent.mkdir(parents=True,exist_ok=True); created_paths.append(matrix_path); np.savez_compressed(matrix_path,temperatures=matrix,valid_mask=valid)
                imported_analysis=AnalysisVersion(image_id=image.id,version=1,status="completed",sdk_version=str(saved_analysis.get("sdk_version") or "package")[:50],matrix_path=matrix_name,width=matrix.shape[1],height=matrix.shape[0],parameters_json=saved_analysis.get("parameters") or {},parameters_provenance=saved_analysis.get("parameter_provenance") or {},stats_json=statistics(matrix,valid),warnings_json=["Restored from verified inspection package"],processed_at=datetime.utcnow())
                db.add(imported_analysis); db.flush()
                for saved_region in manifest.get("regions") or []:
                    validated=RegionCreate.model_validate({"name":saved_region.get("name"),"kind":saved_region.get("kind"),"points":saved_region.get("points"),"is_reference":bool(saved_region.get("is_reference")),"minimum_point":saved_region.get("minimum_selection")})
                    points=[p.model_dump() for p in validated.points]; mask=region_mask(matrix.shape,validated.kind,points); selected=minimum_selection(matrix,valid,mask,validated.minimum_point.model_dump() if validated.minimum_point else None)
                    db.add(Region(analysis_id=imported_analysis.id,name=validated.name,kind=validated.kind,geometry_json={"points":points,"minimum_selection":selected},stats_json=statistics(matrix,valid&mask),is_reference=validated.is_reference))
            db.commit()
            return {"id":image.id,"name":image.original_name,"classification":image.classification,"sha256":image.sha256,"preview_url":f"/api/images/{image.id}/preview","latest_analysis":analysis_dict(imported_analysis) if imported_analysis else None}
    except (BadZipFile,KeyError,ValueError,json.JSONDecodeError) as exc:
        db.rollback()
        for path in created_paths: path.unlink(missing_ok=True)
        fail(422,"invalid_inspection_package",str(exc))
    finally: temporary.unlink(missing_ok=True)

@app.get("/api/images/{image_id}/notes")
def list_image_notes(image_id:int,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    return (item.metadata_json or {}).get("notes",[])

@app.post("/api/images/{image_id}/capture-note")
def ensure_capture_note(image_id:int,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    metadata=item.metadata_json or {}
    capture=metadata.get("capture_metadata")
    previous_capture=capture
    if capture is None or not capture.get("overlay_checked"):
        capture=extract_capture_metadata(settings.storage_root/item.storage_name)
        item.camera_latitude=capture["latitude"]
        item.camera_longitude=capture["longitude"]
    notes=metadata.get("notes",[])
    existing=next((note for note in notes if note.get("id")==metadata.get("capture_note_id")),None)
    if existing and previous_capture:
        lat,lon=previous_capture.get("latitude"),previous_capture.get("longitude")
        old_gps=f"{lat:.6f}, {lon:.6f}" if lat is not None and lon is not None else "Not recorded"
        old_stamp=previous_capture.get("captured_at")
        old_date,old_time=old_stamp.split(" ",1) if old_stamp else ("Not recorded","Not recorded")
        if old_stamp: old_time+=f" {previous_capture['time_zone']}" if previous_capture.get("time_zone") else " (camera time)"
        old_generated=f"GPS: {old_gps}\nDate: {old_date}\nTime: {old_time}"
        if existing.get("text")==old_generated:
            existing={**existing,"text":capture_note_text(capture),"width":330,"height":160,"y":0.62}
            notes=[existing if note.get("id")==existing["id"] else note for note in notes]
    if existing and existing.get("text")==capture_note_text(capture) and existing.get("width")==260 and existing.get("height")==126:
        existing={**existing,"width":330,"height":160,"y":0.62}
        notes=[existing if note.get("id")==existing["id"] else note for note in notes]
    if not any(note.get("id")==metadata.get("capture_note_id") for note in notes):
        note={"id":uuid.uuid4().hex,"text":capture_note_text(capture),"x":0.03,"y":0.62,"font":"sans","font_size":14,"color":"yellow","width":330,"height":160}
        notes=[*notes,note]
        metadata={**metadata,"capture_note_id":note["id"]}
    item.metadata_json={**metadata,"capture_metadata":capture,"notes":notes}
    db.commit()
    return notes

@app.post("/api/images/{image_id}/notes",status_code=201)
def create_image_note(image_id:int,body:ImageNoteInput,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    note={"id":uuid.uuid4().hex,**body.model_dump()}
    metadata=item.metadata_json or {}; item.metadata_json={**metadata,"notes":[*metadata.get("notes",[]),note]}; db.commit()
    return note

@app.put("/api/images/{image_id}/notes/{note_id}")
def update_image_note(image_id:int,note_id:str,body:ImageNoteInput,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    metadata=item.metadata_json or {}; notes=metadata.get("notes",[])
    if not any(n["id"]==note_id for n in notes): fail(404,"note_not_found","Note not found")
    updated={"id":note_id,**body.model_dump()}
    item.metadata_json={**metadata,"notes":[updated if n["id"]==note_id else n for n in notes]}; db.commit()
    return updated

@app.delete("/api/images/{image_id}/notes/{note_id}",status_code=204)
def delete_image_note(image_id:int,note_id:str,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    metadata=item.metadata_json or {}; notes=metadata.get("notes",[])
    if not any(n["id"]==note_id for n in notes): fail(404,"note_not_found","Note not found")
    item.metadata_json={**metadata,"notes":[n for n in notes if n["id"]!=note_id]}; db.commit()

@app.get("/api/images/{image_id}/drawings")
def list_image_drawings(image_id:int,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    return (item.metadata_json or {}).get("drawings",[])

@app.post("/api/images/{image_id}/drawings",status_code=201)
def create_image_drawing(image_id:int,body:ImageDrawingInput,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    drawing={"id":uuid.uuid4().hex,**body.model_dump()}
    metadata=item.metadata_json or {}
    item.metadata_json={**metadata,"drawings":[*metadata.get("drawings",[]),drawing]}
    db.commit()
    return drawing

@app.put("/api/images/{image_id}/drawings/{drawing_id}")
def update_image_drawing(image_id:int,drawing_id:str,body:ImageDrawingInput,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    metadata=item.metadata_json or {}; drawings=metadata.get("drawings",[])
    if not any(d["id"]==drawing_id for d in drawings): fail(404,"drawing_not_found","Drawing not found")
    updated={"id":drawing_id,**body.model_dump()}
    item.metadata_json={**metadata,"drawings":[updated if d["id"]==drawing_id else d for d in drawings]}
    db.commit()
    return updated

@app.delete("/api/images/{image_id}/drawings/{drawing_id}",status_code=204)
def delete_image_drawing(image_id:int,drawing_id:str,db:Session=Depends(get_db)):
    item=db.get(ThermalImage,image_id)
    if not item: fail(404,"image_not_found","Image not found")
    metadata=item.metadata_json or {}; drawings=metadata.get("drawings",[])
    if not any(d["id"]==drawing_id for d in drawings): fail(404,"drawing_not_found","Drawing not found")
    item.metadata_json={**metadata,"drawings":[d for d in drawings if d["id"]!=drawing_id]}
    db.commit()

def run_analysis(analysis_id:int):
    db=SessionLocal(); analysis=db.get(AnalysisVersion,analysis_id); image=db.get(ThermalImage,analysis.image_id)
    try:
        analysis.status="processing"; db.commit(); source_path=(settings.storage_root/image.storage_name).resolve(); result=decoder.decode(source_path,analysis.parameters_json or {})
        matrix_name=f"matrices/{uuid.uuid4().hex}.npz"; matrix_path=settings.storage_root/matrix_name; matrix_path.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(matrix_path,temperatures=result.temperatures.astype(np.float32),valid_mask=result.valid_mask)
        analysis.status="completed"; analysis.sdk_version=result.sdk_version; analysis.matrix_path=matrix_name; analysis.width=result.width; analysis.height=result.height
        analysis.parameters_provenance=result.provenance; analysis.stats_json=statistics(result.temperatures,result.valid_mask); analysis.warnings_json=result.warnings; analysis.processed_at=datetime.utcnow()
        image.classification="supported_radiometric"; image.camera_model=result.camera_model; image.metadata_json={**(image.metadata_json or {}),**result.metadata,"measurement_ranges":result.ranges}
    except UnsupportedThermalImage as exc: analysis.status="failed"; analysis.error=str(exc); image.classification="ordinary_or_unsupported"
    except Exception as exc: analysis.status="failed"; analysis.error=str(exc)
    finally:
        db.commit()
        inspection=db.get(Inspection,image.inspection_id)
        if inspection and inspection.owner_id:
            add_event(db,inspection.owner_id,"analysis_complete","measurement","Temperature analysis completed" if analysis.status=="completed" else "Temperature analysis failed",image=image,outcome="success" if analysis.status=="completed" else "failed")
            db.commit()
        db.close()

@app.post("/api/images/{image_id}/analyses",status_code=202)
def start_analysis(image_id:int,body:AnalysisStart,background:BackgroundTasks,db:Session=Depends(get_db)):
    image=db.get(ThermalImage,image_id)
    if not image: fail(404,"image_not_found","Image not found")
    if not decoder.available(): fail(503,"sdk_unavailable","DJI Thermal SDK executable is unavailable; measurement is disabled")
    params=body.parameters.model_dump(exclude_none=True); existing=db.scalar(select(AnalysisVersion).where(AnalysisVersion.image_id==image_id,AnalysisVersion.parameters_json==params,AnalysisVersion.status=="completed"))
    if existing: return analysis_dict(existing)
    version=(db.scalar(select(func.max(AnalysisVersion.version)).where(AnalysisVersion.image_id==image_id)) or 0)+1
    item=AnalysisVersion(image_id=image_id,version=version,status="queued",parameters_json=params,warnings_json=[]); db.add(item); db.commit(); background.add_task(executor.submit,run_analysis,item.id); return analysis_dict(item)

@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id:int,db:Session=Depends(get_db)):
    item=db.get(AnalysisVersion,analysis_id)
    if not item: fail(404,"analysis_not_found","Analysis not found")
    return analysis_dict(item)

@app.get("/api/analyses/{analysis_id}/pixels/{x}/{y}")
def pixel(analysis_id:int,x:int,y:int,db:Session=Depends(get_db)):
    item=db.get(AnalysisVersion,analysis_id); matrix,valid=load_matrix(item)
    if not (0<=x<matrix.shape[1] and 0<=y<matrix.shape[0]): fail(422,"coordinate_out_of_bounds","Pixel is outside the native matrix")
    return {"x":x,"y":y,"temperature_c":float(matrix[y,x]) if valid[y,x] else None,"valid":bool(valid[y,x])}

@app.get("/api/analyses/{analysis_id}/range-stats")
def range_statistics(analysis_id:int,minimum_c:float=Query(ge=-20,le=150),maximum_c:float=Query(ge=-20,le=150),db:Session=Depends(get_db)):
    if not math.isfinite(minimum_c) or not math.isfinite(maximum_c) or minimum_c>=maximum_c: fail(422,"invalid_temperature_range","Choose finite bounds with minimum below maximum")
    item=db.get(AnalysisVersion,analysis_id)
    if not item: fail(404,"analysis_not_found","Analysis not found")
    matrix,valid=load_matrix(item)
    in_range=valid & (matrix>=minimum_c) & (matrix<=maximum_c)
    def measured(mask):
        if not mask.any(): return {"minimum_c":None,"maximum_c":None,"mean_c":None,"valid_pixels":0,"minimum_location":None,"maximum_location":None}
        return statistics(matrix,mask)
    regions={str(r.id):measured(in_range & region_mask(matrix.shape,r.kind,r.geometry_json["points"])) for r in db.scalars(select(Region).where(Region.analysis_id==analysis_id)).all()}
    return {"minimum_c":minimum_c,"maximum_c":maximum_c,"full":measured(in_range),"regions":regions}

@app.post("/api/analyses/{analysis_id}/regions",status_code=201)
def create_region(analysis_id:int,body:RegionCreate,db:Session=Depends(get_db)):
    analysis=db.get(AnalysisVersion,analysis_id); matrix,valid=load_matrix(analysis); points=[p.model_dump() for p in body.points]
    mask=region_mask(matrix.shape,body.kind,points); stat=region_statistics(matrix,valid,mask)
    minimum=minimum_selection(matrix,valid,mask,body.minimum_point.model_dump()) if body.minimum_point else None
    item=Region(analysis_id=analysis_id,name=body.name,kind=body.kind,geometry_json={"points":points,"minimum_selection":minimum},stats_json=stat,is_reference=body.is_reference); db.add(item); db.commit(); return region_dict(item)

def minimum_selection(matrix,valid,mask,point):
    if point is None: return None
    x,y=point["x"],point["y"]
    if not (0<=y<matrix.shape[0] and 0<=x<matrix.shape[1] and valid[y,x] and mask[y,x]): return None
    return {"x":x,"y":y,"temperature_c":float(matrix[y,x])}

def region_dict(item):
    return {"id":item.id,"name":item.name,"kind":item.kind,"points":item.geometry_json["points"],"statistics":item.stats_json,"is_reference":item.is_reference,"minimum_selection":item.geometry_json.get("minimum_selection")}

@app.put("/api/regions/{region_id}")
def update_region(region_id:int,body:RegionCreate,db:Session=Depends(get_db)):
    item=db.get(Region,region_id)
    if not item: fail(404,"region_not_found","Region not found")
    analysis=db.get(AnalysisVersion,item.analysis_id); matrix,valid=load_matrix(analysis); points=[p.model_dump() for p in body.points]; mask=region_mask(matrix.shape,body.kind,points); stat=region_statistics(matrix,valid,mask)
    previous=item.geometry_json.get("minimum_selection")
    selected_point=body.minimum_point.model_dump() if "minimum_point" in body.model_fields_set and body.minimum_point else (None if "minimum_point" in body.model_fields_set else previous)
    minimum=minimum_selection(matrix,valid,mask,selected_point)
    item.name=body.name; item.kind=body.kind; item.geometry_json={"points":points,"minimum_selection":minimum}; item.stats_json=stat; item.is_reference=body.is_reference; db.commit(); return region_dict(item)

@app.put("/api/regions/{region_id}/minimum")
def set_region_minimum(region_id:int,point:Point,db:Session=Depends(get_db)):
    item=db.get(Region,region_id)
    if not item: fail(404,"region_not_found","Region not found")
    analysis=db.get(AnalysisVersion,item.analysis_id); matrix,valid=load_matrix(analysis)
    mask=region_mask(matrix.shape,item.kind,item.geometry_json["points"])
    selected=minimum_selection(matrix,valid,mask,point.model_dump())
    if selected is None: fail(422,"invalid_minimum_point","Choose a valid measured pixel inside this region")
    item.geometry_json={**item.geometry_json,"minimum_selection":selected}; db.commit()
    return {"minimum_selection":selected,"automatic_minimum_c":item.stats_json["minimum_c"]}

@app.delete("/api/regions/{region_id}/minimum")
def reset_region_minimum(region_id:int,db:Session=Depends(get_db)):
    item=db.get(Region,region_id)
    if not item: fail(404,"region_not_found","Region not found")
    item.geometry_json={**item.geometry_json,"minimum_selection":None}; db.commit()
    return {"minimum_selection":None}

@app.get("/api/analyses/{analysis_id}/regions")
def list_regions(analysis_id:int,db:Session=Depends(get_db)):
    return [region_dict(r) for r in db.scalars(select(Region).where(Region.analysis_id==analysis_id)).all()]

@app.delete("/api/regions/{region_id}",status_code=204)
def delete_region(region_id:int,db:Session=Depends(get_db)):
    item=db.get(Region,region_id)
    if not item: fail(404,"region_not_found","Region not found")
    db.delete(item); db.commit()

@app.post("/api/regions/{region_id}/hotspots")
def find_hotspots(region_id:int,body:HotspotRequest,db:Session=Depends(get_db)):
    region=db.get(Region,region_id)
    if not region: fail(404,"region_not_found","Region not found")
    analysis=db.get(AnalysisVersion,region.analysis_id); matrix,valid=load_matrix(analysis); roi=region_mask(matrix.shape,region.kind,region.geometry_json["points"])
    found=hotspots(matrix,valid,roi,body.threshold_c,body.minimum_area); reference=None
    if body.reference_region_id:
        ref=db.get(Region,body.reference_region_id)
        if not ref or ref.analysis_id!=analysis.id: fail(422,"invalid_reference","Reference region must belong to this analysis")
        reference=ref.stats_json["mean_c"]
    delta=region.stats_json["maximum_c"]-reference if reference is not None else None
    return {"actual_maximum_c":region.stats_json["maximum_c"],"threshold_c":body.threshold_c,"reference_mean_c":reference,"delta_t_c":delta,"delta_definition":"region maximum − reference region mean" if reference is not None else None,"candidates":found,"interpretation":"Thermal observations requiring inspection review; not automatic fault diagnoses."}

@app.get("/api/analyses/{analysis_id}/matrix.csv")
def matrix_csv(analysis_id:int,db:Session=Depends(get_db)):
    item=db.get(AnalysisVersion,analysis_id); matrix,valid=load_matrix(item)
    def rows():
        yield "# units=Celsius; rows=y; columns=x; invalid=blank\r\n"; yield ","+",".join(map(str,range(matrix.shape[1])))+"\r\n"
        for y,row in enumerate(matrix): yield str(y)+","+",".join(f"{v:.6f}" if valid[y,x] else "" for x,v in enumerate(row))+"\r\n"
    return StreamingResponse(rows(),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="analysis-{analysis_id}-matrix.csv"'})
