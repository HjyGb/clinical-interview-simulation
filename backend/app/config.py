"""Application configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings

# Locate .env relative to this file: backend/app/config.py → ../../.env
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model_pro: str = "qwen-plus"
    llm_model_lite: str = "qwen-turbo"

    # Database
    database_url: str = f"sqlite:///{_ENV_FILE.parent / 'data' / 'app.db'}"

    # Auth
    secret_key: str = "change-me"

    # App
    app_name: str = "Clinical Interview Simulation"
    debug: bool = True

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8"}


settings = Settings()
