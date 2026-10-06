"""
ai_import.py — import faktur odczytanych i skategoryzowanych przez Claude
Code (czytającego PDF bezpośrednio, wizualnie), zamiast regexowego
parse_invoice()/kategoryzuj() w categorizer.py.

Dlaczego to w ogóle istnieje: na prawdziwych fakturach z dwóch projektów
regexowy parser miał poważne dziury — zepsute kodowanie fontów w PDF-ie
(sprzedawca wychodził jako fragment zupełnie innego zdania), zeskanowane
dokumenty bez żadnej warstwy tekstowej (zero danych), niestandardowy układ
tabeli pozycji (dwie pozycje sklejone w jedną). Claude czytający PDF
wizualnie (narzędzie Read w Claude Code) poradził sobie z każdym z tych
przypadków bez dodatkowego kodu — testowane na kilku najgorszych znanych
awariach, wszystkie trafione poprawnie.

Ten moduł NIE wywołuje żadnego API i nie jest samodzielnym procesem w tle.
Zakłada, że dane (nagłówek + pozycje + kategoria każdej pozycji) już
zostały wyprodukowane przez Claude Code w BIEŻĄCEJ, interaktywnej sesji —
czytając PDF-y narzędziem Read i oceniając kategorię wg taksonomii z
categorizer.py (KATEGORIE, _VENDOR_CATEGORY_HINTS) oraz reguł brzegowych
opisanych w docs/AI_KATEGORYZACJA.md (dokumenty WZ, korekty walutowe,
zbiorcze rozliczenia pracownicze, faktury zaliczkowe). Ten skrypt tylko
zapisuje gotowe dane do tej samej bazy, tą samą drogą
(find_duplicate/save_invoice), co zwykły upload przez GUI — więc duplikaty,
podgląd PDF-u i wszystko inne w appce działa identycznie jak dla faktur
wgranych normalnie.

Użycie (z poziomu sesji Claude Code):
  1. Przeczytaj każdy PDF z folderu narzędziem Read.
  2. Dla każdej PRAWDZIWEJ faktury (pomiń dokumenty WZ — to załączniki,
     nie faktury) zbuduj wpis wg schema() poniżej.
  3. Zapisz całą listę wpisów do pliku JSON.
  4. Uruchom (najpierw z --dry-run, żeby zobaczyć co by się zapisało):
       python -m app.ai_import <project_id> <plik.json> --dry-run
       python -m app.ai_import <project_id> <plik.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import db
from .categorizer import KATEGORIE

# "plik" i "typ" są wyprowadzane automatycznie (z realnej ścieżki pliku /
# stałej wartości) — Claude nie musi ich zgadywać. Pozostałe pola nagłówka
# faktury muszą być podane wprost (nawet jako None, jeśli naprawdę nie da
# się ich odczytać z dokumentu).
_REQUIRED_HEADER_FIELDS = set(db._INVOICE_FIELDS) - {"plik", "typ"}
_REQUIRED_ITEM_FIELDS = {"opis", "kategoria_klucz"}


def schema() -> dict:
    """Dokładny kształt jednego wpisu w pliku wsadowym (lista takich
    obiektów) — do wglądu, nie do automatycznego wywoływania."""
    return {
        "plik": "C:/pełna/ścieżka/do/oryginalnego/pliku.pdf",
        "header": {f: None for f in sorted(_REQUIRED_HEADER_FIELDS)},
        "items": [
            {
                "opis": "...", "indeks": None, "pkwiu": None, "ilosc": None, "jm": None,
                "cena_netto": None, "wartosc_netto": None, "stawka_vat": None,
                "kwota_vat": None, "wartosc_brutto": None,
                "kategoria_klucz": "jeden z kluczy w categorizer.KATEGORIE",
            }
        ],
    }


def _validate_entry(entry: dict) -> list[str]:
    errors = []
    plik = entry.get("plik")
    if not plik:
        return ["brak pola 'plik' (ścieżka do oryginalnego PDF na dysku)"]
    if not Path(plik).is_file():
        errors.append(f"plik nie istnieje: {plik}")

    header = entry.get("header")
    if not isinstance(header, dict):
        errors.append("brak klucza 'header' (obiekt z polami nagłówka faktury)")
    else:
        missing = _REQUIRED_HEADER_FIELDS - header.keys()
        if missing:
            errors.append(f"brak pól nagłówka: {sorted(missing)}")

    items = entry.get("items")
    if items is None:
        errors.append("brak klucza 'items' (lista pozycji — może być pusta [])")
    else:
        for i, it in enumerate(items):
            missing = _REQUIRED_ITEM_FIELDS - it.keys()
            if missing:
                errors.append(f"pozycja {i}: brak pól {sorted(missing)}")
            klucz = it.get("kategoria_klucz")
            if klucz and klucz not in KATEGORIE:
                errors.append(
                    f"pozycja {i}: nieznana kategoria '{klucz}' "
                    f"(dozwolone: {', '.join(sorted(KATEGORIE))})"
                )
    return errors


def import_batch(project_id: str, entries: list[dict], dry_run: bool = False) -> dict:
    if not db.get_project(project_id):
        raise SystemExit(f"Nie znaleziono projektu: {project_id}")

    results: dict = {"saved": [], "skipped_duplicate": [], "errors": []}
    for entry in entries:
        plik_label = entry.get("plik", "<brak>")
        errors = _validate_entry(entry)
        if errors:
            results["errors"].append({"plik": plik_label, "errors": errors})
            continue

        pdf_path = Path(entry["plik"])
        pdf_bytes = pdf_path.read_bytes()
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()

        header = dict(entry["header"])
        header["plik"] = pdf_path.name
        header.setdefault("typ", "claude-code")

        dup = db.find_duplicate(
            project_id, content_hash, header.get("numer_faktury"), header.get("sprzedawca")
        )
        if dup and dup.get("content_hash") == content_hash:
            results["skipped_duplicate"].append({"plik": header["plik"], "matches": dup.get("plik")})
            continue

        items = []
        for i, it in enumerate(entry.get("items", []), start=1):
            klucz = it.get("kategoria_klucz")
            item = dict(it)
            item.setdefault("lp", i)
            item.setdefault("kategoria_nazwa", KATEGORIE.get(klucz, KATEGORIE["inne"]))
            item.setdefault("pewnosc", 100)
            item.setdefault("zrodlo_dopasowania", "claude-code")
            item.setdefault("powod", "odczyt i kategoryzacja przez Claude Code")
            items.append(item)

        if dry_run:
            results["saved"].append({
                "plik": header["plik"], "numer_faktury": header.get("numer_faktury"),
                "items": len(items), "dry_run": True,
            })
            continue

        invoice_id = db.save_invoice(
            project_id, header, items, content_hash=content_hash, pdf_data=pdf_bytes
        )
        results["saved"].append({
            "plik": header["plik"], "invoice_id": invoice_id,
            "numer_faktury": header.get("numer_faktury"), "items": len(items),
        })
    return results


def main():
    # Domyślna strona kodowa konsoli Windows (cp1250) wywala się na ✓/⊘/✗
    # poniżej — reconfigure dostępny od Pythona 3.7, bezpieczny no-op gdy
    # stdout nie jest prawdziwym strumieniem tekstowym (np. przekierowanie).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project_id")
    parser.add_argument("batch_json", type=Path)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Waliduje i pokazuje, co by się zapisało, bez zapisu do bazy.",
    )
    args = parser.parse_args()

    entries = json.loads(args.batch_json.read_text(encoding="utf-8"))
    db.init_db()
    results = import_batch(args.project_id, entries, dry_run=args.dry_run)

    print(f"Zapisano: {len(results['saved'])}")
    for r in results["saved"]:
        suffix = " (dry-run, nie zapisano)" if r.get("dry_run") else f" | id={r.get('invoice_id')}"
        print(f"  ✓ {r['plik']} | {r.get('numer_faktury')} | {r['items']} pozycji{suffix}")

    if results["skipped_duplicate"]:
        print(f"\nPominięto jako duplikaty: {len(results['skipped_duplicate'])}")
        for r in results["skipped_duplicate"]:
            print(f"  ⊘ {r['plik']} (ten sam plik co już zapisana faktura: {r['matches']})")

    if results["errors"]:
        print(f"\nBłędy walidacji: {len(results['errors'])}", file=sys.stderr)
        for r in results["errors"]:
            print(f"  ✗ {r['plik']}: {'; '.join(r['errors'])}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
