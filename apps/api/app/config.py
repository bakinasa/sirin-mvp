"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_url: str = "http://localhost:8080"
    api_url: str = "http://localhost:8080/api"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "aistudio"
    postgres_user: str = "aistudio"
    postgres_password: str = "aistudio"

    redis_url: str = "redis://localhost:6379/0"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "aistudio"
    minio_public_url: str = "http://localhost:9000"
    minio_secure: bool = False

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    encryption_key: str = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="

    default_provider: str = "openai_compatible"
    default_model: str = ""

    openrouter_api_key: str = ""
    hubris_api_key: str = ""
    tsarrouter_api_key: str = ""
    openai_api_key: str = ""
    yandex_api_key: str = ""
    gigachat_api_key: str = ""

    bootstrap_admin_email: str = "admin@aistudio.local"
    bootstrap_admin_password: str = "admin123"
    bootstrap_admin_name: str = "Admin"

    prompts_dir: str = "/prompts"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
