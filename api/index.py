"""
api/index.py — punkt wejścia dla Vercel Serverless Functions (Python).

Vercel buduje ten plik z @vercel/python i oczekuje w nim zmiennej `app`
(ASGI) — resztę (routing /api/* -> ta funkcja) ustawia vercel.json w
korzeniu repo. Cała prawdziwa logika żyje w backend/app/ — ten plik tylko
dokłada backend/ do sys.path (Vercel spakowuje cały katalog repo razem z
funkcją, ale bez tego importy typu `from . import db` w backend/app/api.py
by nie zadziałały) i re-eksportuje gotowy obiekt FastAPI.

Uwaga o trwałości danych: backend na Vercelu MUSI mieć ustawioną zmienną
środowiskową DATABASE_URL wskazującą na Postgres (np. z Vercel Postgres
albo Neon) — system plików funkcji serverless jest efemeryczny, więc
domyślny plik SQLite (używany lokalnie/w Dockerze) nie przetrwałby między
wywołaniami. Patrz backend/app/db.py.
"""

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.api import app  # noqa: E402  (import po ustawieniu sys.path)

__all__ = ["app"]
