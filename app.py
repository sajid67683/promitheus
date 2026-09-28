# Vercel entrypoint (Vercel looks for a FastAPI instance named `app` in app.py).
# Run locally with:  uvicorn app:app --reload
from backend.main import app  # noqa: F401
