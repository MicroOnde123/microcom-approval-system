"""Standalone SQLite regression settings: never imports production settings/.env.

These tests exercise application behaviour, not PostgreSQL locking/SQL guards.
No migrations or external database connections are used.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = "isolated-stock-review-regression-only"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "accounts", "requests_app", "workflows", "core", "inventory", "invoicing",
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
MIGRATION_MODULES = {app.rsplit(".", 1)[-1]: None for app in INSTALLED_APPS}
AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ROOT_URLCONF = "config.urls"
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "requests_app.context_processors.pending_approval_count",
    ]},
}]
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("fr", "Français")]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "/static/"
MEDIA_URL = "/media/"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
ADMINISTRATION_REPORT_REQUEST_TYPE_CODE = "AUTORISATION_GENERAL"
MATERIAL_RETURN_NOTE_UI_ENABLED = False

CSRF_FAILURE_VIEW = "inventory.entry_i18n.csrf_failure"