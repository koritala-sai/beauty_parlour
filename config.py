import os
from urllib.parse import quote_plus

from dotenv import load_dotenv


# Load variables from .env during local development.
# On Railway, variables are provided directly as environment variables.
load_dotenv()


def get_bool_env(name, default=False):
    """Convert an environment variable to a boolean safely."""
    value = os.environ.get(name)

    if value is None:
        return default

    return value.strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


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
    # Email - Gmail SMTP
    # =========================================================

    MAIL_SERVER = os.environ.get(
        "MAIL_SERVER",
        "smtp.gmail.com",
    )

    MAIL_PORT = int(
        os.environ.get("MAIL_PORT", "587")
    )

    MAIL_USE_TLS = get_bool_env(
        "MAIL_USE_TLS",
        True,
    )

    MAIL_USE_SSL = get_bool_env(
        "MAIL_USE_SSL",
        False,
    )

    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")

    # Use Gmail App Password, NOT normal Gmail password
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

    MAIL_DEFAULT_SENDER = os.environ.get(
        "MAIL_DEFAULT_SENDER",
        MAIL_USERNAME,
    )

    MAIL_TIMEOUT = int(
        os.environ.get("MAIL_TIMEOUT", "20")
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

    # Extra recommended settings
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SAMESITE = "Lax"