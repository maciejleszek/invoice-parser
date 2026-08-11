"""
api.py — REST API dla frontendu React.

Endpointy:
  POST /api/process      – przyjmuje wiele plików PDF, zwraca skategoryzowane dane JSON
  GET  /api/download/{id} – pobiera wygenerowany plik Excel dla danej sesji

Uruchomienie (dev):
  uvicorn app.api:app --reload --port 8000
"""

import io
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from .categorizer import build_workbook, categorize_files

app = FastAPI(title="Invoice Categorizer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# job_id -> openpyxl Workbook (bytes wygenerowane na żądanie pobrania)
_JOBS: dict[str, Workbook] = {}


@app.post("/api/process")
async def process_invoices(
    files: list[UploadFile] = File(...),
    use_web: bool = Form(False),
):
    if not files:
        raise HTTPException(400, "Nie przesłano żadnych plików.")

    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for f in files:
            if not f.filename.lower().endswith(".pdf"):
                continue
            dest = Path(tmp) / f.filename
            dest.write_bytes(await f.read())
            paths.append(str(dest))

        if not paths:
            raise HTTPException(400, "Żaden z przesłanych plików nie jest plikiem PDF.")

        headers, items = categorize_files(paths, use_web=use_web, log=lambda *_: None)

    job_id = uuid.uuid4().hex
    _JOBS[job_id] = build_workbook(headers, items)

    return {
        "job_id": job_id,
        "invoices": headers,
        "items": items,
    }


@app.get("/api/download/{job_id}")
async def download_workbook(job_id: str):
    wb = _JOBS.get(job_id)
    if wb is None:
        raise HTTPException(404, "Nie znaleziono wyników dla podanego identyfikatora.")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="kategoryzacja_{job_id[:8]}.xlsx"'},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}
