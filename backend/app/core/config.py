from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Application
    app_name: str = "RISK-ERA"
    app_env: str = "development"

    # Database
    database_url: str

    # JWT Authentication (optional - defaults provided for backward compatibility)
    jwt_secret_key: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # NVIDIA / Nemotron (required, no defaults - must come from environment)
    nvidia_api_key: str
    nemotron_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"

    # Demo mode — transparent flag to short-circuit Nemotron latency for live presentations
    # When true, investigator uses deterministic fallback instantly instead of calling NVIDIA API
    demo_mode: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()  # type: ignore[call-arg]  # pydantic-settings reads from env