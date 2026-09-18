from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_ROOT / ".env", override=True)

class Settings(BaseSettings):
    database_url: str = "sqlite:///./thermal.db"
    storage_root: Path = Path("./storage")
    dji_irp_path: Path | None = None
    dji_sdk_version: str = "unavailable"
    max_upload_mb: int = 100
    decoder_timeout_seconds: int = 45
    decoder_concurrency: int = 2
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    openai_api_key: str | None = None
    openai_web_model: str = "gpt-4.1-mini"
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

settings = Settings()

