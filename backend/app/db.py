"""
db.py — trwałe przechowywanie projektów i skategoryzowanych faktur (SQLite).

Jedna faktura należy do jednego projektu. Pozycje faktury są zapisywane
z tymi samymi polami co odpowiedź /api/process (patrz categorize_files),
żeby komponenty frontendu (tabela pozycji, wykres kategorii) mogły być
używane bez zmian zarówno dla trybu "szybkiej analizy", jak i projektów.
"""

import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "app.db"),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    id                TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    plik              TEXT,
    typ               TEXT,
    numer_faktury     TEXT,
    sprzedawca        TEXT,
    data_faktury      TEXT,
    rok               INTEGER,
    termin_platnosci  TEXT,
    numer_zamowienia  TEXT,
    waluta            TEXT,
    razem_netto       REAL,
    razem_brutto      REAL,
    uploaded_at       TEXT
);

CREATE TABLE IF NOT EXISTS items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id          TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    lp                  INTEGER,
    opis                TEXT,
    indeks              TEXT,
    pkwiu               TEXT,
    ilosc               REAL,
    jm                  TEXT,
    cena_netto          REAL,
    wartosc_netto       REAL,
    stawka_vat          TEXT,
    kwota_vat           REAL,
    wartosc_brutto      REAL,
    kategoria_klucz     TEXT,
    kategoria_nazwa     TEXT,
    pewnosc             INTEGER,
    zrodlo_dopasowania  TEXT,
    powod               TEXT
);

CREATE INDEX IF NOT EXISTS idx_invoices_project ON invoices(project_id);
CREATE INDEX IF NOT EXISTS idx_invoices_rok      ON invoices(rok);
CREATE INDEX IF NOT EXISTS idx_items_invoice     ON items(invoice_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def extract_year(date_str: str | None) -> int | None:
    """Wyciąga rok z dowolnego formatu daty spotykanego na fakturach
    (2026-01-20 / 20.01.2026 / 11-Aug-2025 / 13 April 2026 ...) — zamiast
    parsować każdy format osobno, po prostu szuka wiarygodnego 4-cyfrowego
    roku w tekście."""
    if not date_str:
        return None
    m = re.search(r"\b(20\d{2})\b", str(date_str))
    return int(m.group(1)) if m else None


@contextmanager
def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connect() as conn:
        conn.executescript(_SCHEMA)


# ── Projekty ─────────────────────────────────────────────────────────

def create_project(name: str) -> dict:
    project = {"id": uuid.uuid4().hex, "name": name.strip(), "created_at": _now()}
    with _connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
            (project["id"], project["name"], project["created_at"]),
        )
    return project


def list_projects() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.created_at,
                   COUNT(i.id)                                   AS invoice_count,
                   COUNT(DISTINCT it.id)                          AS item_count
            FROM projects p
            LEFT JOIN invoices i ON i.project_id = p.id
            LEFT JOIN items it   ON it.invoice_id = i.id
            GROUP BY p.id
            ORDER BY p.created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_project(project_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None


def delete_project(project_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return cur.rowcount > 0


# ── Faktury / pozycje ────────────────────────────────────────────────

_INVOICE_FIELDS = [
    "plik", "typ", "numer_faktury", "sprzedawca", "data_faktury",
    "termin_platnosci", "numer_zamowienia", "waluta", "razem_netto", "razem_brutto",
]
_ITEM_FIELDS = [
    "lp", "opis", "indeks", "pkwiu", "ilosc", "jm", "cena_netto", "wartosc_netto",
    "stawka_vat", "kwota_vat", "wartosc_brutto", "kategoria_klucz", "kategoria_nazwa",
    "pewnosc", "zrodlo_dopasowania", "powod",
]


def save_invoice(project_id: str, header: dict, items: list[dict]) -> str:
    invoice_id = uuid.uuid4().hex
    rok = extract_year(header.get("data_faktury"))
    with _connect() as conn:
        conn.execute(
            f"""INSERT INTO invoices (id, project_id, rok, uploaded_at, {", ".join(_INVOICE_FIELDS)})
                VALUES (?, ?, ?, ?, {", ".join("?" for _ in _INVOICE_FIELDS)})""",
            [invoice_id, project_id, rok, _now()] + [header.get(f) for f in _INVOICE_FIELDS],
        )
        for it in items:
            conn.execute(
                f"""INSERT INTO items (invoice_id, {", ".join(_ITEM_FIELDS)})
                    VALUES (?, {", ".join("?" for _ in _ITEM_FIELDS)})""",
                [invoice_id] + [it.get(f) for f in _ITEM_FIELDS],
            )
    return invoice_id


def list_invoices(project_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM invoices WHERE project_id = ? ORDER BY uploaded_at DESC",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_invoice(project_id: str, invoice_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM invoices WHERE id = ? AND project_id = ?", (invoice_id, project_id)
        )
        return cur.rowcount > 0


def list_items(project_id: str | None = None, year: int | None = None) -> list[dict]:
    """Zwraca pozycje (z dołączonymi polami faktury) w kształcie identycznym
    jak odpowiedź /api/process, żeby frontend mógł użyć tych samych
    komponentów (ItemsTable, CategoryChart) co w trybie szybkiej analizy."""
    conditions = []
    params: list = []
    if project_id:
        conditions.append("i.project_id = ?")
        params.append(project_id)
    if year:
        conditions.append("i.rok = ?")
        params.append(year)
    where = (" AND " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT it.*, i.numer_faktury, i.sprzedawca, i.data_faktury, i.waluta
        FROM items it
        JOIN invoices i ON i.id = it.invoice_id
        WHERE 1=1{where}
        ORDER BY i.uploaded_at DESC, it.lp ASC
    """
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def distinct_years(project_id: str | None = None) -> list[int]:
    sql = "SELECT DISTINCT rok FROM invoices WHERE rok IS NOT NULL"
    params: list = []
    if project_id:
        sql += " AND project_id = ?"
        params.append(project_id)
    sql += " ORDER BY rok DESC"
    with _connect() as conn:
        return [r[0] for r in conn.execute(sql, params).fetchall()]
