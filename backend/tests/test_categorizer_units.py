"""
Testy jednostkowe czystych funkcji parsera — bez potrzeby plików PDF,
zawsze uruchamiane (też w CI). Każdy przypadek odpowiada realnemu bugowi
znalezionemu i naprawionemu podczas pracy nad appką — trzymają regresję.
"""
import pytest

from app.categorizer import (
    _map_columns,
    _strip_diacritics,
    clean_amount,
    detect_vendor,
    find_value,
    parse_text_mercor,
)
from app.db import extract_year


class TestCleanAmount:
    def test_none_returns_none(self):
        assert clean_amount(None) is None

    def test_plain_integer(self):
        assert clean_amount("1234") == 1234.0

    def test_four_digit_no_thousands_separator(self):
        # Bug: Sonepar "Kwota należności ogółem: 1276,37 PLN" — 4-cyfrowa
        # część całkowita bez separatora tysięcy łamała starszy regex,
        # który zakładał maks. 3 cyfry przed pierwszym separatorem.
        assert clean_amount("1276,37") == 1276.37

    def test_polish_thousands_dot_decimal_comma(self):
        assert clean_amount("1.234,56") == 1234.56

    def test_space_thousands_separator(self):
        assert clean_amount("1 234,56") == 1234.56

    def test_us_thousands_comma_decimal_dot(self):
        # Bug: Rapidrop "Total € Incl. VAT 8,631.94" dawało wcześniej 8.631
        # (regex łapał tylko do pierwszego separatora, gubiąc ".94").
        assert clean_amount("8,631.94") == 8631.94

    def test_large_us_number_still_parses_fully(self):
        assert clean_amount("1,009.62") == 1009.62

    def test_percent_value_alone_is_not_an_amount(self):
        # "23,00 %" jest wycinane w całości jako wartość procentowa —
        # zwykły ułamek stawki VAT, nie kwota pieniężna do zliczenia.
        assert clean_amount("23,00 %") is None


class TestStripDiacritics:
    def test_removes_polish_diacritics(self):
        assert _strip_diacritics("podkładka") == "podkladka"

    def test_matches_pdf_without_diacritics(self):
        # Bug: niektóre PDF-y renderują część słów bez polskich znaków
        # ("PODKLADKA" zamiast "PODKŁADKA") mimo że sąsiednie słowa mają
        # poprawne znaki — dopasowanie słów kluczowych musi to tolerować.
        assert _strip_diacritics("PODKLADKA".lower()) == _strip_diacritics("podkładka")


class TestMapColumns:
    def test_item_table_header_maps_value_columns(self):
        header = ["Lp.", "Nazwa towaru lub usługi", "Cena netto", "Ilość", "Wartość netto"]
        mapping = _map_columns(header)
        assert mapping is not None
        assert "opis" in mapping
        assert "cena_netto" in mapping

    def test_metadata_table_without_value_column_is_rejected(self):
        # Bug: tabela "Termin płatności / Opis płatności" (2 kolumny,
        # żadna liczbowa) trafiała jako tabela pozycji, bo "Opis płatności"
        # pasował do wzorca kolumny opisu — dawało fałszywe pozycje faktury.
        header = ["Termin płatności", "Opis płatności"]
        assert _map_columns(header) is None

    def test_delivery_index_table_without_value_column_is_rejected(self):
        header = ["Lp.", "Data dostawy / wykonania", "Indeks"]
        assert _map_columns(header) is None

    def test_one_field_per_column_no_double_claim(self):
        # Bug: "Stawka podatku" pasowała jednocześnie do stawka_vat i (przez
        # rdzeń "podat") do kwota_vat, więc jedno pole nadpisywało drugie.
        header = ["Lp.", "Nazwa", "Stawka podatku", "Kwota netto", "Kwota podatku", "Kwota brutto"]
        mapping = _map_columns(header)
        assert mapping is not None
        assert mapping.get("stawka_vat") != mapping.get("kwota_vat")


class TestDetectVendor:
    def test_sonepar_requires_literal_name_not_just_ksef(self):
        # Bug: dowolna faktura z Krajowego Systemu e-Faktur (obowiązkowego
        # dla każdego wystawcy) była błędnie rozpoznawana jako Sonepar,
        # bo wykrywanie leciało po samym słowie "Numer KSEF".
        text = "Krajowy System e-Faktur\nNumer KSEF:123\nSprzedawca: AWAX Sp. z o.o."
        assert detect_vendor(text) == "ksef_generic"

    def test_sonepar_detected_by_name(self):
        text = "Faktura VAT\nSprzedawca: Sonepar Polska Sp. z o.o.\nNumer KSEF:123"
        assert detect_vendor(text) == "sonepar"

    def test_generic_fallback_without_any_marker(self):
        assert detect_vendor("Some random invoice text with no vendor markers") == "generic"


class TestFindValue:
    def test_returns_first_matching_pattern(self):
        text = "Numer faktury: FV/123/2026"
        assert find_value(text, r"Numer faktury:\s*(\S+)") == "FV/123/2026"

    def test_returns_none_when_nothing_matches(self):
        assert find_value("brak niczego", r"Nie ma tego:\s*(\S+)") is None


class TestParseTextMercor:
    def test_ilosc_and_cena_netto_are_not_merged(self):
        # Bug: dla "1 MWFFID240UA szt 1,00 1 560,30 PLN ..." regex łapiący
        # cenę netto ([\d\s,]+? przed " PLN") nie miał granicy oddzielającej
        # go od pola ilości, więc "1,00 1 560,30" trafiało w całości do
        # cena_netto (dawało 1 001 560,30), a ilosc wychodziło None (brane
        # było przez pomyłkę z pola J.M.).
        line = "1 MWFFID240UA szt 1,00 1 560,30 PLN 1 560,30 23% 358,87 1 919,17"
        items = parse_text_mercor(line)
        assert len(items) == 1
        it = items[0]
        assert it["ilosc"] == 1.0
        assert it["jm"] == "szt"
        assert it["cena_netto"] == 1560.30
        assert it["wartosc_netto"] == 1560.30
        assert it["wartosc_brutto"] == 1919.17


class TestExtractYear:
    @pytest.mark.parametrize("date_str,expected", [
        ("2026-01-20", 2026),
        ("20.01.2026", 2026),
        ("11-Aug-2025", 2025),
        ("13 April 2026", 2026),
        (None, None),
        ("", None),
        ("brak daty", None),
    ])
    def test_various_formats(self, date_str, expected):
        assert extract_year(date_str) == expected
