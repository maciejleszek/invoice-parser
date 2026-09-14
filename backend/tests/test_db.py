"""
Testy warstwy db.py (SQLAlchemy) na świeżym pliku SQLite per test — sprawdza
cały cykl życia projektu/faktury/pozycji przez publiczne funkcje modułu.
Postgres (ścieżka używana na Vercelu) nie jest tu pokryty automatycznie —
wymaga żywej bazy — ale zapytania są identyczne (patrz komentarz w db.py),
więc to i tak łapie większość możliwych regresji w SQL/parametryzacji.
"""
import importlib

import pytest


@pytest.fixture
def db_module(tmp_path, monkeypatch):
    """Świeży moduł db.py związany z pustym plikiem SQLite (jeszcze bez
    wywołanego init_db()) — DATABASE_URL musi być pusty (inaczej wygrałby
    realny Postgres z env), DB_PATH wskazuje na plik tymczasowy;
    importlib.reload, bo `engine` w db.py jest budowany raz przy imporcie
    modułu."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    from app import db as mod
    importlib.reload(mod)
    return mod


@pytest.fixture
def db(db_module):
    """Jak db_module, ale ze schematem już założonym — wariant używany
    przez większość testów, które nie sprawdzają samej migracji."""
    db_module.init_db()
    return db_module


def test_full_project_lifecycle(db):
    project = db.create_project("  Test SA  ")
    assert project["name"] == "Test SA"  # przycięte białe znaki

    header = {
        "plik": "x.pdf", "typ": "tim", "numer_faktury": "FV1", "sprzedawca": "ACME",
        "data_faktury": "2026-01-20", "termin_platnosci": None, "numer_zamowienia": None,
        "waluta": "PLN", "razem_netto": 100.0, "razem_brutto": 123.0,
    }
    item = {
        "lp": 1, "opis": "Śruba", "indeks": "IDX1", "pkwiu": "", "ilosc": 2, "jm": "szt",
        "cena_netto": 50.0, "wartosc_netto": 100.0, "stawka_vat": "23%", "kwota_vat": 23.0,
        "wartosc_brutto": 123.0, "kategoria_klucz": "mechanika", "kategoria_nazwa": "Mechanika",
        "pewnosc": 80, "zrodlo_dopasowania": "słownik", "powod": "test",
    }
    invoice_id = db.save_invoice(project["id"], header, [item], content_hash="abc123")

    projects = db.list_projects()
    assert len(projects) == 1
    assert projects[0]["invoice_count"] == 1
    assert projects[0]["item_count"] == 1  # regresja: JOIN do items nie może zawyżać invoice_count

    invoices = db.list_invoices(project["id"])
    assert len(invoices) == 1
    assert invoices[0]["rok"] == 2026

    items = db.list_items(project_id=project["id"])
    assert len(items) == 1
    assert items[0]["manual_override"] == 0  # domyślna wartość z server_default
    item_id = items[0]["id"]

    # Duplikaty: po hashu i po (numer, sprzedawca)
    assert db.find_duplicate(project["id"], "abc123", None, None) is not None
    assert db.find_duplicate(project["id"], "inny-hash", "FV1", "ACME") is not None
    assert db.find_duplicate(project["id"], "inny-hash", "FV-INNY", "KTOS-INNY") is None

    # Lata
    assert db.distinct_years(project["id"]) == [2026]

    # Ręczna korekta kategorii + ochrona przed recategorize
    assert db.set_item_category(item_id, "transport", "Transport") is True
    items = db.list_items(project_id=project["id"])
    assert items[0]["kategoria_klucz"] == "transport"
    assert items[0]["manual_override"] == 1
    assert db.items_for_recategorize(project["id"]) == []  # pominięty (ręczny)
    assert len(db.items_for_recategorize(project["id"], force=True)) == 1  # force widzi wszystko

    changed = db.bulk_update_item_categories([{
        "id": item_id, "kategoria_klucz": "elektryka", "kategoria_nazwa": "Elektryka",
        "pewnosc": 90, "zrodlo_dopasowania": "słownik", "powod": "auto",
    }])
    assert changed == 1
    assert db.list_items(project_id=project["id"])[0]["kategoria_klucz"] == "elektryka"

    # Edycja nagłówka faktury (rok przeliczony na nowo z nowej daty)
    updated = db.update_invoice(project["id"], invoice_id, {
        "numer_faktury": "FV1-FIXED", "data_faktury": "2027-03-01",
    })
    assert updated["numer_faktury"] == "FV1-FIXED"
    assert updated["rok"] == 2027

    # Eksport (kopia zapasowa) widzi wszystko
    dump = db.export_all()
    assert len(dump["projects"]) == 1
    assert len(dump["invoices"]) == 1
    assert len(dump["items"]) == 1

    # Kasowanie kaskadowe: usunięcie faktury zabiera jej pozycje
    assert db.delete_invoice(project["id"], invoice_id) is True
    assert db.list_items(project_id=project["id"]) == []

    assert db.delete_project(project["id"]) is True
    assert db.list_projects() == []


def test_delete_project_cascades_to_invoices_and_items(db):
    project = db.create_project("Kaskada")
    db.save_invoice(project["id"], {
        "plik": "a.pdf", "typ": "tim", "numer_faktury": "A1", "sprzedawca": "X",
        "data_faktury": "2026-01-01", "termin_platnosci": None, "numer_zamowienia": None,
        "waluta": "PLN", "razem_netto": 1.0, "razem_brutto": 1.23,
    }, [{
        "lp": 1, "opis": "coś", "indeks": None, "pkwiu": None, "ilosc": 1, "jm": "szt",
        "cena_netto": 1.0, "wartosc_netto": 1.0, "stawka_vat": "23%", "kwota_vat": 0.23,
        "wartosc_brutto": 1.23, "kategoria_klucz": "inne", "kategoria_nazwa": "Inne",
        "pewnosc": 10, "zrodlo_dopasowania": "brak", "powod": "brak",
    }])

    assert db.delete_project(project["id"]) is True
    assert db.list_items(project_id=project["id"]) == []
    assert db.get_project(project["id"]) is None


def test_migration_is_idempotent_on_fresh_database(db):
    """init_db() musi dać się wywołać wielokrotnie bez błędu (np. przy
    kolejnych startach appki na tej samej bazie)."""
    db.init_db()
    db.init_db()
    project = db.create_project("Po migracji")
    assert project["id"]


def test_migration_upgrades_pre_existing_database_without_losing_data(db_module):
    """To jest dokładnie sytuacja użytkownika: plik SQLite założony PRZED
    dodaniem content_hash/manual_override (stary raw-sqlite3 schemat, bez
    SQLAlchemy). init_db() musi dograć brakujące kolumny bez ruszania
    istniejących danych.

    Regresja: pierwsza wersja migracji używała "ALTER TABLE ... ADD COLUMN
    IF NOT EXISTS", które SQLite (nawet 3.50, wbrew początkowemu założeniu)
    odrzuca składniowo — błąd był po cichu łykany przez `except Exception:
    pass`, więc migracja nigdy się nie wykonywała, a każde zapytanie o
    manual_override/content_hash by się wysypywało."""
    import sqlite3

    conn = sqlite3.connect(db_module.DB_PATH)
    conn.executescript("""
        CREATE TABLE projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE invoices (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            plik TEXT, typ TEXT, numer_faktury TEXT, sprzedawca TEXT, data_faktury TEXT,
            rok INTEGER, termin_platnosci TEXT, numer_zamowienia TEXT, waluta TEXT,
            razem_netto REAL, razem_brutto REAL, uploaded_at TEXT
        );
        CREATE TABLE items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id TEXT NOT NULL REFERENCES invoices(id),
            lp INTEGER, opis TEXT, indeks TEXT, pkwiu TEXT, ilosc REAL, jm TEXT,
            cena_netto REAL, wartosc_netto REAL, stawka_vat TEXT, kwota_vat REAL,
            wartosc_brutto REAL, kategoria_klucz TEXT, kategoria_nazwa TEXT,
            pewnosc INTEGER, zrodlo_dopasowania TEXT, powod TEXT
        );
    """)
    conn.execute("INSERT INTO projects VALUES ('p1','Real Project','2026-01-01T00:00:00')")
    conn.execute(
        "INSERT INTO invoices (id, project_id, plik, numer_faktury, sprzedawca, uploaded_at) "
        "VALUES ('i1','p1','real.pdf','FV999','Real Vendor','2026-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO items (invoice_id, lp, opis, kategoria_klucz, kategoria_nazwa, pewnosc) "
        "VALUES ('i1', 1, 'Real item', 'elektryka', 'Elektryka', 90)"
    )
    conn.commit()
    conn.close()

    db_module.init_db()

    items = db_module.list_items(project_id="p1")
    assert items[0]["opis"] == "Real item"          # dane nienaruszone
    assert items[0]["kategoria_klucz"] == "elektryka"
    assert items[0]["manual_override"] == 0          # nowa kolumna, wartość domyślna

    invoices = db_module.list_invoices("p1")
    assert invoices[0]["numer_faktury"] == "FV999"
    assert invoices[0]["content_hash"] is None       # nowa kolumna, NULL dla starych wierszy

    # Bez wyjątku przy ponownym uruchomieniu (kolejny restart appki)
    db_module.init_db()
