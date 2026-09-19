"""Create a new protected Compose environment file without printing secrets."""

import os
import secrets
from pathlib import Path
from urllib.parse import quote


target = Path(__file__).resolve().parent.parent / ".env"
os.umask(0o077)
database_password = secrets.token_urlsafe(36)
root_password = secrets.token_urlsafe(36)
database_url = (
    "mysql+pymysql://thermal_user:"
    f"{quote(database_password, safe='')}@db:3306/tower_thermal"
)
values = {
    "MYSQL_DATABASE": "tower_thermal",
    "MYSQL_USER": "thermal_user",
    "MYSQL_PASSWORD": database_password,
    "MYSQL_ROOT_PASSWORD": root_password,
    "DATABASE_URL": database_url,
    "STORAGE_ROOT": "/data",
    "DJI_IRP_PATH": "/opt/dji-thermal-sdk/utility/bin/linux/release_x64/dji_irp",
    "DJI_SDK_VERSION": "unavailable",
    "MAX_UPLOAD_MB": "100",
    "DECODER_TIMEOUT_SECONDS": "45",
    "DECODER_CONCURRENCY": "2",
    "CORS_ORIGINS": "https://skygreenline-lab.io",
    "OPENAI_API_KEY": "",
    "OPENAI_WEB_MODEL": "gpt-4.1-mini",
}
descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
    for name, value in values.items():
        stream.write(f"{name}={value}\n")
print(f"Created {target} with mode 600. Secrets were not displayed.")
