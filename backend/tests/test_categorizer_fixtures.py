"""
Testy end-to-end: parse_invoice() na prawdziwych fakturach PDF, porównane
z wartościami zweryfikowanymi ręcznie (linia po linii z oryginałami) podczas
pracy nad parserem. To one złapały większość realnych bugów po drodze —
znacznie więcej niż testy jednostkowe czystych funkcji.

Pliki PDF (input/, Nowy folder/) są CELOWO poza gitem (.gitignore) — mogą
zawierać rzeczywiste dane firmowe. Jeśli katalog nie istnieje (świeży klon
repo, CI), testy są pomijane zamiast failować — to nie jest "brak testów",
tylko brak lokalnych danych do przetestowania na nich.
"""
import os

import pytest

from app.categorizer import parse_invoice
from conftest import REPO_ROOT

INPUT_DIR = os.path.join(REPO_ROOT, "input")
NOWY_FOLDER = os.path.join(REPO_ROOT, "Nowy folder")

# (ścieżka względem repo, oczekiwane pola). `numer_faktury`/`sprzedawca`
# porównywane dokładnie; `netto`/`brutto` z tolerancją grosza (rozbieżności
# zaokrągleń per-pozycja vs. suma faktury).
CASES = [
    (f"{INPUT_DIR}/(S)FS-1909_25_PI.pdf", {
        "numer_faktury": "(S)FS-1909/25/PI", "sprzedawca": "EUROTERM TGS sp. z o.o.",
        "waluta": "PLN", "razem_brutto": 166.76, "min_items": 2,
    }),
    (f"{INPUT_DIR}/6340135676-20260210-0C0020309144-8E.pdf", {
        "numer_faktury": "FA_26_240_01196", "sprzedawca": "Sonepar Polska Sp. z o.o.",
        "waluta": "PLN", "razem_brutto": 1276.37, "min_items": 11,
    }),
    (f"{INPUT_DIR}/9080648368_30969721.pdf", {
        "numer_faktury": "9080648368", "sprzedawca": "Tyco Building Services Products GmbH",
        "waluta": "EUR", "razem_brutto": 5100.0, "min_items": 1,
    }),
    (f"{INPUT_DIR}/Duplikat nr 1079367972.PDF", {
        "numer_faktury": "1079367972", "sprzedawca": "Siemens Sp. z o.o.",
        "waluta": "PLN", "razem_brutto": 7306.25, "min_items": 5,
    }),
    (f"{INPUT_DIR}/FV262500003003.pdf", {
        "numer_faktury": "FV262500003003", "sprzedawca": "TIM S.A.",
        "waluta": "PLN", "razem_brutto": 624.47, "min_items": 2,
    }),
    (f"{INPUT_DIR}/Invoice_10021147.pdf", {
        "numer_faktury": "10021147", "sprzedawca": "Fire Eater A/S",
        "waluta": "EUR", "razem_brutto": 1009.62, "min_items": 13,
    }),
    (f"{INPUT_DIR}/MCRFakturaFVSHW25090719.pdf", {
        "numer_faktury": "FVSHW/2509/0719", "sprzedawca": "MERCOR Light&Vent sp. z o.o.",
        "waluta": "PLN", "razem_brutto": 1919.17, "min_items": 1,
    }),
    (f"{INPUT_DIR}/Sales Invoice 232326.pdf", {
        "numer_faktury": "232326", "sprzedawca": "Rapidrop Europe Limited",
        "waluta": "EUR", "razem_brutto": 8631.94, "min_items": 18,
    }),
    (f"{NOWY_FOLDER}/5342649864-20260410-721952800008-B3.pdf", {
        "numer_faktury": "FS 2628/2026", "sprzedawca": "AWAX",  # substring — nazwa jest długa
        "waluta": "PLN", "razem_brutto": 366.54, "min_items": 5,
    }),
    (f"{NOWY_FOLDER}/8351605276-20260416-407D4B0004CD-34.pdf", {
        "numer_faktury": "FwP/3151/26", "sprzedawca": "DRIAL WYNAJEM",
        "waluta": "PLN", "razem_brutto": 1259.52, "min_items": 3,
    }),
    (f"{NOWY_FOLDER}/8431486388-20260415-6BB66E80000D-6B.pdf", {
        "numer_faktury": "FS 535/04/2026", "sprzedawca": "SIKLA POLSKA",
        "waluta": "PLN", "razem_brutto": 1763.08, "min_items": 9,
    }),
    (f"{NOWY_FOLDER}/8431486388-20260415-6BB66E80003A-4F.pdf", {
        "numer_faktury": "FS 539/04/2026", "sprzedawca": "SIKLA POLSKA",
        "waluta": "PLN", "razem_brutto": 1362.84, "min_items": 2,
    }),
    (f"{NOWY_FOLDER}/8820003786-20260414-61AB69C00004-80.pdf", {
        "numer_faktury": "FS-227/2026/SKR/04", "sprzedawca": "Boxmet",
        "waluta": "PLN", "razem_brutto": 162.73, "min_items": 1,
    }),
    (f"{NOWY_FOLDER}/Sales Invoice 237468.pdf", {
        "numer_faktury": "237468", "sprzedawca": "Rapidrop Europe Limited",
        "waluta": "EUR", "razem_brutto": 15.29, "min_items": 2,
    }),
]


_CASE_IDS = [os.path.basename(path) for path, _ in CASES]


@pytest.mark.parametrize("path,expected", CASES, ids=_CASE_IDS)
def test_sample_invoice_parses_correctly(path, expected):
    if not os.path.isfile(path):
        pytest.skip(f"Brak pliku (dane lokalne, poza gitem): {path}")

    header, items = parse_invoice(path)

    assert header["numer_faktury"] == expected["numer_faktury"]
    assert expected["sprzedawca"] in (header["sprzedawca"] or "")
    assert header["waluta"] == expected["waluta"]
    assert header["razem_brutto"] == pytest.approx(expected["razem_brutto"], abs=0.02)
    assert len(items) >= expected["min_items"]

    # Zabezpieczenie przeciw wartościom "uciekającym" o rzędy wielkości (pole
    # sąsiednie po cichu wlewające się w cenę/kwotę przez brak granicy w
    # regexie — tak wyglądał bug w Mercor: ilość "1,00" wlana w cenę_netto
    # dawała 1 001 560,30 zamiast 1560,30). Nie sprawdzamy ilość×cena==netto
    # wprost, bo część dostawców (np. Fire Eater) legalnie stosuje rabat per
    # pozycja, więc ta tożsamość nie zawsze zachodzi — tylko rząd wielkości.
    for it in items:
        cena, netto = it.get("cena_netto"), it.get("wartosc_netto")
        if cena and netto:
            assert cena < netto * 50 + 10, f"cena_netto podejrzanie duża względem wartość_netto: {it}"


def test_at_least_one_fixture_file_present():
    """Jeśli WSZYSTKIE pliki są niedostępne, powyższe testy cicho przechodzą
    jako 'skipped' i łatwo nie zauważyć, że w ogóle nic nie sprawdzają —
    ten test explicit failuje w takiej sytuacji zamiast fałszywej zieleni."""
    any_present = any(os.path.isfile(path) for path, _ in CASES)
    if not any_present:
        pytest.fail(
            "Żaden z plików testowych nie jest dostępny lokalnie — testy "
            "end-to-end nic nie sprawdziły. To OK na świeżym klonie repo "
            "(pliki są .gitignore'owane), ale nie na maszynie, gdzie "
            "input/ i 'Nowy folder/' powinny istnieć."
        )
