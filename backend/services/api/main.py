"""Scalpel API — case-based surgical logger routes + optional patient prep routes."""

import shared.bootstrap  # noqa: F401 — load .env before other imports

from cases.server import app  # noqa: F401 — case API (primary)

# Patient prep routes (secondary flow) are registered on the same app.
from services.api import patients as _patients  # noqa: F401

_patients.register(app)


if __name__ == "__main__":
    from cases.server import main

    main()
