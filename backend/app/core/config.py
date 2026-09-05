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


settings = Settings()
