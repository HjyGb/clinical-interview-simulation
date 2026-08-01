"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model_pro: str = "qwen3.7-max"
    llm_model_lite: str = "qwen3.7-flash"

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Auth
    secret_key: str = "change-me"

    # App
    app_name: str = "Clinical Interview Simulation"
    debug: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
