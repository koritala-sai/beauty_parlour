import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()  # reads variables from a .env file if present


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "3306")
    DB_NAME = os.environ.get("DB_NAME", "beauty_parlour")

    # quote_plus escapes special characters (like @, #, %) so a password
    # such as "mysql@1001" doesn't break the connection URL below
    _DB_PASSWORD_ENCODED = quote_plus(DB_PASSWORD)

    # PyMySQL is used as the MySQL driver (pure Python, easy to install, no
    # extra system dependencies compared to mysqlclient)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"mysql+pymysql://{DB_USER}:{_DB_PASSWORD_ENCODED}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Email (Gmail SMTP). MAIL_PASSWORD must be a 16-character Gmail
    # "App Password", not your normal Gmail login password.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", MAIL_USERNAME)

    # Studio's WhatsApp number for the "share your review" link.
    # Format: country code + number, NO +, spaces, or dashes.
    # Example: 919000000000 for +91 90000 00000
    STUDIO_WHATSAPP_NUMBER = os.environ.get("STUDIO_WHATSAPP_NUMBER", "9059302359")


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True