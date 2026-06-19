"""Shared filesystem paths for Scalpel backend services."""

from shared.bootstrap import BACKEND_ROOT

DATA_DIR = BACKEND_ROOT / "data"
PATIENTS_DIR = DATA_DIR / "patients"
CASES_DIR = DATA_DIR / "cases"
DB_PATH = DATA_DIR / "sqlite_database" / "library.db"
TEXTBOOKS_DIR = DATA_DIR / "textbooks"
