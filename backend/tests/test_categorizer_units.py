"""
Testy jednostkowe czystych funkcji parsera — bez potrzeby plików PDF,
zawsze uruchamiane (też w CI). Każdy przypadek odpowiada realnemu bugowi
znalezionemu i naprawionemu podczas pracy nad appką — trzymają regresję.
"""
import pytest

from app.categorizer import (
    _extract_vendor_name,
    _is_delivery_note,
    _looks_like_real_invoice_number,
    _looks_like_real_vendor_name,
    _map_columns,
    _strip_diacritics,
    _synthesize_fallback_item,
    clean_amount,
    detect_vendor,
    extract_header,
    find_value,
    kategoryzuj,
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

    def test_rejects_astronomically_large_glued_together_digits(self):
        # Bug: gdy pdfplumber zleje kilka komórek/wierszy tabeli w jedną
        # (np. przy nietypowym layoucie), regex łapiący "ciąg cyfr" łykał
        # to jako JEDNĄ, absurdalnie wielką kwotę (rzędu 10^30) zamiast
        # rozpoznać błąd — takie "koszty" potrafiły zdominować sumy
        # miesięczne na wykresie trendu, mimo że cały projekt wart był
        # ok. miliona złotych.
        assert clean_amount("20664414392732124000000000000000,00") is None
        assert clean_amount("81,18") == 81.18  # normalna kwota nadal działa


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


class TestLooksLikeRealInvoiceNumber:
    @pytest.mark.parametrize("value", ["FV1", "232326", "F.ZAL_17", "FS 2628/2026", "(S)FS-1909/25/PI"])
    def test_accepts_realistic_numbers(self, value):
        assert _looks_like_real_invoice_number(value) is True

    @pytest.mark.parametrize("value", [None, "", "-", "Str", "Sikla"])
    def test_rejects_values_without_a_digit(self, value):
        # Bug: fallback dla nieznanych dostawców (bez trafienia w etykietę
        # "Numer faktury") potrafił złapać przypadkowe sąsiednie słowo
        # (urwany fragment adresu, placeholder "-", fragment nazwy
        # sprzedawcy) jako numer faktury. Dwie RÓŻNE faktury tego samego
        # dostawcy dostawały wtedy ten sam śmieciowy "numer", co dawało
        # fałszywe ostrzeżenia "wygląda na duplikat".
        assert _looks_like_real_invoice_number(value) is False

    def test_rejects_overly_long_value(self):
        assert _looks_like_real_invoice_number("A" * 50) is False


class TestLooksLikeRealVendorName:
    @pytest.mark.parametrize("value", [
        "TIM S.A.", "Sonepar Polska Sp. z o.o.", "Tyco Building Services Products GmbH",
    ])
    def test_accepts_realistic_names(self, value):
        assert _looks_like_real_vendor_name(value) is True

    def test_rejects_label_fragment_ending_in_colon(self):
        # Bug: regex fallback czasem łapał etykietę SĄSIEDNIEGO pola
        # zamiast wartości (np. "Tel:" zamiast prawdziwej nazwy firmy).
        assert _looks_like_real_vendor_name("Tel:") is False

    def test_rejects_sentence_from_terms_and_conditions(self):
        # Bug: generyczny fallback szukał dowolnej linii z formą prawną
        # (Sp. z o.o. itd.) w pierwszych ~600 znakach — jeśli klauzula
        # Ogólnych Warunków wspominała nazwę kontrahenta wcześniej niż
        # właściwy nagłówek "Sprzedawca", łapał całe zdanie zamiast nazwy.
        sentence = (
            "Wszystkie dostawy oraz świadczenie usług przez firmę Sikla "
            "Polska Sp. z o.o. odbywa się w oparciu o aktualne zapisy "
            "Ogólnych Warunków"
        )
        assert _looks_like_real_vendor_name(sentence) is False

    def test_rejects_mixed_up_buyer_block(self):
        assert _looks_like_real_vendor_name(
            "Forma płatności :przedpłata Nabywca: DEKK FIRE SOLUTIONS SP. Z O.O."
        ) is False


class TestExtractHeaderRejectsGarbageFields:
    def test_numer_faktury_without_digit_is_dropped_not_kept_as_garbage(self):
        text = "Jakiś dokument\nNr Str\nFaktura\nSprzedawca:\nTel:\n"
        h = extract_header(text, tables=[], vendor="generic")
        assert h["numer_faktury"] is None

    def test_vendor_extraction_skips_terms_and_conditions_sentence(self):
        text = (
            "Wszystkie dostawy oraz świadczenie usług przez firmę Sikla Polska "
            "Sp. z o.o. odbywa się w oparciu o aktualne zapisy Ogólnych Warunków\n"
            "Sprzedawca:\nSikla Polska Sp. z o.o.\nNIP 123\n"
        )
        assert _extract_vendor_name(text) == "Sikla Polska Sp. z o.o."


class TestTransportCategoryDoesNotOvermatch:
    """Bug: słowo kluczowe "dostaw" (substring) łapało też "dostawca"/
    "dostawcy" (SPRZEDAWCA faktury — zupełnie inne pojęcie niż koszt
    przesyłki), więc dowolna pozycja ze słowem "dostawca" gdziekolwiek w
    opisie/indeksie trafiała do kategorii transport, sztucznie zawyżając
    jej sumę kosztów w projekcie."""

    def test_delivery_charge_is_still_transport(self):
        result = kategoryzuj("Koszt dostawy towaru", use_web=False)
        assert result["kategoria_klucz"] == "transport"

    def test_supplier_mention_is_not_transport(self):
        result = kategoryzuj("Zestaw wg specyfikacji dostawcy XYZ", use_web=False)
        assert result["kategoria_klucz"] != "transport"

    def test_bare_carriage_is_transport(self):
        result = kategoryzuj("Carriage", use_web=False)
        assert result["kategoria_klucz"] == "transport"

    def test_carriage_bolt_is_not_transport(self):
        # "carriage bolt" to śruba (złącze mechaniczne), nie koszt przesyłki.
        result = kategoryzuj("Carriage bolt M8x50", use_web=False)
        assert result["kategoria_klucz"] != "transport"


class TestVendorExtractionRejectsBuyerBleed:
    """Bug znaleziony na żywym deployu (projekt 601, ~27/103 faktur): ta
    appka jest wewnętrznym narzędziem DEKK Fire Solutions do przetwarzania
    faktur OD dostawców DO DEKK, więc "DEKK Fire Solutions" nigdy nie
    powinno wyjść jako sprzedawca — a jednak wychodziło, gdy ekstrakcja
    pomyliła blok Sprzedawcy z blokiem Nabywcy (typowe przy fakturach z
    układem dwukolumnowym)."""

    @pytest.mark.parametrize("value", [
        "DEKKFIRESOLUTIONSP.ZO.O. Idnabywcy: 1231283458",
        "PRZEDSIĘBIORSTWO PRODUKCYJNO- DEKK FIRE SOLUTIONS Sp. z o.o.",
        "EWMET Ewa Małecka DEKK FIRE SOLUTIONS SP.Z O.O.",
        "DEKK FIRE SOLUTIONS Sp. z o.o.",
    ])
    def test_rejects_buyer_name_in_any_form(self, value):
        assert _looks_like_real_vendor_name(value) is False

    def test_still_accepts_a_real_vendor_mentioning_dekk_as_customer_elsewhere(self):
        # Kontrola negatywna: samo słowo w INNYM miejscu tekstu (nie w
        # samej wartości sprzedawcy) nie jest tu sprawdzane — to test na
        # to, że walidacja nie jest przesadnie szeroka wobec prawdziwych
        # nazw firm bez "dekk" w środku.
        assert _looks_like_real_vendor_name("TASTA ARMATURA Sp. z o.o.") is True


class TestIsDeliveryNote:
    def test_recognizes_wz_document_by_its_own_heading(self):
        text = (
            "METALOWIEC | www.opara.pl\n"
            "Data:30.07.2025\n"
            "DOKUMENT WYDANIA nr WZ 013971/25\n"
            "Odbiorca: DEKK FIRE SOLUTIONS SP.Z O.O.\n"
        )
        assert _is_delivery_note(text) is True

    def test_real_invoice_mentioning_wz_numbers_is_not_a_delivery_note(self):
        # Bug: prawdziwa faktura CZĘSTO wymienia numery WZ, do których się
        # odnosi ("Wydano wg dokumentów WZ 011907/25...") — to nie może
        # samo w sobie sprawiać, że faktura zostanie potraktowana jak
        # załącznik i pominięta. Liczy się tylko WŁASNY nagłówek dokumentu.
        text = (
            "Faktura nr F/007418/25\n"
            "Sprzedawca/podatnik Nabywca/płatnik\n"
            "PHPU Bożena i Tadeusz Oparowie s.c. DEKK FIRE SOLUTIONS SP.Z O.O.\n"
            "Wydano wg dokumentów\n"
            "WZ 011907/25 z dnia 03.07.2025, Magazyn Główny;\n"
        )
        assert _is_delivery_note(text) is False


def _words_from_columns(left_lines, right_lines, col_x=310):
    """Buduje listę słów w formacie pdfplumber `page.extract_words()`
    (dict z 'text'/'x0'/'top') z dwóch kolumn tekstu — do testowania
    rozdzielania układu dwukolumnowego bez potrzeby prawdziwego PDF-u."""
    words = []
    for row, line in enumerate(left_lines):
        for col, word in enumerate(line.split()):
            words.append({"text": word, "x0": 10 + col * 15, "top": row * 12})
    for row, line in enumerate(right_lines):
        for col, word in enumerate(line.split()):
            words.append({"text": word, "x0": col_x + col * 15, "top": row * 12})
    return words


class TestExtractHeaderTwoColumnVendorSplit:
    def test_generic_vendor_two_column_layout_recovers_correct_seller(self):
        # Bug znaleziony na żywych danych: ta appka jest wewnętrznym
        # narzędziem DEKK Fire Solutions, więc "Sprzedawca | Nabywca" w
        # układzie dwukolumnowym (typowy nie tylko dla KSeF) dawał po
        # zwykłym extract_text() jedną zlaną linię "Sprzedawca NABYWCA" —
        # generyczny fallback bez rozdzielenia kolumn albo nic nie
        # znajdował, albo łapał nazwę nabywcy (DEKK) zamiast sprzedawcy.
        left = ["Sprzedawca", "TASTA ARMATURA SP. Z O.O.", "ul. Testowa 1"]
        right = ["NABYWCA", "DEKK FIRE SOLUTIONS Sp. z o.o.", "ul. Inna 2"]
        words = _words_from_columns(left, right)
        text = (
            "Sprzedawca NABYWCA\n"
            "TASTA ARMATURA SP. Z O.O. DEKK FIRE SOLUTIONS Sp. z o.o.\n"
            "ul. Testowa 1 ul. Inna 2\n"
        )
        h = extract_header(text, tables=[], vendor="generic",
                            page0_words=words, page0_width=620)
        assert h["sprzedawca"] == "TASTA ARMATURA SP. Z O.O."

    def test_known_vendor_hardcoded_name_wins_over_column_split_guess(self):
        # Regresja: rozdzielanie kolumn nie może przesłonić zaufanej,
        # zahardkodowanej nazwy znanego dostawcy krótszym, ale błędnym
        # dopasowaniem z heurystyki.
        left = ["Sprzedawca", "EUROTERM"]
        right = ["Nabywca", "Ktoś Inny Sp. z o.o."]
        words = _words_from_columns(left, right)
        text = "Sprzedawca Nabywca\nEUROTERM Ktoś Inny Sp. z o.o.\n"
        h = extract_header(text, tables=[], vendor="euroterm",
                            page0_words=words, page0_width=620)
        assert h["sprzedawca"] == "EUROTERM TGS sp. z o.o."


class TestExtractHeaderTotalsFromUnusualLabels:
    def test_razem_brutto_from_three_number_summary_line_without_label(self):
        # Bug: Tasta Armatura pisze "Do zapłaty" i jego wartość w RÓŻNYCH
        # komórkach/liniach wyekstrahowanego tekstu (układ tabelaryczny),
        # więc wzorce szukające liczby zaraz po etykiecie nic nie łapały —
        # mimo że podsumowanie netto/VAT/brutto stoi tuż obok, w jednej,
        # w pełni czytelnej linii "Razem X Y Z".
        text = (
            "Faktura VAT 2025/06/FA/CD/461\n"
            "Razem 106,64 24,53 131,17\n"
            "Termin płatności Bank Do zapłaty\n"
            "30-07-2025 BNP Paribas Bank Polska S.A.\n"
            "131,17 PLN\n"
        )
        h = extract_header(text, tables=[], vendor="generic")
        assert h["razem_brutto"] == 131.17

    def test_razem_brutto_from_naleznosc_label(self):
        # Bug: Sonepar używa etykiety "NALEŻNOŚĆ:", nieobecnej wcześniej
        # w liście rozpoznawanych wariantów "kwota do zapłaty".
        text = "Suma 268,00 61,64 329,64\nNALEŻNOŚĆ: 329,64 PLN\n"
        h = extract_header(text, tables=[], vendor="generic")
        assert h["razem_brutto"] == 329.64


class TestSynthesizeFallbackItem:
    def test_creates_one_item_from_known_total_when_table_unparseable(self):
        # Bug: gdy żaden parser tabeli pozycji nic nie znalazł (inny układ
        # kolumn niż obsługiwane formaty, albo faktura usługowa bez żadnej
        # tabeli — np. "Montaż instalacji tryskaczowej" za jedną kwotę),
        # cała faktura znikała z zestawień kosztów mimo znanej sumy z
        # nagłówka. Jedna zbiorcza pozycja jest gorsza niż rozbicie, ale
        # dużo lepsza niż całkowita utrata kosztu tej faktury.
        header = {"sprzedawca": "Acme Sp. z o.o.", "razem_netto": 100.0, "razem_brutto": 123.0}
        items = _synthesize_fallback_item(header)
        assert len(items) == 1
        assert items[0]["wartosc_brutto"] == 123.0
        assert items[0]["wartosc_netto"] == 100.0
        assert "Acme Sp. z o.o." in items[0]["opis"]

    def test_returns_nothing_without_any_known_total(self):
        assert _synthesize_fallback_item({"sprzedawca": "Acme"}) == []

    def test_fills_missing_side_from_the_other_when_only_one_total_known(self):
        items = _synthesize_fallback_item({"razem_netto": 100.0, "razem_brutto": None})
        assert items[0]["wartosc_brutto"] == 100.0
