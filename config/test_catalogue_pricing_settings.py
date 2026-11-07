"""Synthetic PostgreSQL pricing tests; independent of deployment settings/.env.

Use only with the disposable loopback PostgreSQL cluster on port 55439.
"""
from .test_stock_review_settings import *

MIGRATION_MODULES = {}
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": "postgres", "USER": "postgres", "HOST": "127.0.0.1", "PORT": "55439",
    "TEST": {"NAME": "test_microcom_catalogue_pricing_20261105_b"},
}}
MIDDLEWARE = ["django.middleware.csrf.CsrfViewMiddleware", *MIDDLEWARE]
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = BASE_DIR / "local_artifacts" / "catalogue_pricing_media"
TEST_RUNNER = "config.catalogue_pricing_test_runner.CataloguePricingRunner"
