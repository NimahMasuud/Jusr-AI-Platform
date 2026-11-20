import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Jusr AI API"
    database_url: str = "postgresql+psycopg://jusr:jusr@db:5432/jusr_ai"
    secret_key: str = "change-this-development-secret"
    access_token_expire_minutes: int = 30
    cors_origins: list[str] = ["http://localhost:5173"]
    demo_mode: bool = True
    # Patient secure links (Part 2)
    patient_link_expiry_days: int = 7
    patient_link_max_attempts: int = 3
    patient_link_verify_birth_year: bool = True
    patient_link_base_url: str = "http://localhost:5173"
    patient_session_minutes: int = 30
    # Time limits, message retries and urgent-routing windows are no longer environment variables: they live in the settings store (R-23), see /api/v1/settings.
    # Background scheduler for message retries and routing deadlines. With several API workers, enable it on one
    # instance only, or disable it and run `python -m app.worker` as its own process.
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
