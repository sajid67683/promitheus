"""Central configuration, read from environment variables (and `.env` locally)."""
import os

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    pass


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw and raw.strip() else default


class Settings:
    def __init__(self) -> None:
        self.environment = os.getenv("ENVIRONMENT", "development").lower()
        # Vercel sets VERCEL_ENV to "production", "preview" or "development".
        self.vercel_env = os.getenv("VERCEL_ENV")
        self.on_vercel = bool(os.getenv("VERCEL"))

        self.gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        # Tried in order when the main model is overloaded (503) or rate-limited (429).
        self.gemini_fallback_models = [
            m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-flash-latest,gemini-flash-lite-latest").split(",") if m.strip()
        ]
        # Quick yes/no checks (is this short answer equivalent?) use a faster, cheaper model.
        self.gemini_fast_model = os.getenv("GEMINI_FAST_MODEL", "gemini-flash-lite-latest")
        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID") or None
        self.cron_secret = os.getenv("CRON_SECRET") or None

        # Password-reset emails are sent through Resend (https://resend.com) when configured.
        self.resend_api_key = os.getenv("RESEND_API_KEY") or None
        self.email_from = os.getenv("EMAIL_FROM") or None
        # Public URL used in emails; falls back to the request's own URL.
        self.app_url = (os.getenv("APP_URL") or "").rstrip("/") or None

        self.session_cookie = "promitheus_session"
        # Cache-busts CSS/JS per deployment.
        self.asset_version = (os.getenv("VERCEL_GIT_COMMIT_SHA") or os.getenv("VERCEL_DEPLOYMENT_ID") or "dev")[:12]

        self.access_token_expire_minutes = _int_env("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7)
        # Vercel rejects request bodies over 4.5 MB, so stay below that.
        self.max_upload_bytes = _int_env("MAX_UPLOAD_MB", 4) * 1024 * 1024
        self.max_lecture_chars = _int_env("MAX_LECTURE_CHARS", 150_000)
        self.daily_upload_limit = _int_env("DAILY_UPLOAD_LIMIT", 10)
        self.daily_ai_grading_limit = _int_env("DAILY_AI_GRADING_LIMIT", 200)

    @property
    def is_production(self) -> bool:
        return self.environment == "production" or self.vercel_env == "production"

    @property
    def secure_cookies(self) -> bool:
        # Local development runs on plain http.
        return self.on_vercel or self.is_production

    @property
    def email_enabled(self) -> bool:
        return bool(self.resend_api_key and self.email_from)

    @property
    def database_url(self) -> str:
        url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
        if not url:
            raise ConfigError(
                "DATABASE_URL is not set. Add it to .env locally or to the Vercel project settings."
            )
        # Some providers hand out postgres:// URLs, which SQLAlchemy 2 rejects.
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        return url

    @property
    def secret_key(self) -> str:
        key = os.getenv("SECRET_KEY", "")
        if len(key) < 32:
            raise ConfigError(
                "SECRET_KEY must be set to a random string of at least 32 characters. "
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return key

    def validate(self) -> None:
        """Fail fast at startup instead of on the first request."""
        _ = self.database_url
        _ = self.secret_key


settings = Settings()
