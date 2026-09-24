from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_TITLE: str = "FME Chat API"
    APP_VERSION: str = "0.1.0"

    # Lưu ý: KHÔNG dùng port 8001 — trùng với Hiring MCP Server chạy SSE
    # (mặc định MCP_PORT=8001 trong .env.example gốc của dự án).
    APP_PORT: int = 8000
    APP_HOST: str = "0.0.0.0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
