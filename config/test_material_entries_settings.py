
"""Isolated local PostgreSQL settings for Material Entries testing.

Never use this configuration with Supabase or production.
"""

from .test_catalogue_pricing_settings import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "microcom_material_test",
        "USER": "postgres",
        "HOST": "127.0.0.1",
        "PORT": "5432",
        "CONN_MAX_AGE": 0,
        "TEST": {
            "NAME": "test_microcom_material_entries",
        },
    }
}

TEST_RUNNER = "django.test.runner.DiscoverRunner"

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8001",
    "http://localhost:8001",
]
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

# Local isolated testing only.
DEBUG = True
