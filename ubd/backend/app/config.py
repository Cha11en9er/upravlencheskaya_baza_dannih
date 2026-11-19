"""Конфигурация приложения (UBD_ переменные окружения / ubd/backend/.env)."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # ubd/backend


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_prefix="UBD_", extra="ignore")

    app_name: str = "УБД — Управленческая база данных"
    # По умолчанию SQLite; для PostgreSQL:
    # UBD_DB_URL=postgresql+psycopg://ubd_app:<пароль>@127.0.0.1:5432/ubd
    db_url: str = f"sqlite:///{(BASE_DIR / 'ubd.db').as_posix()}"
    secret_key: str = "dev-secret-change-me"
    token_expire_hours: int = 12
    admin_email: str = "admin@ubd.local"
    admin_password: str = "admin123"


settings = Settings()
