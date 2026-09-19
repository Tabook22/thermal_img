"""Run once from the trusted server console after `alembic upgrade head`."""
import argparse
from pathlib import Path
import secrets
import shutil
from sqlalchemy import select, update
from .auth import AccountInput, hash_password
from .config import settings
from .database import SessionLocal
from .models import Inspection, Tower, User

def bootstrap(username: str, credential_file: Path):
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)) is not None:
            raise RuntimeError("Accounts already exist. Use the administrator's Users page.")
        password=secrets.token_urlsafe(24)
        data=AccountInput(username=username, display_name="Workspace Administrator", role="admin", password=password)
        user=User(username=data.username,display_name=data.display_name,role="admin",is_active=True,
                  is_deleted=False,must_change_password=True,password_hash=hash_password(password))
        db.add(user); db.flush()
        db.execute(update(Inspection).where(Inspection.owner_id.is_(None)).values(owner_id=user.id))
        db.execute(update(Tower).where(Tower.owner_id.is_(None)).values(owner_id=user.id))
        old_library=(settings.storage_root/"knowledge").resolve()
        destination=(settings.storage_root/"workspaces"/str(user.id)/"knowledge").resolve()
        root=settings.storage_root.resolve()
        if root not in old_library.parents or root not in destination.parents:
            raise RuntimeError("Unexpected library storage path")
        if old_library.exists():
            if destination.exists(): raise RuntimeError("Administrator library destination already exists")
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(old_library,destination)
        credential_file.parent.mkdir(parents=True,exist_ok=True)
        with credential_file.open("x",encoding="utf-8") as output:
            credential_file.chmod(0o600)
            output.write(f"Thermal application administrator\nUsername: {user.username}\nTemporary password: {password}\nSign in and choose a new password before using the workspace.\n")
        db.commit()
        print("Administrator created; existing inspections and library assigned. Credentials saved to the protected file.")

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--username",default="nasser")
    parser.add_argument("--credential-file",type=Path,required=True)
    arguments=parser.parse_args()
    bootstrap(arguments.username,arguments.credential_file)
