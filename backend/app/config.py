"""Application configuration."""



from pathlib import Path



from pydantic_settings import BaseSettings, SettingsConfigDict



PROJECT_ROOT = Path(__file__).resolve().parents[2]





class Settings(BaseSettings):

    model_config = SettingsConfigDict(

        env_file=PROJECT_ROOT / ".env",

        env_file_encoding="utf-8",

        extra="ignore",

    )



    app_name: str = "CyberMirror"

    app_version: str = "2.1.0"

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



    serpapi_key: str | None = None  # reserved — engine uses DDGS

    hibp_api_key: str | None = None

    scan_timeout_seconds: int = 900



    wmn_data_path: Path = Path(r"C:\استخبارات\OSINT_tools\WhatsMyName\wmn-data.json")

    username_scan_limit: int = 600

    web_search_max_queries: int = 30

    web_search_results_per_query: int = 8

    cache_ttl_seconds: int = 3600

    playwright_enabled: bool = True



    schedule_enabled: bool = False

    schedule_interval_hours: int = 168





settings = Settings()

