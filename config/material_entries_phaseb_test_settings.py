"""Phase B disposable tests: independent of deployment settings and .env."""
from .material_entries_local_settings import *
DATABASES = {"default": {**DATABASES["default"], "TEST": {"NAME": "test_microcom_material_entries_phaseb_20261104"}}}
