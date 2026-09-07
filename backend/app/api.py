"""
api.py — REST API dla frontendu React.

Dwa tryby pracy:
  • Szybka analiza (bezstanowa): POST /api/process + GET /api/download/{job_id}
    — nic nie jest zapisywane, wynik żyje tylko w pamięci procesu.
  • Projekty (trwałe, SQLite): utwórz projekt, wgrywaj do niego faktury,
    przeglądaj/filtruj pozycje i kategorie per projekt oraz globalnie
    (np. rozbicie kosztów za dany rok).

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
from pydantic import BaseModel

from . import db
from .categorizer import build_workbook, categorize_files

app = FastAPI(title="Invoice Categorizer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    db.init_db()


# ══════════════════════════════════════════════════════════════
#  SZYBKA ANALIZA (bezstanowa)
# ══════════════════════════════════════════════════════════════

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
    return _xlsx_response(wb, f"kategoryzacja_{job_id[:8]}.xlsx")


def _xlsx_response(wb: Workbook, filename: str) -> StreamingResponse:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ══════════════════════════════════════════════════════════════
#  PROJEKTY (trwałe)
# ══════════════════════════════════════════════════════════════

class ProjectCreate(BaseModel):
    name: str


@app.post("/api/projects")
def create_project(body: ProjectCreate):
    if not body.name or not body.name.strip():
        raise HTTPException(400, "Nazwa projektu nie może być pusta.")
    return db.create_project(body.name)


@app.get("/api/projects")
def list_projects():
    return db.list_projects()


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Nie znaleziono projektu.")
    project["invoices"] = db.list_invoices(project_id)
    project["years"] = db.distinct_years(project_id)
    return project


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    if not db.delete_project(project_id):
        raise HTTPException(404, "Nie znaleziono projektu.")
    return {"ok": True}


@app.post("/api/projects/{project_id}/invoices")
async def add_invoices_to_project(
    project_id: str,
    files: list[UploadFile] = File(...),
    use_web: bool = Form(False),
):
    if not db.get_project(project_id):
        raise HTTPException(404, "Nie znaleziono projektu.")
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

        # Jeden plik na wywołanie categorize_files — batchowanie zwraca płaską
        # listę pozycji ze wszystkich faktur naraz, bez informacji, która
        # pozycja należy do której faktury (dopasowanie po numerze faktury
        # zawiodłoby, gdyby dwie wgrane faktury miały ten sam numer).
        for path in paths:
            headers, items = categorize_files([path], use_web=use_web, log=lambda *_: None)
            if headers:
                db.save_invoice(project_id, headers[0], items)

    return {
        "invoices": db.list_invoices(project_id),
        "items": db.list_items(project_id=project_id),
    }


@app.delete("/api/projects/{project_id}/invoices/{invoice_id}")
def delete_invoice(project_id: str, invoice_id: str):
    if not db.delete_invoice(project_id, invoice_id):
        raise HTTPException(404, "Nie znaleziono faktury w tym projekcie.")
    return {"ok": True}


@app.get("/api/projects/{project_id}/download")
def download_project_workbook(project_id: str, year: int | None = None):
    if not db.get_project(project_id):
        raise HTTPException(404, "Nie znaleziono projektu.")
    invoices = db.list_invoices(project_id)
    if year:
        invoices = [i for i in invoices if i.get("rok") == year]
    items = db.list_items(project_id=project_id, year=year)
    wb = build_workbook(invoices, items)
    suffix = f"_{year}" if year else ""
    return _xlsx_response(wb, f"projekt_{project_id[:8]}{suffix}.xlsx")


# ══════════════════════════════════════════════════════════════
#  POZYCJE / KATEGORIE — widok globalny i per projekt
# ══════════════════════════════════════════════════════════════

@app.get("/api/items")
def list_items(project_id: str | None = None, year: int | None = None):
    """Pozycje (globalnie albo dla jednego projektu), opcjonalnie
    filtrowane po roku faktury — używane do wykresu 'koszty per kategoria'
    i tabeli pozycji zarówno w widoku projektu, jak i w globalnym dashboardzie."""
    return db.list_items(project_id=project_id, year=year)


@app.get("/api/years")
def list_years(project_id: str | None = None):
    return db.distinct_years(project_id=project_id)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
