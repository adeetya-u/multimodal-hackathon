"""Load environment before other backend imports."""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent

backend_env = BACKEND_ROOT / ".env"
root_env = REPO_ROOT / ".env"
if backend_env.is_file():
    load_dotenv(backend_env)
elif root_env.is_file():
    load_dotenv(root_env)

# Resolve case data directory for the standalone backend repo.
_cases_dir = BACKEND_ROOT / "data" / "cases"
_raw = os.environ.get("CASE_DATA_DIR", "").strip()


def _case_dir_candidates() -> list[Path]:
    out: list[Path] = []
    if _raw:
        p = Path(_raw)
        if p.is_absolute():
            out.append(p)
        else:
            out.extend([BACKEND_ROOT / p, REPO_ROOT / p, Path.cwd() / p])
    out.append(_cases_dir)
    return out


for candidate in _case_dir_candidates():
    if candidate.is_dir() and any(candidate.iterdir()):
        os.environ["CASE_DATA_DIR"] = str(candidate.resolve())
        break
else:
    for candidate in _case_dir_candidates():
        if candidate.is_dir():
            os.environ["CASE_DATA_DIR"] = str(candidate.resolve())
            break
    else:
        os.environ.setdefault("CASE_DATA_DIR", str(_cases_dir))

_api_port = os.environ.get("SCALPEL_API_PORT", os.environ.get("SURGICAL_PORT", "3001"))
os.environ.setdefault("SURGICAL_API_URL", f"http://127.0.0.1:{_api_port}")
