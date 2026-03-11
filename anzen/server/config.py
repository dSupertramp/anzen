from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ANZEN_",
        env_file=".env",
        extra="ignore",  # ignore env vars not used by the monitor (e.g. GEMINI_API_KEY)
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Auth
    api_key: str = ""  # Empty = no auth (dev mode)
    api_key_header: str = "X-Api-Key"

    # Database
    database_url: str = "sqlite+aiosqlite:///./anzen.db"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Retention
    events_max_age_days: int = 30
    events_max_count: int = 100_000


settings = Settings()
