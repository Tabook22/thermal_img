from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

class UserSession(Base):
    __tablename__ = "user_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime)

class ActivityEvent(Base):
    __tablename__ = "activity_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(String(300))
    outcome: Mapped[str] = mapped_column(String(20), default="success")
    source: Mapped[str] = mapped_column(String(20), default="server")
    image_id: Mapped[int | None] = mapped_column(Integer, index=True)
    image_name: Mapped[str | None] = mapped_column(String(255))
    inspection_id: Mapped[int | None] = mapped_column(Integer)

class ActivityVisit(Base):
    __tablename__ = "activity_visits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_hash: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    end_reason: Mapped[str | None] = mapped_column(String(60))
    foreground_seconds: Mapped[float] = mapped_column(Float, default=0)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    page: Mapped[str] = mapped_column(String(40), default="workspace")
    image_id: Mapped[int | None] = mapped_column(Integer)
    sequence: Mapped[int] = mapped_column(Integer, default=0)

class Tower(Base):
    __tablename__ = "towers"
    __table_args__ = (UniqueConstraint("owner_id", "tower_code", name="uq_tower_owner_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    tower_code: Mapped[str] = mapped_column(String(100))
    circuit: Mapped[str | None] = mapped_column(String(100))
    verified_latitude: Mapped[float | None] = mapped_column(Float)
    verified_longitude: Mapped[float | None] = mapped_column(Float)

class Inspection(Base):
    __tablename__ = "inspections"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    tower_id: Mapped[int] = mapped_column(ForeignKey("towers.id"))
    phase: Mapped[str | None] = mapped_column(String(30))
    insulator_identifier: Mapped[str | None] = mapped_column(String(100))
    direction: Mapped[str | None] = mapped_column(String(50))
    capture_time: Mapped[datetime | None]
    inspector_notes: Mapped[str | None] = mapped_column(Text)
    ambient_conditions: Mapped[dict | None] = mapped_column(JSON)
    electrical_load: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

class ThermalImage(Base):
    __tablename__ = "thermal_images"
    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"))
    original_name: Mapped[str] = mapped_column(String(255))
    storage_name: Mapped[str] = mapped_column(String(255), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    classification: Mapped[str] = mapped_column(String(50))
    camera_model: Mapped[str | None] = mapped_column(String(100))
    camera_latitude: Mapped[float | None] = mapped_column(Float)
    camera_longitude: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

class AnalysisVersion(Base):
    __tablename__ = "analysis_versions"; __table_args__ = (UniqueConstraint("image_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("thermal_images.id"))
    version: Mapped[int]; status: Mapped[str] = mapped_column(String(20))
    sdk_version: Mapped[str | None] = mapped_column(String(50)); matrix_path: Mapped[str | None] = mapped_column(String(255))
    width: Mapped[int | None]; height: Mapped[int | None]
    parameters_json: Mapped[dict | None] = mapped_column(JSON); parameters_provenance: Mapped[dict | None] = mapped_column(JSON)
    stats_json: Mapped[dict | None] = mapped_column(JSON); warnings_json: Mapped[list | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text); processed_at: Mapped[datetime | None]

class Region(Base):
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(primary_key=True); analysis_id: Mapped[int] = mapped_column(ForeignKey("analysis_versions.id"))
    name: Mapped[str] = mapped_column(String(100)); kind: Mapped[str] = mapped_column(String(20)); geometry_json: Mapped[dict] = mapped_column(JSON)
    stats_json: Mapped[dict | None] = mapped_column(JSON); is_reference: Mapped[bool] = mapped_column(Boolean, default=False)

class HotspotObservation(Base):
    __tablename__ = "hotspot_observations"
    id: Mapped[int] = mapped_column(primary_key=True); region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"))
    threshold_c: Mapped[float]; minimum_area: Mapped[int]; peak_c: Mapped[float]; pixel_area: Mapped[int]
    location_json: Mapped[dict] = mapped_column(JSON); outline_json: Mapped[dict] = mapped_column(JSON); reviewer_notes: Mapped[str | None] = mapped_column(Text)

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True); analysis_id: Mapped[int] = mapped_column(ForeignKey("analysis_versions.id")); storage_path: Mapped[str] = mapped_column(String(255)); created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
