"""Live Emergent preview entrypoint for the Akasha BFF (Slice 0).

The Emergent sandbox runs a single supervisor-managed FastAPI process on
port 8001 (ingress routes `/api/*` here). To avoid code duplication, this
module mounts the *canonical* `apps/api` FastAPI application so the live
preview exercises exactly the same skeleton code that ships in the `api`
container on Railway.

Nothing Akasha-specific lives here other than wiring. No database is used in
Slice 0.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load the Emergent backend .env (CORS_ORIGINS, etc.). Never read secrets here.
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# Point the skeleton manifest endpoint at the monorepo root so the live
# dashboard can render the real repository tree.
os.environ.setdefault("REPO_ROOT", "/app")

# Make the canonical BFF package importable: /app/apps/api/app/main.py
CANONICAL_API_DIR = "/app/apps/api"
if CANONICAL_API_DIR not in sys.path:
    sys.path.insert(0, CANONICAL_API_DIR)

# `app` resolves to /app/apps/api/app (the canonical BFF package).
from app.main import app  # noqa: E402  (re-exported for `uvicorn server:app`)

__all__ = ["app"]
