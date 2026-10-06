"""
Testy dla ai_import.py — ścieżki importu faktur czytanych przez Claude
Code zamiast regexowego parsera (patrz docs/AI_KATEGORYZACJA.md). Ten
moduł nic nie "czyta" sam z siebie — testy skupiają się na walidacji
wejścia i zapisie do bazy, czyli na tym, co faktycznie może się zepsuć.
"""
import importlib

import pytest


@pytest.fixture
def db_module(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    from app import db as mod
    importlib.reload(mod)
    mod.init_db()
    return mod


@pytest.fixture
def ai_import(db_module):
    from app import ai_import as mod
    importlib.reload(mod)
    return mod


@pytest.fixture
def project(db_module):
    return db_module.create_project("Test AI Import")


@pytest.fixture
def fake_pdf(tmp_path):
    path = tmp_path / "faktura.pdf"
    path.write_bytes(b"%PDF-1.4 fake content for hashing, not a real PDF\n")
    return path


def _valid_entry(plik, **header_overrides):
    header = {
        "numer_faktury": "FV1", "sprzedawca": "Acme Sp. z o.o.", "data_faktury": "2026-01-01",
        "termin_platnosci": None, "numer_zamowienia": None, "waluta": "PLN",
        "razem_netto": 100.0, "razem_brutto": 123.0,
    }
    header.update(header_overrides)
    return {
        "plik": str(plik),
        "header": header,
        "items": [
            {"opis": "Montaż instalacji", "kategoria_klucz": "uslugi_podwykonawcow",
             "wartosc_brutto": 123.0},
        ],
    }


class TestValidateEntry:
    def test_missing_plik(self, ai_import):
        errors = ai_import._validate_entry({})
        assert any("plik" in e for e in errors)

    def test_file_does_not_exist(self, ai_import, tmp_path):
        errors = ai_import._validate_entry({"plik": str(tmp_path / "brak.pdf")})
        assert any("nie istnieje" in e for e in errors)

    def test_missing_header_fields(self, ai_import, fake_pdf):
        errors = ai_import._validate_entry({"plik": str(fake_pdf), "header": {}, "items": []})
        assert any("brak pól nagłówka" in e for e in errors)

    def test_missing_item_fields(self, ai_import, fake_pdf):
        entry = _valid_entry(fake_pdf)
        entry["items"] = [{"opis": "coś bez kategorii"}]
        errors = ai_import._validate_entry(entry)
        assert any("kategoria_klucz" in e for e in errors)

    def test_unknown_category_rejected(self, ai_import, fake_pdf):
        entry = _valid_entry(fake_pdf)
        entry["items"][0]["kategoria_klucz"] = "zmyslona_kategoria"
        errors = ai_import._validate_entry(entry)
        assert any("nieznana kategoria" in e for e in errors)

    def test_valid_entry_has_no_errors(self, ai_import, fake_pdf):
        assert ai_import._validate_entry(_valid_entry(fake_pdf)) == []


class TestImportBatch:
    def test_saves_valid_entry_with_pdf_bytes_and_category(self, db_module, ai_import, project, fake_pdf):
        results = ai_import.import_batch(project["id"], [_valid_entry(fake_pdf)])
        assert len(results["saved"]) == 1
        assert results["errors"] == []

        items = db_module.list_items(project_id=project["id"])
        assert len(items) == 1
        assert items[0]["kategoria_klucz"] == "uslugi_podwykonawcow"
        assert items[0]["kategoria_nazwa"]  # auto-uzupełnione z KATEGORIE
        assert items[0]["zrodlo_dopasowania"] == "claude-code"

        invoices = db_module.list_invoices(project["id"])
        assert invoices[0]["numer_faktury"] == "FV1"
        assert invoices[0]["has_pdf"]  # bajty PDF-u faktycznie zapisane

    def test_dry_run_does_not_write_to_db(self, db_module, ai_import, project, fake_pdf):
        results = ai_import.import_batch(project["id"], [_valid_entry(fake_pdf)], dry_run=True)
        assert len(results["saved"]) == 1
        assert results["saved"][0]["dry_run"] is True
        assert db_module.list_invoices(project["id"]) == []

    def test_duplicate_file_is_skipped_on_second_import(self, ai_import, project, fake_pdf):
        entry = _valid_entry(fake_pdf)
        ai_import.import_batch(project["id"], [entry])
        results = ai_import.import_batch(project["id"], [entry])
        assert results["saved"] == []
        assert len(results["skipped_duplicate"]) == 1

    def test_invalid_entry_reported_without_aborting_whole_batch(self, ai_import, project, fake_pdf):
        good = _valid_entry(fake_pdf)
        bad = {"plik": "nie-istnieje.pdf"}
        results = ai_import.import_batch(project["id"], [bad, good])
        assert len(results["errors"]) == 1
        assert len(results["saved"]) == 1

    def test_unknown_project_id_raises(self, ai_import, fake_pdf):
        with pytest.raises(SystemExit):
            ai_import.import_batch("nieistniejacy-projekt", [_valid_entry(fake_pdf)])
