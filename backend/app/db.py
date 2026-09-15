"""
db.py — trwałe przechowywanie projektów i skategoryzowanych faktur.

Dwa środowiska, jeden kod:
  • Docker/lokalnie (domyślnie): SQLite w pliku pod DB_PATH — dokładnie jak
    dotychczas, zero zmian w zachowaniu ani w danych już zapisanych.
  • Vercel (serverless): system plików jest efemeryczny, więc SQLite by nie
    przetrwał między wywołaniami. Ustawienie zmiennej środowiskowej
    DATABASE_URL (np. z dodatku Vercel Postgres/Neon) przełącza na Postgres
    — ten sam kod, ta sama logika, inny silnik pod spodem (SQLAlchemy).

Jedna faktura należy do jednego projektu. Pozycje faktury są zapisywane
z tymi samymi polami co odpowiedź /api/process (patrz categorize_files),
żeby komponenty frontendu (tabela pozycji, wykres kategorii) mogły być
używane bez zmian zarówno dla trybu "szybkiej analizy", jak i projektów.
"""

import os
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    text,
)
from sqlalchemy.pool import NullPool

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "app.db"),
)


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        # Vercel ustawia VERCEL=1 w każdym środowisku uruchomieniowym funkcji
        # (patrz System Environment Variables w ich dokumentacji). Bez
        # DATABASE_URL próba os.makedirs() na system plików funkcji i tak
        # wywali się z kryptycznym "Read-only file system" — lepiej od razu
        # dać jasny komunikat, co skonfigurować, zamiast czekać na to.
        if os.environ.get("VERCEL"):
            raise RuntimeError(
                "Brak zmiennej środowiskowej DATABASE_URL. Na Vercelu system "
                "plików jest tylko do odczytu, więc SQLite (domyślne lokalnie/"
                "w Dockerze) tu nie zadziała — dodaj bazę Postgres w zakładce "
                "Storage projektu i ustaw DATABASE_URL w Environment Variables "
                "(patrz README, sekcja 'Deployment na Vercel')."
            )
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        return f"sqlite:///{DB_PATH}"
    # Neon/Vercel Postgres/Heroku-style URLs zwykle zaczynają się od
    # "postgres://", którego SQLAlchemy 2.x już nie akceptuje jako alias
    # dla "postgresql://" — trzeba znormalizować, i wybrać sterownik psycopg.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,  # krótkie, niezależne połączenia — bezpieczne też
    # w serverless, gdzie proces (i pula połączeń) może zniknąć w każdej chwili.
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
)

if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")


metadata = MetaData()

projects = Table(
    "projects", metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("created_at", String, nullable=False),
)

invoices = Table(
    "invoices", metadata,
    Column("id", String, primary_key=True),
    Column("project_id", String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
    Column("plik", String),
    Column("typ", String),
    Column("numer_faktury", String),
    Column("sprzedawca", String),
    Column("data_faktury", String),
    Column("rok", Integer),
    Column("termin_platnosci", String),
    Column("numer_zamowienia", String),
    Column("waluta", String),
    Column("razem_netto", Float),
    Column("razem_brutto", Float),
    Column("content_hash", String),
    Column("uploaded_at", String),
)

items = Table(
    "items", metadata,
    Column("id", Integer, primary_key=True),
    Column("invoice_id", String, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
    Column("lp", Integer),
    Column("opis", String),
    Column("indeks", String),
    Column("pkwiu", String),
    Column("ilosc", Float),
    Column("jm", String),
    Column("cena_netto", Float),
    Column("wartosc_netto", Float),
    Column("stawka_vat", String),
    Column("kwota_vat", Float),
    Column("wartosc_brutto", Float),
    Column("kategoria_klucz", String),
    Column("kategoria_nazwa", String),
    Column("pewnosc", Integer),
    Column("zrodlo_dopasowania", String),
    Column("powod", String),
    Column("manual_override", Integer, nullable=False, server_default="0"),
)

# Kolumny dodane po pierwszym wydaniu schematu — metadata.create_all() tworzy
# tylko brakujące TABELE, nie kolumny w już istniejącej (starszej) tabeli, więc
# na bazach założonych przed tą zmianą trzeba je dograć ręcznie. Działa
# identycznie w SQLite (3.35+) i Postgresie — oba wspierają IF NOT EXISTS.
_COLUMN_MIGRATIONS = [
    ("invoices", "content_hash", "VARCHAR"),
    ("items", "manual_override", "INTEGER NOT NULL DEFAULT 0"),
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


def _row(row) -> dict:
    return dict(row._mapping)


def init_db():
    metadata.create_all(engine)
    with engine.begin() as conn:
        for table, col, coltype in _COLUMN_MIGRATIONS:
            if engine.dialect.name == "postgresql":
                # Postgres wspiera IF NOT EXISTS wprost — idempotentne bez
                # połykania nieznanych błędów.
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}"))
            else:
                # SQLite (nawet najnowsze) NIE wspiera ADD COLUMN IF NOT
                # EXISTS — jedyny sposób sprawdzenia to złapać błąd "kolumna
                # już istnieje" przy próbie dodania jej po raz drugi.
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"))
                except Exception:
                    pass


# ── Projekty ─────────────────────────────────────────────────────────

def create_project(name: str) -> dict:
    project = {"id": uuid.uuid4().hex, "name": name.strip(), "created_at": _now()}
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO projects (id, name, created_at) VALUES (:id, :name, :created_at)"
        ), project)
    return project


def list_projects() -> list[dict]:
    with engine.begin() as conn:
        rows = conn.execute(text(
            """
            SELECT p.id, p.name, p.created_at,
                   COUNT(DISTINCT i.id)  AS invoice_count,
                   COUNT(DISTINCT it.id) AS item_count
            FROM projects p
            LEFT JOIN invoices i ON i.project_id = p.id
            LEFT JOIN items it   ON it.invoice_id = i.id
            GROUP BY p.id, p.name, p.created_at
            ORDER BY p.created_at DESC
            """
        )).fetchall()
        return [_row(r) for r in rows]


def get_project(project_id: str) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT * FROM projects WHERE id = :id"), {"id": project_id}
        ).fetchone()
        return _row(row) if row else None


def delete_project(project_id: str) -> bool:
    with engine.begin() as conn:
        cur = conn.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
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


def save_invoice(project_id: str, header: dict, items_: list[dict],
                  content_hash: str | None = None) -> str:
    invoice_id = uuid.uuid4().hex
    rok = extract_year(header.get("data_faktury"))
    invoice_row = {
        "id": invoice_id, "project_id": project_id, "rok": rok,
        "uploaded_at": _now(), "content_hash": content_hash,
        **{f: header.get(f) for f in _INVOICE_FIELDS},
    }
    cols = ["id", "project_id", "rok", "uploaded_at", "content_hash", *_INVOICE_FIELDS]
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO invoices ({', '.join(cols)}) "
            f"VALUES ({', '.join(':' + c for c in cols)})"
        ), invoice_row)
        if items_:
            item_cols = ["invoice_id", *_ITEM_FIELDS]
            item_rows = [
                {"invoice_id": invoice_id, **{f: it.get(f) for f in _ITEM_FIELDS}}
                for it in items_
            ]
            conn.execute(text(
                f"INSERT INTO items ({', '.join(item_cols)}) "
                f"VALUES ({', '.join(':' + c for c in item_cols)})"
            ), item_rows)
    return invoice_id


def list_invoices(project_id: str) -> list[dict]:
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT * FROM invoices WHERE project_id = :pid ORDER BY uploaded_at DESC"
        ), {"pid": project_id}).fetchall()
        return [_row(r) for r in rows]


def delete_invoice(project_id: str, invoice_id: str) -> bool:
    with engine.begin() as conn:
        cur = conn.execute(text(
            "DELETE FROM invoices WHERE id = :iid AND project_id = :pid"
        ), {"iid": invoice_id, "pid": project_id})
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
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    with engine.begin() as conn:
        cur = conn.execute(
            text(f"UPDATE invoices SET {set_clause} WHERE id = :iid AND project_id = :pid"),
            {**updates, "iid": invoice_id, "pid": project_id},
        )
        if cur.rowcount == 0:
            return None
    return get_invoice(project_id, invoice_id)


def get_invoice(project_id: str, invoice_id: str) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT * FROM invoices WHERE id = :iid AND project_id = :pid"
        ), {"iid": invoice_id, "pid": project_id}).fetchone()
        return _row(row) if row else None


def find_duplicate(project_id: str, content_hash: str | None,
                    numer_faktury: str | None, sprzedawca: str | None) -> dict | None:
    """Szuka w projekcie faktury, która wygląda na tę samą co podana:
    albo bajt w bajt ten sam plik (content_hash), albo ten sam numer
    faktury u tego samego sprzedawcy (np. ta sama faktura zeskanowana
    drugi raz jako inny plik PDF)."""
    with engine.begin() as conn:
        if content_hash:
            row = conn.execute(text(
                "SELECT * FROM invoices WHERE project_id = :pid AND content_hash = :hash"
            ), {"pid": project_id, "hash": content_hash}).fetchone()
            if row:
                return _row(row)
        if numer_faktury and numer_faktury.strip() and sprzedawca and sprzedawca.strip():
            row = conn.execute(text(
                """SELECT * FROM invoices WHERE project_id = :pid
                   AND lower(trim(numer_faktury)) = lower(trim(:numer))
                   AND lower(trim(sprzedawca)) = lower(trim(:sprzedawca))"""
            ), {"pid": project_id, "numer": numer_faktury, "sprzedawca": sprzedawca}).fetchone()
            if row:
                return _row(row)
    return None


def list_items(project_id: str | None = None, year: int | None = None) -> list[dict]:
    """Zwraca pozycje (z dołączonymi polami faktury) w kształcie identycznym
    jak odpowiedź /api/process, żeby frontend mógł użyć tych samych
    komponentów (ItemsTable, CategoryChart) co w trybie szybkiej analizy."""
    conditions = []
    params: dict = {}
    if project_id:
        conditions.append("i.project_id = :pid")
        params["pid"] = project_id
    if year:
        conditions.append("i.rok = :rok")
        params["rok"] = year
    where = (" AND " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT it.*, i.numer_faktury, i.sprzedawca, i.data_faktury, i.waluta
        FROM items it
        JOIN invoices i ON i.id = it.invoice_id
        WHERE 1=1{where}
        ORDER BY i.uploaded_at DESC, it.lp ASC
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).fetchall()
        return [_row(r) for r in rows]


def distinct_years(project_id: str | None = None) -> list[int]:
    sql = "SELECT DISTINCT rok FROM invoices WHERE rok IS NOT NULL"
    params: dict = {}
    if project_id:
        sql += " AND project_id = :pid"
        params["pid"] = project_id
    sql += " ORDER BY rok DESC"
    with engine.begin() as conn:
        return [r[0] for r in conn.execute(text(sql), params).fetchall()]


# ── Ręczna korekta kategorii / ponowna kategoryzacja ────────────────

def set_item_category(item_id: int, kategoria_klucz: str, kategoria_nazwa: str) -> bool:
    """Ręczna poprawka kategorii jednej pozycji z GUI. Oznaczana jako
    manual_override, żeby recategorize_items() jej nie nadpisał."""
    with engine.begin() as conn:
        cur = conn.execute(text(
            """UPDATE items SET kategoria_klucz = :klucz, kategoria_nazwa = :nazwa,
                   pewnosc = 100, zrodlo_dopasowania = 'ręcznie',
                   powod = 'poprawka ręczna', manual_override = 1
               WHERE id = :id"""
        ), {"klucz": kategoria_klucz, "nazwa": kategoria_nazwa, "id": item_id})
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
        WHERE i.project_id = :pid
    """
    params: dict = {"pid": project_id}
    if invoice_id:
        sql += " AND i.id = :iid"
        params["iid"] = invoice_id
    if not force:
        sql += " AND it.manual_override = 0"
    with engine.begin() as conn:
        return [_row(r) for r in conn.execute(text(sql), params).fetchall()]


def bulk_update_item_categories(updates: list[dict]) -> int:
    """updates: [{id, kategoria_klucz, kategoria_nazwa, pewnosc,
    zrodlo_dopasowania, powod}, ...] — wynik automatycznej kategoryzacji,
    nie oznacza manual_override (to zostaje 0)."""
    if not updates:
        return 0
    with engine.begin() as conn:
        conn.execute(text(
            """UPDATE items SET kategoria_klucz = :kategoria_klucz,
                   kategoria_nazwa = :kategoria_nazwa, pewnosc = :pewnosc,
                   zrodlo_dopasowania = :zrodlo_dopasowania, powod = :powod
               WHERE id = :id"""
        ), updates)
    return len(updates)


# ── Kopia zapasowa ───────────────────────────────────────────────────

def export_all() -> dict:
    """Zrzut całej bazy (wszystkie projekty/faktury/pozycje) jako zwykłe
    słowniki/listy — działa identycznie niezależnie od silnika pod spodem
    (SQLite czy Postgres), w przeciwieństwie do kopiowania pliku .db, które
    ma sens tylko dla SQLite."""
    with engine.begin() as conn:
        projects_ = [_row(r) for r in conn.execute(text("SELECT * FROM projects")).fetchall()]
        invoices_ = [_row(r) for r in conn.execute(text("SELECT * FROM invoices")).fetchall()]
        items_ = [_row(r) for r in conn.execute(text("SELECT * FROM items")).fetchall()]
    return {
        "exported_at": _now(),
        "projects": projects_,
        "invoices": invoices_,
        "items": items_,
    }
