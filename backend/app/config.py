"""Application configuration."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WMN_DATA_PATH = PROJECT_ROOT / "data" / "wmn-data.json"


def resolve_project_path(value: str | Path) -> Path:
    """Resolve a configured path relative to the project root when needed."""
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "CyberMirror"
    app_version: str = "2.4.0"
    app_release_name: str = "Correlation"
    host: str = "127.0.0.1"
    port: int = 8787
    debug: bool = False
    api_auth_enabled: bool = True
    api_token: str | None = None
    encryption_enabled: bool = True
    encryption_key: str | None = None

    database_path: Path = PROJECT_ROOT / "data" / "cybermirror.sqlite3"
    exports_dir: Path = PROJECT_ROOT / "exports"
    logs_dir: Path = PROJECT_ROOT / "data" / "logs"
    cache_dir: Path = PROJECT_ROOT / "data" / "cache"

    serpapi_key: str | None = None  # Reserved for a future optional provider.
    hibp_api_key: str | None = None
    scan_timeout_seconds: int = 900

    # Optional external WhatsMyName dataset. The default is project-local and
    # intentionally contains no machine-specific path.
    wmn_data_path: Path = DEFAULT_WMN_DATA_PATH
    username_scan_limit: int = 600
    web_search_max_queries: int = 30
    web_search_results_per_query: int = 8
    cache_ttl_seconds: int = 3600
    playwright_enabled: bool = True

    schedule_enabled: bool = False
    schedule_interval_hours: int = 168
    ahmia_max_results: int = 10
    ahmia_max_queries: int = 3

    @field_validator("wmn_data_path", mode="before")
    @classmethod
    def _resolve_wmn_data_path(cls, value):
        if value in (None, ""):
            return DEFAULT_WMN_DATA_PATH
        return resolve_project_path(value)


settings = Settings()
