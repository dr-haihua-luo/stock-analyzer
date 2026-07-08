from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "SignalForge"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

    # Server
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    FRONTEND_PORT: int = int(os.getenv("FRONTEND_PORT", "5173"))

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Database
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "signalforge")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "signalforge_pass")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "signalforge")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Sync database URL for alembic migrations."""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)

    # OpenRouter API
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "your-api-key")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = "your-openrouter-model"
    PRIMARY_MODEL: str = "google/gemma-4-26b-a4b-it:free"
    FALLBACK_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"



    # Alpaca API
    APCA_API_KEY_ID: str = os.getenv("APCA_API_KEY_ID", "your-Alpaca-key")
    APCA_API_SECRET_KEY: str = os.getenv("APCA_API_SECRET_KEY", "your-Alpaca-secret")

    # Cache TTLs (in seconds)
    MARKET_DATA_TTL: int = 300  # 5 minutes
    SECTOR_DATA_TTL: int = 300  # 5 minutes
    STOCK_DATA_TTL: int = 60    # 1 minute

    # Analysis settings
    MAX_CONCURRENT_ANALYSES: int = 10
    ANALYSIS_TIMEOUT: int = 30  # seconds

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra environment variables like DATABASE_URL_SYNC


settings = Settings()