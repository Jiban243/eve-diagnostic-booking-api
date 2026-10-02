from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "eve_db"
    db_user: str = "eve_user"
    db_password: SecretStr

    jwt_secret: SecretStr = Field(min_length=32)
    access_token_expire_minutes: int = Field(default=60, ge=1)
    webhook_secret: SecretStr = Field(min_length=32)

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
