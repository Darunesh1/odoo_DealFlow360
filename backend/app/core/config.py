from typing import Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder secret shipped in .env.example. Refused in production.
INSECURE_DEFAULT_SECRET = "supersecretkeychangeinproduction123"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api"

    # Public URL of the frontend application. Used to build links inside emails.
    FRONTEND_URL: str = "http://localhost:5173"

    # Comma separated list of origins allowed to call the API from a browser.
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173,http://localhost:4173"

    # PostgreSQL Configuration
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "backend_db"

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # JWT Configuration
    JWT_SECRET_KEY: str = INSECURE_DEFAULT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Single use email token lifetimes
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    INVITE_EXPIRE_HOURS: int = 72

    # Bootstrap administrator, created on startup when missing. There is no
    # public signup, so without this nobody could ever sign in.
    FIRST_ADMIN_EMAIL: str = "admin@dealflow360.com"
    FIRST_ADMIN_PASSWORD: str = "admin12345"

    # Seeds one ready to use account per role. Development only, so a real
    # deployment never gets anything beyond the administrator above.
    SEED_DEMO_USERS: bool = True

    # A quotation untouched for this many days is flagged as stalled on the
    # deal health dashboard.
    STALLED_DEAL_DAYS: int = 7

    # How long resolving a deal-health alert buys quiet before the same problem
    # can be raised again. Its own knob rather than reusing the stall window,
    # which would silence resolved alerts for as long as the stall threshold.
    ALERT_QUIET_DAYS: int = 7

    # Upsell suggestions below this margin percentage are suppressed entirely
    # (spec A6's "minimum margin thresholds"). A rep should not have to judge
    # which suggestions are safe to accept.
    MIN_UPSELL_MARGIN_PERCENT: float = 10.0

    # SMTP Configuration (Optional)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    # STARTTLS on a submission port (587) is the common case and the default.
    # Set SMTP_SSL for an implicit-TLS port (465); the two are mutually
    # exclusive, and SSL wins if both are somehow true.
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    # For Gmail this MUST be the same address as SMTP_USER - the server
    # rewrites or rejects a From it does not own, which looks like "the email
    # silently never arrived".
    EMAILS_FROM_EMAIL: Optional[str] = "no-reply@yourdomain.com"
    EMAILS_FROM_NAME: Optional[str] = "DealFlow360"

    @model_validator(mode="after")
    def _refuse_default_secret_in_production(self) -> "Settings":
        """Fail fast rather than let a production deployment run on the sample secret."""
        if self.ENVIRONMENT == "production" and self.JWT_SECRET_KEY == INSECURE_DEFAULT_SECRET:
            raise ValueError(
                "JWT_SECRET_KEY is still set to the insecure default value. "
                "Generate one with: openssl rand -hex 32"
            )
        return self

    @property
    def cors_origins(self) -> list[str]:
        """Parses BACKEND_CORS_ORIGINS into a list of origins."""
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def async_database_url(self) -> str:
        """Constructs the async database URL using asyncpg."""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def default_database_url(self) -> str:
        """Constructs the URL to connect to the default 'postgres' database (used to check/create the main database in dev)."""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/postgres"

    @property
    def redis_url(self) -> str:
        """Constructs the Redis connection URL."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # --- Discount risk scoring -------------------------------------------- #
    # The blended score is severity + spread + exposure + breadth, each weight
    # capped so none can dominate. They add to 100.
    #
    # The old score was `8 x worst + 5 x weighted`, which on a single-line quote
    # collapsed to 13 x points_over - so 3.5 points over the ceiling was already
    # HIGH and deal size never entered it at all.
    RISK_WEIGHT_SEVERITY: float = 3.0
    RISK_WEIGHT_SPREAD: float = 2.0
    RISK_WEIGHT_EXPOSURE: float = 25.0
    RISK_WEIGHT_BREADTH: float = 10.0
    # Money given away above policy, in the base currency, at which the exposure
    # component is full marks. Tune this to the size of a typical deal.
    RISK_EXPOSURE_FULL: float = 5000.0

    # Gemini ranking for the upsell panel (Optional)
    #
    # Unset, the panel keeps its own margin-and-pairing ordering and shows no
    # rationale. It is never a hard dependency of the suggestions route: a slow
    # or failing ranking falls back to that same ordering.
    GEMINI_API_KEY: Optional[str] = None
    # flash-lite, not flash: the free tier allows 20 gemini-2.5-flash calls a
    # DAY, which a single afternoon of quoting exhausts - and the panel then
    # silently drops to its deterministic order. flash-lite is far more
    # generous, faster, and ample for ranking fifteen priced rows.
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    # Budget for the whole call. The panel sits on the critical path of a screen
    # a rep refetches on every line change, so a slow ranking is worse than no
    # ranking. Measured at ~2.5s for fifteen candidates with thinking off, so
    # this leaves headroom without letting a stall hold the panel.
    GEMINI_TIMEOUT_SECONDS: float = 6.0
    # Kill switch that does not require deleting the key.
    AI_SUGGESTIONS_ENABLED: bool = True

    @property
    def smtp_configured(self) -> bool:
        """True once all four SMTP values are present.

        Nothing else switches email delivery on: with any of them missing,
        send_email logs the message instead of dispatching it, which is how a
        verification link reaches you in development.
        """
        return all(
            [self.SMTP_HOST, self.SMTP_PORT, self.SMTP_USER, self.SMTP_PASSWORD]
        )

    @property
    def ai_ranking_configured(self) -> bool:
        """True when the upsell panel may ask Gemini to re-rank.

        One gate, like `smtp_configured`: the key being absent and the feature
        being switched off are the same thing to every caller.
        """
        return bool(self.GEMINI_API_KEY) and self.AI_SUGGESTIONS_ENABLED


settings = Settings()
