"""Create a new protected Compose environment file without printing secrets."""

import os
from pathlib import Path


target = Path(__file__).resolve().parent.parent / ".env"
os.umask(0o077)
values = {
    "DATABASE_URL": "sqlite:////data/thermal.db",
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
