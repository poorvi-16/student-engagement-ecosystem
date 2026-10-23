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

    # LLM providers, tried in order; providers without a key are skipped (see app/llm.py)
    llm_providers: str = "gemini,groq"
    gemini_api_key: str = ""
    # Comma-separated fallback lists: each model has its own free-tier quota (~5 req/min on Gemini)
    gemini_model_fast: str = "gemini-flash-lite-latest,gemini-3.5-flash"
    gemini_model_smart: str = "gemini-3.5-flash,gemini-flash-lite-latest"
    gemini_reasoning_effort: str = "minimal"  # ~2.5s vs ~6s at "low"; every listed model must accept it
    groq_api_key: str = ""
    groq_model_fast: str = "openai/gpt-oss-20b,openai/gpt-oss-120b"
    groq_model_smart: str = "openai/gpt-oss-120b,openai/gpt-oss-20b"
    groq_reasoning_effort: str = "low"  # gpt-oss supports low | medium | high
    # Optional paid provider (structured calls only)
    anthropic_api_key: str = ""
    model_smart: str = "claude-sonnet-5-5"
    model_fast: str = "claude-haiku-5-5"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # Comma-separated emails that get the admin role on first login
    admin_emails: str = ""

    nudge_ab: bool = True  # A/B test nudge copy (rules/ab.py)

    daily_llm_limit: int = 50
    monthly_llm_budget: float = 20.0

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def llm_provider_list(self) -> list[str]:
        return [x.strip().lower() for x in self.llm_providers.split(",") if x.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
