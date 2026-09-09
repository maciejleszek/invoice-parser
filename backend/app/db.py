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
    content_hash      TEXT,
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
    powod               TEXT,
    manual_override     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_invoices_project ON invoices(project_id);
CREATE INDEX IF NOT EXISTS idx_invoices_rok      ON invoices(rok);
CREATE INDEX IF NOT EXISTS idx_items_invoice     ON items(invoice_id);
"""

# Kolumny dodane po pierwszym wydaniu schematu — CREATE TABLE IF NOT EXISTS
# nie doda ich do już istniejącej (starszej) bazy, więc trzeba dograć ALTER
# TABLE. Błąd "duplicate column" (baza założona już z tą kolumną) ignorujemy.
_MIGRATIONS = [
    "ALTER TABLE invoices ADD COLUMN content_hash TEXT",
    "ALTER TABLE items ADD COLUMN manual_override INTEGER NOT NULL DEFAULT 0",
]


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
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # kolumna/zmiana już istnieje


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
                   COUNT(DISTINCT i.id)                           AS invoice_count,
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


def save_invoice(project_id: str, header: dict, items: list[dict],
                  content_hash: str | None = None) -> str:
    invoice_id = uuid.uuid4().hex
    rok = extract_year(header.get("data_faktury"))
    with _connect() as conn:
        conn.execute(
            f"""INSERT INTO invoices (id, project_id, rok, uploaded_at, content_hash, {", ".join(_INVOICE_FIELDS)})
                VALUES (?, ?, ?, ?, ?, {", ".join("?" for _ in _INVOICE_FIELDS)})""",
            [invoice_id, project_id, rok, _now(), content_hash] + [header.get(f) for f in _INVOICE_FIELDS],
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


_EDITABLE_INVOICE_FIELDS = set(_INVOICE_FIELDS)


def update_invoice(project_id: str, invoice_id: str, fields: dict) -> dict | None:
    """Nadpisuje wybrane pola nagłówka faktury (poprawka ręczna błędu
    parsera — zły numer, sprzedawca, data...). Tylko pola z _INVOICE_FIELDS
    są edytowalne; rok jest przeliczany na nowo, jeśli zmienia się data."""
    updates = {k: v for k, v in fields.items() if k in _EDITABLE_INVOICE_FIELDS}
    if not updates:
        return get_invoice(project_id, invoice_id)
    if "data_faktury" in updates:
        updates["rok"] = extract_year(updates["data_faktury"])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE invoices SET {set_clause} WHERE id = ? AND project_id = ?",
            [*updates.values(), invoice_id, project_id],
        )
        if cur.rowcount == 0:
            return None
    return get_invoice(project_id, invoice_id)


def get_invoice(project_id: str, invoice_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM invoices WHERE id = ? AND project_id = ?", (invoice_id, project_id)
        ).fetchone()
        return dict(row) if row else None


def find_duplicate(project_id: str, content_hash: str | None,
                    numer_faktury: str | None, sprzedawca: str | None) -> dict | None:
    """Szuka w projekcie faktury, która wygląda na tę samą co podana:
    albo bajt w bajt ten sam plik (content_hash), albo ten sam numer
    faktury u tego samego sprzedawcy (np. ta sama faktura zeskanowana
    drugi raz jako inny plik PDF)."""
    with _connect() as conn:
        if content_hash:
            row = conn.execute(
                "SELECT * FROM invoices WHERE project_id = ? AND content_hash = ?",
                (project_id, content_hash),
            ).fetchone()
            if row:
                return dict(row)
        if numer_faktury and numer_faktury.strip() and sprzedawca and sprzedawca.strip():
            row = conn.execute(
                """SELECT * FROM invoices WHERE project_id = ?
                   AND lower(trim(numer_faktury)) = lower(trim(?))
                   AND lower(trim(sprzedawca)) = lower(trim(?))""",
                (project_id, numer_faktury, sprzedawca),
            ).fetchone()
            if row:
                return dict(row)
    return None


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


# ── Ręczna korekta kategorii / ponowna kategoryzacja ────────────────

def set_item_category(item_id: int, kategoria_klucz: str, kategoria_nazwa: str) -> bool:
    """Ręczna poprawka kategorii jednej pozycji z GUI. Oznaczana jako
    manual_override, żeby recategorize_items() jej nie nadpisał."""
    with _connect() as conn:
        cur = conn.execute(
            """UPDATE items SET kategoria_klucz = ?, kategoria_nazwa = ?,
                   pewnosc = 100, zrodlo_dopasowania = 'ręcznie',
                   powod = 'poprawka ręczna', manual_override = 1
               WHERE id = ?""",
            (kategoria_klucz, kategoria_nazwa, item_id),
        )
        return cur.rowcount > 0


def items_for_recategorize(project_id: str, invoice_id: str | None = None,
                            force: bool = False) -> list[dict]:
    """Pozycje kwalifikujące się do ponownego przeliczenia kategorii —
    domyślnie z pominięciem tych poprawionych ręcznie (chyba że force=True,
    świadome nadpisanie także ręcznych poprawek)."""
    sql = """
        SELECT it.id, it.opis, it.indeks, it.pkwiu
        FROM items it
        JOIN invoices i ON i.id = it.invoice_id
        WHERE i.project_id = ?
    """
    params: list = [project_id]
    if invoice_id:
        sql += " AND i.id = ?"
        params.append(invoice_id)
    if not force:
        sql += " AND it.manual_override = 0"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def bulk_update_item_categories(updates: list[dict]) -> int:
    """updates: [{id, kategoria_klucz, kategoria_nazwa, pewnosc,
    zrodlo_dopasowania, powod}, ...] — wynik automatycznej kategoryzacji,
    nie oznacza manual_override (to zostaje 0)."""
    if not updates:
        return 0
    with _connect() as conn:
        conn.executemany(
            """UPDATE items SET kategoria_klucz = :kategoria_klucz,
                   kategoria_nazwa = :kategoria_nazwa, pewnosc = :pewnosc,
                   zrodlo_dopasowania = :zrodlo_dopasowania, powod = :powod
               WHERE id = :id""",
            updates,
        )
    return len(updates)


# ── Kopia zapasowa ───────────────────────────────────────────────────

def backup_to_file(dest_path: str) -> None:
    """Bezpieczna kopia bazy przez SQLite backup API — działa nawet przy
    równoległych zapisach (w przeciwieństwie do zwykłego shutil.copy pliku
    .db, który mógłby złapać bazę w trakcie zapisu)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as src, sqlite3.connect(dest_path) as dst:
        src.backup(dst)
