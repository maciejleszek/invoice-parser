"""
api.py — REST API dla frontendu React.

Dwa tryby pracy:
  • Szybka analiza (bezstanowa): POST /api/process + GET /api/download/{job_id}
    — nic nie jest zapisywane, wynik żyje tylko w pamięci procesu.
  • Projekty (trwałe — SQLite lokalnie/Docker, Postgres na Vercelu, patrz
    db.py): utwórz projekt, wgrywaj do niego faktury, przeglądaj/filtruj
    pozycje i kategorie per projekt oraz globalnie (np. rozbicie kosztów
    za dany rok).

Uruchomienie (dev):
  uvicorn app.api:app --reload --port 8000
"""

import hashlib
import io
import json
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel

from . import db
from .categorizer import KATEGORIE, build_workbook, categorize_files, kategoryzuj

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


def _invoice_key(header: dict) -> tuple[str, str] | None:
    """Klucz (numer faktury, sprzedawca) znormalizowany do porównań —
    None jeśli któregoś z pól brakuje (nie ma sensu dopasowywać po pustym)."""
    numer = (header.get("numer_faktury") or "").strip().lower()
    sprzedawca = (header.get("sprzedawca") or "").strip().lower()
    return (numer, sprzedawca) if numer and sprzedawca else None


async def _save_uploads(tmp: str, files: list[UploadFile]) -> list[tuple[str, str, str]]:
    """Zapisuje przesłane PDF-y do katalogu tymczasowego. Zwraca listę
    (ścieżka, nazwa_pliku, sha256_zawartości) — hash służy do wykrywania,
    czy ten sam plik nie został wgrany więcej niż raz."""
    out = []
    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            continue
        content = await f.read()
        dest = Path(tmp) / f.filename
        dest.write_bytes(content)
        out.append((str(dest), f.filename, hashlib.sha256(content).hexdigest()))
    return out


@app.post("/api/process")
async def process_invoices(
    files: list[UploadFile] = File(...),
    use_web: bool = Form(False),
):
    if not files:
        raise HTTPException(400, "Nie przesłano żadnych plików.")

    with tempfile.TemporaryDirectory() as tmp:
        entries = await _save_uploads(tmp, files)
        if not entries:
            raise HTTPException(400, "Żaden z przesłanych plików nie jest plikiem PDF.")

        headers, items = categorize_files(
            [path for path, _, _ in entries], use_web=use_web, log=lambda *_: None
        )

    # Tu nic nie jest trwale zapisywane, więc duplikat w obrębie tej samej
    # paczki jest tylko ostrzeżeniem informacyjnym — nie blokujemy wyniku.
    hash_by_name = {name: h for _, name, h in entries}
    seen_hash: dict[str, str] = {}
    seen_key: dict[tuple[str, str], str] = {}
    duplicate_warnings = []
    for header in headers:
        fname = header.get("plik")
        file_hash = hash_by_name.get(fname)
        key = _invoice_key(header)
        if file_hash and file_hash in seen_hash:
            duplicate_warnings.append({
                "plik": fname, "matches_plik": seen_hash[file_hash],
                "reason": "identical_file",
            })
        elif key and key in seen_key:
            duplicate_warnings.append({
                "plik": fname, "matches_plik": seen_key[key],
                "numer_faktury": header.get("numer_faktury"),
                "sprzedawca": header.get("sprzedawca"),
                "reason": "same_invoice_number",
            })
        else:
            if file_hash:
                seen_hash[file_hash] = fname
            if key:
                seen_key[key] = fname

    job_id = uuid.uuid4().hex
    _JOBS[job_id] = build_workbook(headers, items)

    return {
        "job_id": job_id,
        "invoices": headers,
        "items": items,
        "duplicate_warnings": duplicate_warnings,
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
    kierownik: str | None = None


@app.post("/api/projects")
def create_project(body: ProjectCreate):
    if not body.name or not body.name.strip():
        raise HTTPException(400, "Nazwa projektu nie może być pusta.")
    return db.create_project(body.name, kierownik=body.kierownik)


@app.get("/api/projects")
def list_projects():
    return db.list_projects()


class ProjectUpdate(BaseModel):
    name: str | None = None
    kierownik: str | None = None


@app.patch("/api/projects/{project_id}")
def edit_project(project_id: str, body: ProjectUpdate):
    """Edycja nazwy/kierownika już istniejącego projektu — przydatne do
    dopisania kierownika projektom założonym zanim to pole istniało."""
    fields = body.model_dump(exclude_unset=True)
    updated = db.update_project(project_id, fields)
    if not updated:
        raise HTTPException(404, "Nie znaleziono projektu.")
    return updated


@app.get("/api/kierownicy")
def list_kierownicy():
    return db.distinct_kierownicy()


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

    skipped = []
    with tempfile.TemporaryDirectory() as tmp:
        entries = await _save_uploads(tmp, files)
        if not entries:
            raise HTTPException(400, "Żaden z przesłanych plików nie jest plikiem PDF.")

        # Jeden plik na wywołanie categorize_files — batchowanie zwraca płaską
        # listę pozycji ze wszystkich faktur naraz, bez informacji, która
        # pozycja należy do której faktury (dopasowanie po numerze faktury
        # zawiodłoby, gdyby dwie wgrane faktury miały ten sam numer).
        # Zapisujemy od razu po sprawdzeniu duplikatu, więc kolejne pliki z
        # tej samej paczki też są sprawdzane względem tego, co już trafiło
        # do bazy — bez osobnej logiki na duplikaty "w obrębie tej paczki".
        for path, filename, content_hash in entries:
            headers, items = categorize_files([path], use_web=use_web, log=lambda *_: None)
            if not headers:
                continue
            header = headers[0]
            dup = db.find_duplicate(
                project_id, content_hash, header.get("numer_faktury"), header.get("sprzedawca")
            )
            if dup:
                skipped.append({
                    "plik": filename,
                    "numer_faktury": header.get("numer_faktury"),
                    "sprzedawca": header.get("sprzedawca"),
                    "matches_plik": dup.get("plik"),
                    "reason": "identical_file" if dup.get("content_hash") == content_hash
                              else "same_invoice_number",
                })
                continue
            db.save_invoice(project_id, header, items, content_hash=content_hash)

    return {
        "invoices": db.list_invoices(project_id),
        "items": db.list_items(project_id=project_id),
        "skipped_duplicates": skipped,
    }


@app.delete("/api/projects/{project_id}/invoices/{invoice_id}")
def delete_invoice(project_id: str, invoice_id: str):
    if not db.delete_invoice(project_id, invoice_id):
        raise HTTPException(404, "Nie znaleziono faktury w tym projekcie.")
    return {"ok": True}


class InvoiceUpdate(BaseModel):
    numer_faktury: str | None = None
    sprzedawca: str | None = None
    data_faktury: str | None = None
    termin_platnosci: str | None = None
    numer_zamowienia: str | None = None
    waluta: str | None = None
    razem_netto: float | None = None
    razem_brutto: float | None = None


@app.patch("/api/projects/{project_id}/invoices/{invoice_id}")
def edit_invoice(project_id: str, invoice_id: str, body: InvoiceUpdate):
    """Ręczna poprawka nagłówka faktury — parser czasem nie trafi idealnie
    (np. złapie etykietę zamiast wartości), a bez tego jedyną naprawą była
    zmiana kodu i ponowne wgranie pliku."""
    # tylko pola faktycznie przesłane przez klienta (nie None-z-braku-wpisania)
    fields = body.model_dump(exclude_unset=True)
    updated = db.update_invoice(project_id, invoice_id, fields)
    if not updated:
        raise HTTPException(404, "Nie znaleziono faktury w tym projekcie.")
    return updated


class ItemCategoryUpdate(BaseModel):
    kategoria_klucz: str


@app.patch("/api/items/{item_id}")
def edit_item_category(item_id: int, body: ItemCategoryUpdate):
    """Ręczna korekta kategorii jednej pozycji z GUI. Oznaczana jako
    manual_override, więc 'Przelicz kategorie ponownie' jej nie nadpisze."""
    nazwa = KATEGORIE.get(body.kategoria_klucz)
    if not nazwa:
        raise HTTPException(400, f"Nieznana kategoria: {body.kategoria_klucz}")
    if not db.set_item_category(item_id, body.kategoria_klucz, nazwa):
        raise HTTPException(404, "Nie znaleziono pozycji.")
    return {"ok": True, "kategoria_klucz": body.kategoria_klucz, "kategoria_nazwa": nazwa}


@app.post("/api/projects/{project_id}/recategorize")
def recategorize_project(project_id: str, invoice_id: str | None = None,
                          use_web: bool = False, force: bool = False):
    """Przelicza kategorie już zapisanych pozycji (np. po rozszerzeniu
    słownika słów kluczowych) bez konieczności usuwania i ponownego
    wgrywania faktur. Domyślnie omija pozycje poprawione ręcznie
    (manual_override) — force=True nadpisuje też te."""
    if not db.get_project(project_id):
        raise HTTPException(404, "Nie znaleziono projektu.")
    items = db.items_for_recategorize(project_id, invoice_id=invoice_id, force=force)
    all_items = db.items_for_recategorize(project_id, invoice_id=invoice_id, force=True)
    updates = []
    for it in items:
        kat = kategoryzuj(it.get("opis", ""), it.get("indeks", ""), it.get("pkwiu", ""),
                           use_web=use_web)
        updates.append({
            "id": it["id"],
            "kategoria_klucz": kat["kategoria_klucz"],
            "kategoria_nazwa": kat["kategoria_nazwa"],
            "pewnosc": kat["pewnosc"],
            "zrodlo_dopasowania": kat["zrodlo_dopasowania"],
            "powod": kat["powod"],
        })
    changed = db.bulk_update_item_categories(updates)
    return {"changed": changed, "skipped_manual": len(all_items) - len(items)}


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
def list_items(project_id: str | None = None, year: int | None = None,
               kierownik: str | None = None):
    """Pozycje (globalnie albo dla jednego projektu), opcjonalnie
    filtrowane po roku faktury i/lub kierowniku projektu — używane do
    wykresu 'koszty per kategoria' i tabeli pozycji zarówno w widoku
    projektu, jak i w globalnym dashboardzie."""
    return db.list_items(project_id=project_id, year=year, kierownik=kierownik)


@app.get("/api/years")
def list_years(project_id: str | None = None):
    return db.distinct_years(project_id=project_id)


# ══════════════════════════════════════════════════════════════
#  KOPIA ZAPASOWA
# ══════════════════════════════════════════════════════════════

@app.get("/api/backup")
def download_backup():
    """Cała baza (wszystkie projekty/faktury/pozycje) jako plik .json do
    pobrania — jedyna kopia danych żyje w bazie (wolumen Dockera albo
    Postgres na Vercelu), więc to najprostsza asekuracja przed utratą
    dysku/bazy. JSON zamiast kopii pliku .db, bo działa identycznie
    niezależnie od silnika (SQLite lokalnie, Postgres na Vercelu)."""
    dump = db.export_all()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    buf = io.BytesIO(json.dumps(dump, ensure_ascii=False, indent=2).encode("utf-8"))
    return StreamingResponse(
        buf,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="kategoryzacja_backup_{stamp}.json"'},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}
