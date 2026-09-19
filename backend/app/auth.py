"""Server-side sessions and ownership checks for every application route."""
from contextvars import ContextVar
from datetime import datetime, timedelta
import hashlib
import hmac
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import AnalysisVersion, Inspection, LoginAttempt, Region, ThermalImage, User, UserSession

COOKIE = "thermal_session"
current_user: ContextVar[User | None] = ContextVar("thermal_user", default=None)
router = APIRouter()

def error(status: int, message: str):
    raise HTTPException(status, {"message": message})

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f"pbkdf2_sha256$600000${salt}${digest}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt, expected = encoded.split("$")
        if scheme != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

# Equal-cost password checking for unknown usernames.
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))

def user_view(user: User):
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "role": user.role, "is_active": user.is_active,
            "must_change_password": user.must_change_password, "created_at": user.created_at}

def active_user() -> User:
    user = current_user.get()
    if user is None: error(401, "Sign in to your workspace")
    return user

def private_library_root():
    user = current_user.get()
    # No request context is used by local scripts and direct unit tests only.
    return settings.storage_root / "workspaces" / str(user.id) if user else settings.storage_root

def session_user(request: Request, db: Session) -> User:
    token = request.cookies.get(COOKIE, "")
    session = db.get(UserSession, hashlib.sha256(token.encode()).hexdigest()) if token else None
    user = db.get(User, session.user_id) if session and session.expires_at > datetime.utcnow() else None
    if user is None or not user.is_active or user.is_deleted:
        error(401, "Your session has ended. Please sign in.")
    return user

def check_write_request(request: Request):
    if request.method in {"GET", "HEAD", "OPTIONS"}: return
    if request.headers.get("X-Thermal-Request") != "1":
        error(403, "Invalid application request")
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in {item.strip().rstrip("/") for item in settings.cors_origins.split(",")}:
        error(403, "Request origin is not allowed")

async def authorize_request(request: Request, db: Session = Depends(get_db)):
    """Global dependency: route parameters are resolved before ownership is checked."""
    check_write_request(request)
    path = request.url.path.rstrip("/")
    if path in {"/api/health", "/api/auth/login"} or (request.method == "GET" and
            (path == "/api/settings/branding" or path.startswith("/api/settings/assets/"))):
        yield
        return
    user = session_user(request, db)
    if user.must_change_password and path not in {"/api/auth/me", "/api/auth/password", "/api/auth/logout"}:
        error(403, "Change your temporary password before opening your workspace")
    if (path.startswith("/api/admin/") or (path.startswith("/api/settings/") and request.method != "GET")) and user.role != "admin":
        error(403, "Only an administrator can manage users or application settings")
    params = request.path_params
    inspection = None
    resource = False
    if "inspection_id" in params:
        resource = True
        inspection = db.get(Inspection, params["inspection_id"])
    elif "image_id" in params:
        resource = True
        image = db.get(ThermalImage, params["image_id"])
        inspection = db.get(Inspection, image.inspection_id) if image else None
    elif "analysis_id" in params or "region_id" in params:
        resource = True
        region = db.get(Region, params["region_id"]) if "region_id" in params else None
        analysis_id = region.analysis_id if region else params.get("analysis_id")
        analysis = db.get(AnalysisVersion, analysis_id) if analysis_id else None
        image = db.get(ThermalImage, analysis.image_id) if analysis else None
        inspection = db.get(Inspection, image.inspection_id) if image else None
    # Administration grants account management, never implicit access to another workspace.
    if resource and (inspection is None or inspection.owner_id != user.id):
        error(404, "Item not found in your workspace")
    token = current_user.set(user)
    try:
        yield
    finally:
        current_user.reset(token)

class Login(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

class AccountInput(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    role: Literal["user", "admin"] = "user"
    is_active: bool = True
    password: str | None = Field(default=None, min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value): return value.lower()

    @field_validator("display_name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip(): raise ValueError("Enter a display name")
        return value.strip()

class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

def issue_session(user: User, response: Response, db: Session):
    token = secrets.token_urlsafe(32)
    db.execute(delete(UserSession).where(UserSession.expires_at <= datetime.utcnow()))
    db.add(UserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                       expires_at=datetime.utcnow() + timedelta(hours=settings.session_hours)))
    db.commit()
    response.set_cookie(COOKIE, token, max_age=settings.session_hours * 3600, httponly=True,
                        secure=settings.session_cookie_secure, samesite="strict", path=settings.session_cookie_path)

@router.post("/api/auth/login")
def login(body: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    username = body.username.strip().lower()
    now = datetime.utcnow()
    # Rate limit both account and direct client address; never trust a client-supplied forwarding header.
    keys = [hashlib.sha256(value.encode()).hexdigest() for value in ("user:"+username, "ip:"+(request.client.host if request.client else "unknown"))]
    for key, limit in zip(keys, (10, 100)):
        attempt = db.get(LoginAttempt, key)
        if attempt and attempt.window_start > now - timedelta(minutes=15) and attempt.attempts >= limit:
            error(429, "Too many sign-in attempts. Please wait 15 minutes.")
    for key in keys:
        attempt = db.get(LoginAttempt, key)
        if not attempt: db.add(LoginAttempt(key=key, attempts=1, window_start=now))
        elif attempt.window_start <= now - timedelta(minutes=15): attempt.attempts=1; attempt.window_start=now
        else: attempt.attempts += 1
    db.commit()
    user = db.scalar(select(User).where(User.username == username))
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not valid or not user or not user.is_active or user.is_deleted:
        error(401, "Username or password is incorrect")
    db.execute(delete(LoginAttempt).where(LoginAttempt.key == keys[0]))
    previous = request.cookies.get(COOKIE)
    if previous: db.execute(delete(UserSession).where(UserSession.token_hash == hashlib.sha256(previous.encode()).hexdigest()))
    issue_session(user, response, db)
    return user_view(user)

@router.get("/api/auth/me")
def me(): return user_view(active_user())

@router.post("/api/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token_hash = hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest()
    db.execute(delete(UserSession).where(UserSession.token_hash == token_hash)); db.commit()
    response.delete_cookie(COOKIE, path=settings.session_cookie_path)
    return {"signed_out": True}

@router.post("/api/auth/password")
def change_password(body: PasswordChange, response: Response, db: Session = Depends(get_db)):
    user = active_user()
    if not verify_password(body.current_password, user.password_hash): error(400, "Current password is incorrect")
    if body.current_password == body.new_password: error(400, "Choose a different password")
    user.password_hash = hash_password(body.new_password); user.must_change_password = False
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    issue_session(user, response, db)
    return user_view(user)

@router.get("/api/admin/users")
def list_users(db: Session = Depends(get_db)):
    return [user_view(user) for user in db.scalars(select(User).where(User.is_deleted == False).order_by(User.username)).all()]

def save_account(db: Session):
    try: db.commit()
    except IntegrityError:
        db.rollback(); error(409, "This username is already in use. Choose another.")

@router.post("/api/admin/users", status_code=201)
def create_user(body: AccountInput, db: Session = Depends(get_db)):
    if not body.password: error(422, "Enter a temporary password of at least 12 characters")
    user = User(**body.model_dump(exclude={"password"}), password_hash=hash_password(body.password), must_change_password=True)
    db.add(user); save_account(db)
    return user_view(user)

@router.put("/api/admin/users/{user_id}")
def edit_user(user_id: int, body: AccountInput, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or user.is_deleted: error(404, "User not found")
    if user.id == active_user().id and (body.role != "admin" or not body.is_active or body.password):
        error(409, "Use Change password for your account. You cannot disable or demote yourself.")
    for key, value in body.model_dump(exclude={"password"}).items(): setattr(user, key, value)
    if body.password: user.password_hash=hash_password(body.password); user.must_change_password=True
    if user.id != active_user().id:
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    save_account(db)
    return user_view(user)

@router.delete("/api/admin/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or user.is_deleted: error(404, "User not found")
    if user.id == active_user().id: error(409, "You cannot delete your own administrator account")
    # Retain ownership records to avoid transferring or accidentally erasing inspection evidence.
    user.is_deleted=True; user.is_active=False; user.password_hash=hash_password(secrets.token_urlsafe(48))
    db.execute(delete(UserSession).where(UserSession.user_id == user.id)); db.commit()
    return {"deleted": True, "workspace_retained": True}
