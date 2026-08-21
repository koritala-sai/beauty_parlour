import os
from urllib.parse import quote_plus

from dotenv import load_dotenv


# Load variables from .env during local development.
# On Railway, variables are provided directly as environment variables.
load_dotenv()


class Config:

    # =========================================================
    # Security
    # =========================================================

    SECRET_KEY = os.environ.get("SECRET_KEY")

    if not SECRET_KEY:
        SECRET_KEY = "dev-secret-change-me"


    # =========================================================
    # Database
    # =========================================================

    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "3306")
    DB_NAME = os.environ.get("DB_NAME", "beauty_parlour")

    # Encode special characters in database password
    _DB_PASSWORD_ENCODED = quote_plus(DB_PASSWORD)

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        (
            f"mysql+pymysql://{DB_USER}:"
            f"{_DB_PASSWORD_ENCODED}@"
            f"{DB_HOST}:{DB_PORT}/{DB_NAME}"
        ),
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False


    # =========================================================
    # Email - Resend HTTP API
    # =========================================================

    # Railway variable: RESEND_API_KEY
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

    # Railway variable: MAIL_FROM
    # Example:
    # Glow Studio <onboarding@resend.dev>
    MAIL_FROM = os.environ.get(
        "MAIL_FROM",
        "Glow Studio <onboarding@resend.dev>",
    )


    # =========================================================
    # WhatsApp
    # =========================================================

    STUDIO_WHATSAPP_NUMBER = os.environ.get(
        "STUDIO_WHATSAPP_NUMBER",
        "9059302359",
    )


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False

    # Secure cookies for deployed HTTPS website
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True

    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SAMESITE = "Lax"