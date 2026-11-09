"""Disposable local PostgreSQL only. Never imports deployment settings or .env."""
from .test_stock_review_settings import *
import os
from pathlib import Path

DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
MIGRATION_MODULES = {}
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": "material_entries_local",
    "USER": "postgres",
    "TEST": {"NAME": "test_material_entries_phase1"},
    "HOST": "127.0.0.1",
    "PORT": os.environ.get("MATERIAL_ENTRIES_PG_PORT", "55439"),
}}
MIDDLEWARE = ["django.middleware.csrf.CsrfViewMiddleware", *MIDDLEWARE]
LOGIN_URL = "/login/"
STATICFILES_DIRS = [Path(__file__).resolve().parent.parent / "static"]

# Material Entries uses localized CSRF errors; other modules retain Django defaults.
CSRF_FAILURE_VIEW = "inventory.entry_i18n.csrf_failure"
