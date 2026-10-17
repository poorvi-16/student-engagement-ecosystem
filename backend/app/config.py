from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "PathPilot API"
    environment: str = "development"

    # Comma-separated list of allowed frontend origins (CORS)
    frontend_origin: str = "http://localhost:3000"
    # Optional regex for extra origins, e.g. Vercel preview deploys: https://student-engagement-ecosystem-.*\.vercel\.app
    frontend_origin_regex: str = ""

    database_url: str = "sqlite:///./local.db"

    anthropic_api_key: str = ""
    model_smart: str = "claude-sonnet-5-5"
    model_fast: str = "claude-haiku-5-5"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # Comma-separated emails that get the admin role on first login
    admin_emails: str = ""

    daily_llm_limit: int = 50
    monthly_llm_budget: float = 20.0

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
