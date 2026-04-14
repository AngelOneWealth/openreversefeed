"""Django settings for the openreversefeed reference app.

This is a demo-only configuration. It deliberately skips auth and uses SQLite
for Django's session / admin tables so the demo runs without any external
state beyond the library's Postgres. The library itself uses Postgres via
SQLAlchemy — Django never talks to that database directly.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "dev-only-change-me-before-production-use-1234567890"
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"]

# Applications
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "django.contrib.messages",
    "uploads.apps.UploadsConfig",
    "corrections.apps.CorrectionsConfig",
    "dashboard.apps.DashboardConfig",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "reference_app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "reference_app.wsgi.application"

# SQLite for Django's own internal tables (sessions, auth if enabled later).
# NOT the library database. The library uses Postgres via SQLAlchemy.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "django_internal.sqlite3",
    }
}

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Where uploaded feed files land on disk. The worker polls this directory.
UPLOAD_DIR = Path(os.environ.get("OFR_UPLOAD_DIR", BASE_DIR / "uploaded_files"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Library database URL (also read by openreversefeed.settings directly).
OFR_DATABASE_URL = os.environ.get(
    "OFR_DATABASE_URL", "postgresql+psycopg://ofr:ofr@localhost:5438/ofr"
)
os.environ.setdefault("OFR_DATABASE_URL", OFR_DATABASE_URL)
