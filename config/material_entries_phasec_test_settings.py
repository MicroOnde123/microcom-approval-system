"""Phase C synthetic PostgreSQL tests. Never imports deployment settings or .env."""
from .material_entries_local_settings import *
DATABASES = {"default": {**DATABASES["default"], "TEST": {"NAME": "test_microcom_material_entries_phasec_20261104"}}}
