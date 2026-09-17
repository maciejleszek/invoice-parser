"""
categorize6.py — v6 (universal, PL + EN)
-----------------------------------------
Automatyczna kategoryzacja wydatków z faktur budowlanych.

Zmiany w v6 (relative to v5):
  • clean_amount poprawnie parsuje kwoty z obydwoma separatorami naraz
    (np. "8,631.94"), wcześniej ucinało część po drugim separatorze.
  • _map_columns odrzuca tabele metadanych (dane bankowe, terminy
    płatności, tabele "Indeks dostawy" itp.) bez kolumny liczbowej —
    wcześniej trafiały jako fałszywe pozycje faktury.
  • Dodatkowe wzorce sum brutto ("Wartość sprzedaży brutto",
    "Total EUR ..." bez "Incl./Excl. VAT").
  • Wykrywanie waluty uwzględnia symbol/deklarację ("Currency EUR", "€")
    zamiast pierwszego przypadkowego 3-literowego kodu w tekście.

Wymagania:  pip install pdfplumber openpyxl requests beautifulsoup4

Użycie:
  python categorize6.py                   # bieżący folder
  python categorize6.py faktury/          # podany folder
  python categorize6.py f1.pdf f2.pdf ... # konkretne pliki
  python categorize6.py --bez-internetu   # tylko słownik
"""

import re, sys, glob, os, time, urllib.parse
from datetime import datetime
from pathlib import Path
from collections import defaultdict

try:
    import requests
    from bs4 import BeautifulSoup
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False

import pdfplumber
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ══════════════════════════════════════════════════════════════
#  KATEGORIE I SŁOWNIKI
# ══════════════════════════════════════════════════════════════

KATEGORIE = {
    "sygnalizacja_pozaru": "🔴 Sygnalizacja pożaru",
    "elektryka":           "⚡ Elektryka",
    "automatyka":          "🔧 Automatyka / Sterowniki",
    "hydraulika":          "💧 Hydraulika / P.poż",
    "gazownictwo":         "🔥 Gazownictwo",
    "transport":           "🚚 Transport / Logistyka",
    "teletechnika":        "📡 Teletechnika / IT",
    "mechanika":           "⚙️ Mechanika / Ślusarka",
    "obudowy_szafy":       "🗃️ Obudowy / Szafy elektryczne",
    "narzedzia":           "🔨 Narzędzia / Materiały pomocnicze",
    "ogolnobudowlane":     "🏗️ Ogólnobudowlane",
    "inne":                "❓ Inne / Nieokreślone",
}

KEYWORD_RULES: dict[str, list[str]] = {
    "sygnalizacja_pozaru": [
        # Centrale, czujniki
        "sygnalizator", "saoz", "czujnik dymu", "czujnik ciepła", "czujnik pożar",
        "centrala pożar", "centrala poż", "centrala po ", "fc721", "fdci", "fdcio", "fdch",
        "konwencjonalny", "adresowalny", "pętlowy", "pętlowa", "linia dozorowa",
        "ręczny ostrzegacz", "syrena", "flaszer", "lampka alarmowa",
        "akumulator 12v", "pss 50va",
        "wkład modułu", "obudowa modułu",
        # Kody produktów Siemens SAP
        "fa2003", "s54400", "s54312", "fdch221", "fdcio222", "fdci222", "fc721-zz",
        # Klapy / napędy pożarowe
        "klapa pożarowa", "klapa dymna", "klapa odcinająca", "napęd klapy",
        "mwffid", "mwf", "bfl24", "bfl", "belimo", "fire damper", "smoke damper",
        # Przekaźniki SAP
        "pz-828", "przekaźnik przelania",
        # Angielskie — SAP / tryskacze
        "fire alarm", "smoke detector", "solenoid", "nozzle calibrated",
        "alarm valve", "waterflow indicator", "retard chamber", "supervisory switch",
        "fire suppression", "sprinkler", "dry pipe", "dpv", "wet alarm",
        "orifice", "nozzle", "accelerator", "deluge",
    ],
    "elektryka": [
        "wyłącznik nadprądowy", "wyłącznik różnicowy", "bezpiecznik",
        "rozłącznik izolacyjny", "rozłącznik", "is-25", "pl6-b", "hn-c",
        "przewód", "kabel", "drut", "listwa zaciskowa",
        "gniazdo elektryczne", "wtyczka",
        "transformator", "zasilacz", "pss ", "ups ",
        "lampka kontrolna", "główka lampki", "element z diodą", "led",
        "łącznik mocujący", "m22-", "przycisk sterowniczy",
        "tablica rozdzielcza", "rozdzielnia",
        "cable kit", "cable", "wire", "manosw", "pressure switch",
    ],
    "automatyka": [
        "przekaźnik miniaturowy", "przekaźnik czasowy", "przekaźnik bistabilny",
        "przekaźnik", "gniazdo przekaźnika", "gniazdo do serii",
        "sterownik plc", "plc", "przetwornik", "regulator",
        "falownik", "softstart", "stycznik", "przekaźnik termiczny",
        "40.52", "95.05 spa", "m22-a", "actuator",
    ],
    "obudowy_szafy": [
        "obudowa metalowa", "szafa elektryczna", "szafa sterownicza",
        "szafka", "rozdzielnica", "ip66", "ip65", "ip54",
        "gt50", "puszkowanie", "kanał kablowy",
        "korytko kablowe", "drabinka kablowa",
        "cabinet", "enclosure",
        # UWAGA: "bracket/rail" do mechaniki, nie szaf
    ],
    "hydraulika": [
        "rura", "zawór", "armatura", "pompa wody", "pompa obiegowa",
        "kolektor", "trójnik", "uszczelka",
        "wodomierz", "hydrant", "tryskacz", "zraszacz",
        "klapa przeciwpożarowa", "przepustnica", "filtr skośny", "zawór zwrotny",
        # EN fire suppression valves / fittings
        "grooved butterfly valve", "swing check valve", "gate valve", "butterfly valve",
        "check valve", "alarm gong", "water motor", "manifold",
        "hose", "grooved", "os&y", "obejm", "kotw",
    ],
    "gazownictwo": [
        "rura gazowa", "zawór gazowy", "gazomierz", "regulator gazu",
        "armatura gazowa", "instalacja gazowa",
    ],
    "transport": [
        "spedycja", "transport", "dostaw", "przewóz", "kurier",
        "przesyłka", "logistyka",
        "shipping", "freight", "handling charge", "carriage",
    ],
    "teletechnika": [
        "router", "kabel sieciowy", "patchcord", "patch panel",
        "szafa rack", "kamera", "nvr", "dvr",
        "czujnik ruchu", "access point", "antena",
    ],
    "mechanika": [
        "śruba", "nakrętka", "podkładka", "kołek", "wiertło",
        "wspornik", "uchwyt", "konsol", "profil stalowy",
        "cyl bracket", "cyl rail", "rail end cover",
        "switch kit", "limit switch", "mounting bracket",
        "gwintowan", "kątownik", "klamr", "szyna montaż",
    ],
    "narzedzia": [
        "taśma", "uszczelniacz", "silikon", "klej", "folia",
        "rękawice", "okulary", "kask", "kombinezon",
        "wiertarka", "klucz", "śrubokręt", "miara",
    ],
    "ogolnobudowlane": [
        "cement", "beton", "tynk", "gips", "farba", "lakier",
        "drzwi", "okno", "podłoga", "płytka",
        "izolacja", "wełna mineralna", "styropian",
    ],
}

# Niektóre PDF-y (zwłaszcza starsze/ERP-owe) zapisują polskie znaki bez
# ogonków/kresek na części słów (np. "PODKLADKA" zamiast "PODKŁADKA" w tej
# samej fakturze, gdzie inne słowa mają poprawne znaki) — prawdopodobnie
# błąd czcionki/eksportu po stronie wystawcy, nie da się tego przewidzieć
# wzorcem. Dopasowanie słów kluczowych ignoruje więc ogonki po obu stronach.
_PL_DIACRITICS = str.maketrans("ąćęłńóśźż", "acelnoszz")

def _strip_diacritics(s: str) -> str:
    return s.translate(_PL_DIACRITICS)

_KEYWORD_RULES_NORM: dict[str, list[tuple[str, str]]] = {
    kat: [(_strip_diacritics(k), k) for k in kws] for kat, kws in KEYWORD_RULES.items()
}

PKWIU_RULES: dict[str, str] = {
    "26.30.50": "sygnalizacja_pozaru",   # Aparatura alarmowa
    "27.20.22": "sygnalizacja_pozaru",   # Akumulatory (do SAP)
    "27.12.40": "sygnalizacja_pozaru",   # Aparatura automatyki/detekcji
    "22.29.29": "obudowy_szafy",         # Wyroby z tworzyw sztucznych
    "27.12.31": "obudowy_szafy",         # Tablice / szafy rozdzielcze
    "27.51":    "elektryka",
    "27.12":    "elektryka",
    "28.29":    "automatyka",
    "28.14":    "hydraulika",            # Armatura / zawory
    "26.30":    "teletechnika",          # Sprzęt (tele)komunikacyjny (poza 26.30.50 wyżej)
    "25.94":    "mechanika",             # Wyroby złączne i śruby
    "25.73":    "narzedzia",             # Narzędzia
    "20.30":    "ogolnobudowlane",       # Farby, lakiery i podobne środki pokrywające
    "49.41":    "transport",             # Transport drogowy towarów
    "52.29":    "transport",             # Pozostała działalność wspomagająca transport
    "53.20":    "transport",             # Pozostała działalność pocztowa i kurierska
}

WEB_HINTS: dict[str, list[str]] = {
    "sygnalizacja_pozaru": ["fire alarm", "sygnalizacja pożaru", "pożarowy", "centrala pożarowa",
                             "czujka", "detekcja dymu", "system sap", "fire suppression"],
    "elektryka":           ["instalacja elektryczna", "elektryka", "wyłącznik", "bezpiecznik",
                             "rozdzielnia", "zasilanie"],
    "automatyka":          ["automatyka przemysłowa", "sterownik", "przekaźnik", "plc"],
    "obudowy_szafy":       ["obudowa elektryczna", "szafa elektryczna", "rozdzielnica", "ip66"],
    "hydraulika":          ["hydraulika", "instalacja wod-kan", "rury", "armatura", "pompa",
                             "zawory", "sprinkler", "tryskacz"],
    "transport":           ["transport", "spedycja", "dostawa", "logistyka"],
}


# ══════════════════════════════════════════════════════════════
#  KATEGORYZACJA – 3 WARSTWY
# ══════════════════════════════════════════════════════════════

def _cat_keywords(opis, indeks="", pkwiu="") -> tuple[str, int, str]:
    tekst = _strip_diacritics((opis + " " + indeks + " " + pkwiu).lower())
    best, score, match = "inne", 0, ""
    for kat, kws in _KEYWORD_RULES_NORM.items():
        hits = [orig for norm, orig in kws if norm in tekst]
        s = len(hits)*20 + (10 if hits else 0)
        if s > score:
            score, best, match = s, kat, ", ".join(hits[:3])
    if score >= 30:
        return best, min(92, 50+score), f"słowo: '{match}'"
    if pkwiu:
        pk = pkwiu.strip().replace(" ","")
        for prefix, kat in sorted(PKWIU_RULES.items(), key=lambda x:-len(x[0])):
            if pk.startswith(prefix):
                return kat, 85, f"PKWiU {pk}"
    if score > 0:
        return best, min(60, 40+score), f"słowo(słabe): '{match}'"
    return "inne", 0, "brak"

_web_cache: dict = {}

def _cat_web(opis, indeks="") -> tuple[str, int, str]:
    if not WEB_AVAILABLE: return "inne", 0, "brak web"
    q = re.sub(r'\b(do|ze|z|w|na|dla|lub|oraz|szt|pcs|mm|cm|m)\b', '', opis, flags=re.I).strip()
    q = f"{q} {indeks}".strip()
    if len(q) < 5: return "inne", 0, "za krótkie"
    key = q[:80].lower()
    if key not in _web_cache:
        hdrs = {"User-Agent":"Mozilla/5.0","Accept-Language":"pl-PL,pl;q=0.9,en;q=0.5"}
        snips = []
        try:
            r = requests.get(f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(q+' zastosowanie')}&kl=pl-pl",
                             headers=hdrs, timeout=8)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                snips = [el.get_text(strip=True) for el in soup.select(".result__snippet")[:5]]
        except Exception: pass
        _web_cache[key] = " ".join(snips).lower()
        time.sleep(0.8)
    combined = _web_cache[key]
    if not combined: return "inne", 0, "brak wyników"
    best, score, hint = "inne", 0, ""
    for kat, hints in WEB_HINTS.items():
        hits = [h for h in hints if h in combined]
        s = len(hits)*25
        if s > score: score, best, hint = s, kat, ", ".join(hits[:2])
    return (best, min(80, 40+score), f"web:'{hint}'") if score else ("inne", 15, "web:brak")

def _cat_heuristic(opis, indeks="") -> tuple[str, int, str]:
    t = (opis+" "+indeks).lower()
    if re.search(r'\b(s5\d{4}|a5q\d{8}|fd[cchi])', t): return "sygnalizacja_pozaru", 70, "indeks Siemens SAP"
    if re.search(r'\bm22-',   t): return "elektryka",    65, "seria M22"
    if re.search(r'spedycja|dostawa|transport|kurier|shipping|freight|handling',t): return "transport", 90, "transport"
    if re.search(r'obudowa.*(ip\d+|metal)|(ip\d{2}).*(obudow|szaf)', t): return "obudowy_szafy", 75, "obudowa+IP"
    if re.search(r'\b(kabel|przewód|cable|wire|nym|lsoh)\b', t): return "elektryka",    70, "kabel"
    if re.search(r'\b(valve|zawór|armatura|hose|rura|zawor)\b', t): return "hydraulika",  65, "armatura"
    return "inne", 10, "fallback"

def kategoryzuj(opis, indeks="", pkwiu="", use_web=True) -> dict:
    opis, indeks, pkwiu = str(opis or "").strip(), str(indeks or "").strip(), str(pkwiu or "").strip()
    k1, p1, r1 = _cat_keywords(opis, indeks, pkwiu)
    if p1 >= 70: return _wynik(k1, p1, r1, "słownik")
    if use_web and WEB_AVAILABLE:
        k2, p2, r2 = _cat_web(opis, indeks)
        if p2 >= 40 and p2 > p1: return _wynik(k2, p2, r2, "internet")
    k3, p3, r3 = _cat_heuristic(opis, indeks)
    if p3 >= p1: return _wynik(k3, p3, r3, "heurystyka")
    return _wynik(k1, p1 or 5, r1 or "brak", "słownik")

def _wynik(klucz, pewnosc, powod, zrodlo) -> dict:
    return {"kategoria_klucz": klucz, "kategoria_nazwa": KATEGORIE.get(klucz,"❓ Inne"),
            "pewnosc": pewnosc, "powod": powod, "zrodlo_dopasowania": zrodlo}


# ══════════════════════════════════════════════════════════════
#  NARZĘDZIA POMOCNICZE
# ══════════════════════════════════════════════════════════════

# Jedna poprawnie sformatowana kwota pieniężna: grupy tysięcy (spacja/kropka/
# przecinek) + dokładnie 2 cyfry grosza. Używane zamiast łapczywego
# "[\d\s.,]+" przy wyszukiwaniu sum na fakturze — to ostatnie potrafiło
# połknąć przypadkowe sąsiednie liczby (np. nagłówek kolumny w tabeli tuż
# nad pierwszym wierszem pozycji) jako jedną wielką, bez sensu kwotę.
_MONEY = r"(?:\d{1,3}(?:[ .,]\d{3})*|\d+)[.,]\d{2}"

# Górna granica prawdopodobieństwa dla JEDNEJ kwoty/ilości na fakturze —
# żadna pozycja ani suma faktury w tej domenie (sprzęt/usługi ppoż.) nie
# sięga nawet pojedynczych milionów. Powyżej tego to prawie zawsze sklejone
# przez pomyłkę sąsiednie liczby z komórki tabeli (np. gdy pdfplumber zleje
# dwa wiersze w jedną komórkę) — regex łapiący "ciąg cyfr" wtedy łyka je
# jako jedną, astronomiczną wartość zamiast rozpoznać błąd. Lepiej pokazać
# brak danych niż wymyśloną liczbę, która zawyża sumy/wykresy o dwadzieścia
# rzędów wielkości.
_MAX_PLAUSIBLE_AMOUNT = 10_000_000

def clean_amount(text) -> float | None:
    """Obsługuje PL (1.234,56) i EN (1,234.56) i spacje jako separator tysięcy."""
    if text is None: return None
    text = str(text).replace('\n', ' ')
    text = re.sub(r'[\d.,]+\s*%', '', text)     # usuń wartości procentowe
    # Dopasuj cały ciąg cyfr, dopuszczając oba separatory (np. "8,631.94"),
    # ale tylko gdy separator jest bezpośrednio otoczony cyframi.
    m = re.search(r'-?\d(?:\d|[  .,](?=\d))*', text)
    if not m: return None
    raw = m.group().replace(' ','').replace('\xa0','')
    if ',' in raw and '.' in raw:
        raw = (raw.replace('.','').replace(',','.') if raw.rfind(',') > raw.rfind('.')
               else raw.replace(',',''))
    elif ',' in raw and raw.count(',') == 1:
        raw = raw.replace(',','.')
    elif ',' in raw:                             # 1,234,567
        parts = raw.split(','); raw = "".join(parts[:-1])+"."+parts[-1]
    elif raw.count('.') > 1:                     # 1.234.567
        parts = raw.split('.'); raw = "".join(parts[:-1])+"."+parts[-1]
    try:
        value = float(raw)
    except Exception:
        return None
    return value if abs(value) <= _MAX_PLAUSIBLE_AMOUNT else None

def find_value(text, *patterns):
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE | re.MULTILINE)
        if m: return m.group(1).strip()
    return None


def _looks_like_real_invoice_number(value: str | None) -> bool:
    """Prawdziwy numer faktury jest krótki i zawsze ma choć jedną cyfrę.
    Bez tej walidacji zbyt zachłanny regex fallback (dla nieznanych
    dostawców, bez dopasowania etykiety 'Numer faktury') potrafił złapać
    przypadkowe, sąsiadujące słowo (np. urwany fragment adresu "Str",
    albo sam placeholder "-") jako numer faktury. Dwie zupełnie różne
    faktury tego samego dostawcy dostawały wtedy ten sam śmieciowy
    "numer", co dawało fałszywe ostrzeżenia o duplikacie."""
    if not value:
        return False
    value = value.strip()
    if not value or len(value) > 40 or len(value.split()) > 4:
        return False
    return any(ch.isdigit() for ch in value)


def _looks_like_real_vendor_name(value: str | None) -> bool:
    """Prawdziwa nazwa sprzedawcy to kilka słów, opcjonalnie z formą
    prawną (Sp. z o.o., S.A., GmbH...) — zbyt zachłanny fallback (szukanie
    dowolnej linii z formą prawną w pierwszych ~600 znakach) potrafił
    zamiast tego złapać całe zdanie z klauzuli Ogólnych Warunków albo
    pomylony blok Nabywcy, jeśli tamten fragment wspominał nazwę firmy
    wcześniej niż właściwy nagłówek 'Sprzedawca'."""
    if not value:
        return False
    value = value.strip()
    if not value or len(value) > 90 or len(value.split()) > 8:
        return False
    return not value.endswith(":")

def _clean_opis(text: str) -> str:
    """Usuwa kody PKWiU oraz zbędne białe znaki z opisu."""
    text = re.sub(r'\b\d{2}\.\d{2}\.\d{2}\.\d\b', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def _extract_pkwiu(text: str) -> str:
    m = re.search(r'\b(\d{2}\.\d{2}\.\d{2}\.\d)\b', text)
    return m.group(1) if m else ""


# ══════════════════════════════════════════════════════════════
#  PARSOWANIE TABEL – UNIWERSALNE
# ══════════════════════════════════════════════════════════════

# Wzorce nagłówków kolumn (PL + EN)
_COL_RE = {
    'lp':              r'^(?:lp\.?|nr\.?|l\.p\.?|poz\.?|no\.?|pos\.?|#|item\s*no\.?)$',
    'opis':            r'nazwa|opis|towar|us[łl]ug|artyk|produkt|przedmiot|description|goods|service|particulars',
    'indeks':          r'indeks|kod\b|symbol|katalog|ref\b|index|code\b|cat\.?|part\s*no|item\s*number|item\s*no\b|product\s*code',
    'pkwiu':           r'pkwiu|pkw\.?iu',
    'ilosc':           r'ilo[śs][ćc]|qty|quantity|count\b',
    'jm':              r'^(?:jm|j\.m\.?|jedn|miara|unit|uom)$',
    'cena_netto':      r'cena\s*netto|c\.?\s*netto|unit\s*price|unit\s*cost|price\s*each|sales\s*price|cena\s*jedn',
    'wartosc_netto':   r'wart[oó][śs][ćc]\s*(?:sprzeda[żz]y\s*)?netto|wart\.?\s*netto|net\s*(?:amount|value|total)|^amount',
    'stawka_vat':      r'^vat$|stawka\s*vat|stawka\s*podatku|%\s*vat|vat\s*%|tax\s*rate',
    'kwota_vat':       r'kwota\s*vat|kwota\s*podat|podatek|tax\s*amount|vat\s*amount',
    'wartosc_brutto':  r'brutto|wart[oó][śs][ćc]\s*brutto|gross|total(?:\s*amount)?|amount\s*(?:inc|incl)',
}

def _map_columns(header_row: list) -> dict | None:
    if not header_row: return None
    mapping: dict[str, int] = {}
    for i, cell in enumerate(header_row):
        if cell is None: continue
        c = str(cell).lower().strip().replace('\n', ' ')
        for field, pattern in _COL_RE.items():
            if re.search(pattern, c):
                # Jedna kolumna = jedno pole. Bez tego np. "Stawka podatku"
                # (stawka VAT) potrafiła jednocześnie trafić do kwota_vat
                # (przez rdzeń "podat"), nadpisując właściwą kolumnę kwotową.
                if field in ('lp', 'indeks', 'pkwiu', 'ilosc', 'jm',
                             'cena_netto', 'wartosc_netto', 'stawka_vat',
                             'kwota_vat', 'wartosc_brutto'):
                    mapping.setdefault(field, i)
                else:  # opis – może nadpisać słabsze dopasowanie
                    mapping.setdefault('opis', i)
                break
    if 'opis' not in mapping and 'indeks' in mapping:
        mapping['opis'] = mapping['indeks']
    if 'opis' not in mapping:
        return None
    # Tabela pozycji faktury musi zawierać choć jedną kolumnę liczbową
    # (ilość/cena/wartość) — inaczej to zwykła tabela metadanych
    # (dane bankowe, terminy płatności, dane sprzedawcy itp.), nie pozycje.
    value_fields = ('ilosc', 'cena_netto', 'wartosc_netto',
                     'kwota_vat', 'wartosc_brutto')
    if not any(f in mapping for f in value_fields):
        return None
    return mapping

def _row_to_item(row: list, col_map: dict, lp_counter: int) -> dict | None:
    def g(field):
        idx = col_map.get(field)
        if idx is None or idx >= len(row): return None
        v = row[idx]
        return str(v).strip().replace('\n', ' ') if v is not None else None

    opis = g('opis')
    if not opis or len(opis.strip()) < 2: return None
    if re.match(r'^(?:razem|suma|og[oó][łl]em|total|subtotal|lp\.?|nr\.?|opis|nazwa|product)',
                opis.strip(), re.I): return None

    try:   lp = int(re.sub(r'\D','', g('lp') or '') or lp_counter)
    except: lp = lp_counter

    wartosc_netto  = clean_amount(g('wartosc_netto'))
    stawka_vat     = g('stawka_vat')
    kwota_vat      = clean_amount(g('kwota_vat'))
    wartosc_brutto = clean_amount(g('wartosc_brutto'))

    # Niektóre formaty (np. polskie e-Faktury/KSeF) podają w tabeli pozycji
    # tylko stawkę VAT i wartość netto, bez osobnych kolumn na kwotę VAT
    # i brutto — doliczamy je, żeby raport/kategoryzacja miały pełne dane.
    if wartosc_netto is not None and kwota_vat is None and wartosc_brutto is None and stawka_vat:
        rate_m = re.search(r'(\d+(?:[.,]\d+)?)\s*%', stawka_vat)
        if rate_m:
            rate = float(rate_m.group(1).replace(',', '.')) / 100
            kwota_vat = round(wartosc_netto * rate, 2)
            wartosc_brutto = round(wartosc_netto + kwota_vat, 2)

    return {
        "lp": lp, "opis": _clean_opis(opis),
        "indeks": g('indeks') or '',
        "pkwiu":  g('pkwiu')  or _extract_pkwiu(opis),
        "ilosc":  clean_amount(g('ilosc')),
        "jm":     g('jm') or 'szt',
        "cena_netto":    clean_amount(g('cena_netto')),
        "wartosc_netto": wartosc_netto,
        "stawka_vat":    stawka_vat,
        "kwota_vat":     kwota_vat,
        "wartosc_brutto":wartosc_brutto,
    }

def parse_all_tables(tables: list, text: str) -> list[dict]:
    """
    Przetwarza WSZYSTKIE tabele ze wszystkich stron.
    Dedulikuje po kluczu (opis, ilosc, cena_netto).
    """
    all_items: list[dict] = []
    seen: set = set()
    lp_global = 0

    for table in tables:
        if not table or len(table) < 2: continue

        # Szukaj wiersza nagłówkowego w pierwszych 5 wierszach
        col_map = None
        data_start = 0
        for i, row in enumerate(table[:5]):
            col_map = _map_columns(row)
            if col_map:
                data_start = i + 1
                break
        if not col_map: continue

        prev_item = None
        for row in table[data_start:]:
            if not row or all(c is None or str(c).strip()=='' for c in row): continue
            lp_global += 1
            item = _row_to_item(row, col_map, lp_global)
            if item:
                key = (item['opis'][:40], item['ilosc'], item['cena_netto'])
                if key not in seen:
                    seen.add(key)
                    all_items.append(item)
                    prev_item = item
            elif prev_item:
                # Wiersz kontynuacji (np. TIM – opis na następnym wierszu)
                non_empty = [str(c).strip() for c in row if c and str(c).strip()]
                if 1 <= len(non_empty) <= 3:
                    cont = ' '.join(non_empty)
                    if not re.match(r'^(?:Razem|Total|EAN|PKWiU|AL:|ECCN:)',cont,re.I):
                        # Uzupełnij opis, jeśli był taki sam jak indeks (brak opisu)
                        if prev_item['opis'] == prev_item.get('indeks','') or len(prev_item['opis']) < 5:
                            prev_item['opis'] = _clean_opis(cont)

    return all_items


# ══════════════════════════════════════════════════════════════
#  PARSOWANIE TEKSTU – PARSERY SPECYFICZNE + UNIWERSALNY
# ══════════════════════════════════════════════════════════════

def _lines_between(text: str, start_re: str, end_re: str) -> list[str]:
    """Zwraca linie tekstu między dwoma wzorcami regex."""
    lines = text.split('\n')
    inside = False
    result = []
    for line in lines:
        if not inside and re.search(start_re, line, re.I): inside = True; continue
        if inside:
            if re.search(end_re, line, re.I): break
            result.append(line)
    return result


def parse_text_tim(text: str) -> list[dict]:
    """
    TIM: item na jednej linii (nr indeks ilość jm cena net vat% kvat brutto),
         opis produktu na kolejnych liniach (może zawierać kod PKWiU).
    """
    lines = text.split('\n')
    items = []
    item_pat = re.compile(
        r'^(\d{1,3})\s+(\S+)\s+([\d,]+)\s+(\w+\.?)\s+([\d,]+)\s+([\d,]+)\s+(\d+)%\s+([\d,]+)\s+([\d,]+)'
    )
    i = 0
    while i < len(lines):
        m = item_pat.match(lines[i].strip())
        if m:
            # Zbierz opisy do następnego itemu lub RAZEM
            desc_parts = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt: j += 1; continue
                if item_pat.match(nxt) or re.match(r'^(?:RAZEM|Razem|Total)', nxt, re.I): break
                desc_parts.append(nxt)
                j += 1

            desc_raw = ' '.join(desc_parts)
            pkwiu    = _extract_pkwiu(desc_raw)
            opis     = _clean_opis(desc_raw) or m.group(2)

            items.append({
                "lp": int(m.group(1)), "opis": opis, "indeks": m.group(2), "pkwiu": pkwiu,
                "ilosc": clean_amount(m.group(3)), "jm": m.group(4),
                "cena_netto": clean_amount(m.group(5)), "wartosc_netto": clean_amount(m.group(6)),
                "stawka_vat": m.group(7)+"%", "kwota_vat": clean_amount(m.group(8)),
                "wartosc_brutto": clean_amount(m.group(9)),
            })
            i = j
        else:
            i += 1
    return items


def parse_text_siemens(text: str) -> list[dict]:
    """
    Siemens: 001000 KODMAT XX  N SZT  3.079,10  23,00 %  3.079,10
             OpisproduktuNazwaModelu
             PKWiU: XX.XX.XX.X
    """
    pat = re.compile(
        r'^(\d{6})\s+(\S+)\s+\w{2}\s+(\d+)\s+SZT\s+([\d.,]+)\s+23[.,]\d+\s*%\s+([\d.,]+)',
        re.M | re.I
    )
    items = []
    for m in pat.finditer(text):
        pos = m.end()
        rest = text[pos:pos+400]
        om = re.match(r'[ \t]*\n(.+?)(?=\n\d{6}\s|\nWartość|\nVAT\s|\Z)', rest, re.DOTALL)
        raw_desc = om.group(1).strip().replace('\n',' ') if om else m.group(2)
        pkwiu = _extract_pkwiu(raw_desc)
        opis  = _clean_opis(re.sub(r'(?:PKWiU|Materiał zamówiony|EAN|AL:|ECCN:)[^\n]*', '', raw_desc))
        v_net = clean_amount(m.group(5))
        items.append({
            "lp": len(items)+1, "opis": opis or m.group(2), "indeks": m.group(2), "pkwiu": pkwiu,
            "ilosc": float(m.group(3)), "jm": "SZT",
            "cena_netto": clean_amount(m.group(4)), "wartosc_netto": v_net,
            "stawka_vat": "23%",
            "kwota_vat":    round(v_net*0.23, 2) if v_net else None,
            "wartosc_brutto": round(v_net*1.23, 2) if v_net else None,
        })
    return items


def parse_text_mercor(text: str) -> list[dict]:
    """
    Mercor: 1 KOD JM ILOŚĆ CENA PLN NETTO VAT% KWOTA_VAT BRUTTO
            Opis produktu (następna linia)
    Liczby mają polski separator tysięcy (spacja: "1 560,30"), więc nie
    da się rozdzielić pól samym `\\s+` — trzeba je łapać jako osobne grupy.
    """
    lines = text.split('\n')
    items = []
    pat = re.compile(
        r'^(\d+)\s+(\S+)\s+(\w+\.?)\s+([\d,]+)\s+'      # lp, indeks, jm, ilość
        r'([\d\s,]+?)\s+PLN\s+'                          # cena netto
        r'([\d\s,]+?)\s+(\d+)%\s+'                       # wartość netto, stawka
        r'([\d\s,]+?)\s+([\d\s,]+?)\s*$'                 # kwota VAT, wartość brutto
    )
    for i, line in enumerate(lines):
        m = pat.match(line)
        if not m: continue

        # Opis: następna linia (jeśli nie jest kolejnym itemem / Razem)
        opis = m.group(2)  # fallback: symbol
        if i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt and not re.match(r'^\d+\s+\S|\s*Razem|Sprawę', nxt):
                opis = nxt

        items.append({
            "lp": int(m.group(1)), "opis": opis, "indeks": m.group(2), "pkwiu": "",
            "ilosc": clean_amount(m.group(4)),
            "jm": m.group(3),
            "cena_netto":    clean_amount(m.group(5)),
            "wartosc_netto": clean_amount(m.group(6)),
            "stawka_vat":    m.group(7) + "%",
            "kwota_vat":     clean_amount(m.group(8)),
            "wartosc_brutto":clean_amount(m.group(9)),
        })
    return items


def parse_text_euroterm(text: str) -> list[dict]:
    """Euroterm: LP KOD PKWIU QTY JM CENA NETTO VAT%  + opis na następnej linii."""
    lines = text.split('\n')
    items = []
    pat = re.compile(r'^(\d+)\s+(\S+)\s+([\d.]+)\s+([\d,]+)\s+(\w+\.?)\s+([\d,]+)\s+([\d,]+)\s+(\d+)%')
    for i, line in enumerate(lines):
        m = pat.match(line.strip())
        if not m: continue
        opis = ""
        if i+1 < len(lines):
            nxt = lines[i+1].strip()
            if nxt and not re.match(r'^\d+\s|\s*Forma|\s*Przelew|\s*Stawka', nxt):
                opis = nxt
        v = clean_amount(m.group(7))
        vr = clean_amount(m.group(8))
        vv = round(v*vr/100, 2) if v and vr else None
        items.append({
            "lp": int(m.group(1)), "opis": opis or m.group(2), "indeks": m.group(2),
            "pkwiu": m.group(3),
            "ilosc": clean_amount(m.group(4)), "jm": m.group(5),
            "cena_netto": clean_amount(m.group(6)), "wartosc_netto": v,
            "stawka_vat": m.group(8)+"%", "kwota_vat": vv,
            "wartosc_brutto": round(v+vv, 2) if v and vv else None,
        })
    return items


def parse_text_fire_eater(text: str) -> list[dict]:
    """
    Fire Eater (EN): ITEMNO Description qty pcs [DISC%]  price  amount
    Kody: 6-cyfrowe, 5-cyfrowe (63020) i alfanumeryczne (210204-8).
    Pozycje typu "Handling charge"/"Shipping" nie mają rabatu (DISC% opcjonalny).
    """
    pat = re.compile(
        r'^([\w][\w\-]*)\s+(.+?)\s+([\d,]+)\s+pcs\s+(?:[\d.]+\s*%\s+)?([\d,]+)\s+([\d,]+)',
        re.M)
    items = []
    for m in pat.finditer(text):
        opis = m.group(2).strip()
        if re.search(r'net\s*weight|hs\s*code|country\s*of', opis, re.I): continue
        if re.search(r'item\s*number|description', opis, re.I): continue
        items.append({
            "lp": len(items)+1, "opis": opis, "indeks": m.group(1), "pkwiu": "",
            "ilosc": clean_amount(m.group(3)), "jm": "pcs",
            "cena_netto": clean_amount(m.group(4)),
            "wartosc_netto": clean_amount(m.group(5)),
            "stawka_vat": "0%", "kwota_vat": 0.0,
            "wartosc_brutto": clean_amount(m.group(5)),
        })
    return items


def parse_text_tyco(text: str) -> list[dict]:
    """Tyco: LP MATCODE QTY EA QTY EA UNIT_PRICE 1 EA TOTAL + opis na następnej linii."""
    pat = re.compile(
        r'^(\d+)\s+(\S+)\s+(\d+)\s+EA\s+\d+\s+EA\s+([\d.,]+)\s+1\s+EA\s+([\d.,]+)',
        re.M)
    items = []
    for m in pat.finditer(text):
        pos = m.end()
        om = re.match(r'[ \t]*\n(.+?)(?=\n\d+\s+\S|\nSurcharge|\nTotal|\Z)', text[pos:pos+350], re.DOTALL)
        opis = om.group(1).strip().replace('\n',' ') if om else m.group(2)
        v = clean_amount(m.group(5))
        items.append({
            "lp": int(m.group(1)), "opis": opis, "indeks": m.group(2), "pkwiu": "",
            "ilosc": float(m.group(3)), "jm": "EA",
            "cena_netto": clean_amount(m.group(4)), "wartosc_netto": v,
            "stawka_vat": "0%", "kwota_vat": 0.0, "wartosc_brutto": v,
        })
    return items


def parse_text_universal(text: str) -> list[dict]:
    """
    Fallback dla nieznanych dostawców bez tabel.
    Szuka bloku między nagłówkiem kolumn a wierszem podsumowującym.
    Obsługuje format: LP [KOD] OPIS QTY JM CENA NET  VAT  BRUTTO
    """
    lines = text.split('\n')
    # Znajdź nagłówek tabeli
    hdr_idx = -1
    for i, line in enumerate(lines):
        if (re.search(r'(?:Lp|Nr|Poz|No|#)\b', line, re.I) and
            re.search(r'(?:Nazwa|Opis|Description|Price|Cena)', line, re.I) and
            re.search(r'(?:Cena|Ilość|Qty|Price|Amount)', line, re.I)):
            hdr_idx = i; break
    if hdr_idx < 0: return []

    items = []
    pat = re.compile(r'^(\d{1,3})\s+(.{4,}?)\s+([\d,]+)\s+(\w+\.?)\s+([\d,]+)\s+([\d,]+)\s+(\d+)%\s+([\d,]+)\s+([\d,]+)')
    i = hdr_idx + 1
    while i < len(lines):
        line = lines[i].strip()
        if re.match(r'(?:Razem|RAZEM|Total|Subtotal|Do zapłaty|Net amount)', line, re.I): break
        m = pat.match(line)
        if m:
            items.append({
                "lp": int(m.group(1)), "opis": _clean_opis(m.group(2)), "indeks": "",
                "pkwiu": "", "ilosc": clean_amount(m.group(3)), "jm": m.group(4),
                "cena_netto": clean_amount(m.group(5)), "wartosc_netto": clean_amount(m.group(6)),
                "stawka_vat": m.group(7)+"%", "kwota_vat": clean_amount(m.group(8)),
                "wartosc_brutto": clean_amount(m.group(9)),
            })
        i += 1
    return items


# ══════════════════════════════════════════════════════════════
#  DETEKCJA DOSTAWCY
# ══════════════════════════════════════════════════════════════

def detect_vendor(text: str) -> str:
    if re.search(r'TIM S\.A\.',              text):               return "tim"
    if re.search(r'Sonepar',                text):               return "sonepar"
    if re.search(r'Siemens Sp\. z o\.o\.',  text):               return "siemens"
    if re.search(r'MERCOR|mercor\.com\.pl', text, re.I):         return "mercor"
    if re.search(r'EUROTERM|euroterm24',    text, re.I):         return "euroterm"
    if re.search(r'Fire Eater|fire-eater\.com', text, re.I):    return "fire_eater"
    if re.search(r'Tyco Building Services', text, re.I):        return "tyco"
    if re.search(r'[Rr]apidrop',           text):               return "rapidrop"
    # Krajowy System e-Faktur (KSeF) — obowiązkowy krajowy format e-faktur
    # w Polsce, używany przez dowolnego wystawcę (nie tylko powyższych).
    # Ma stały układ nagłówka, więc warto go rozpoznać osobno zamiast
    # wpadać w generyczny fallback albo (gorzej) mylić z jednym z powyższych
    # tylko dlatego, że tamta faktura też przechodzi przez KSeF.
    if re.search(r'Krajowy System e-Faktur|Numer KSEF', text):    return "ksef_generic"
    return "generic"


# ══════════════════════════════════════════════════════════════
#  EKSTRAKCJA NAGŁÓWKA FAKTURY
# ══════════════════════════════════════════════════════════════

def _column_texts(words: list, page_width: float) -> tuple[str, str]:
    """
    Dzieli słowa strony (pdfplumber `page.extract_words()`) na tekst lewej
    i prawej kolumny wg pozycji x0. Potrzebne dla layoutów dwukolumnowych
    (np. blok "Sprzedawca / Nabywca" na fakturach KSeF), gdzie zwykłe
    `extract_text()` miesza pola z obu kolumn w jednej linii.
    """
    if not words:
        return "", ""
    mid = page_width / 2

    def to_text(ws):
        lines: dict[int, list] = {}
        for w in ws:
            lines.setdefault(round(w["top"]), []).append(w)
        out = []
        for top in sorted(lines):
            row = sorted(lines[top], key=lambda w: w["x0"])
            out.append(" ".join(w["text"] for w in row))
        return "\n".join(out)

    left  = [w for w in words if w["x0"] < mid]
    right = [w for w in words if w["x0"] >= mid]
    return to_text(left), to_text(right)


def _extract_party_name(col_text: str) -> str | None:
    """Wyciąga wartość pola 'Nazwa:' z tekstu jednej kolumny, doklejając
    kolejne linie zawijania nazwy aż do napotkania kolejnej etykiety."""
    lines = col_text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip().startswith("Nazwa:")), None)
    if start is None:
        return None
    parts = [lines[start].split("Nazwa:", 1)[1].strip()]
    for l in lines[start + 1:]:
        ls = l.strip()
        if not ls or re.match(
            r'^(Adres|NIP|Dane|Identyfikator|Numer|Prefiks|E-mail|Tel\.)', ls, re.I
        ):
            break
        parts.append(ls)
    name = " ".join(p for p in parts if p).strip()
    return name or None


def _ksef_vat_summary(tables: list) -> tuple[float | None, float | None, float | None]:
    """Sumuje wiersze tabeli 'Podsumowanie stawek podatku' (Kwota netto /
    Kwota podatku / Kwota brutto) — jedna faktura może mieć kilka stawek VAT."""
    for table in tables:
        if not table or len(table) < 2:
            continue
        header = [str(c or "").lower().strip().replace("\n", " ") for c in table[0]]
        if "kwota netto" not in header or "kwota brutto" not in header:
            continue
        i_net = header.index("kwota netto")
        i_brutto = header.index("kwota brutto")
        i_vat = next((i for i, h in enumerate(header) if "kwota podat" in h), None)
        net = vat = brutto = 0.0
        for row in table[1:]:
            if not row:
                continue
            v = clean_amount(row[i_net]) if i_net < len(row) else None
            b = clean_amount(row[i_brutto]) if i_brutto < len(row) else None
            t = clean_amount(row[i_vat]) if i_vat is not None and i_vat < len(row) else None
            if v: net += v
            if b: brutto += b
            if t: vat += t
        return net or None, vat or None, brutto or None
    return None, None, None


def _from_header_table(tables: list) -> dict:
    """
    Wyciąga pola nagłówkowe z dwuwierszowej tabeli klucz-wartość
    (np. Rapidrop: Invoice Date | Invoice No | … / 13 Oct 2025 | 232326 | …)
    """
    h = {}
    mapping = {
        'invoice no': 'numer_faktury', 'invoice number': 'numer_faktury',
        'invoice date': 'data_faktury', 'due date': 'termin_platnosci',
        'payment due date': 'termin_platnosci', 'zahlungsdatum': 'termin_platnosci',
        'sales order no': 'numer_zamowienia', 'sales order no.': 'numer_zamowienia',
        'customer order no': 'numer_zamowienia', 'customer order no.': 'numer_zamowienia',
        'numer faktury': 'numer_faktury', 'data faktury': 'data_faktury',
        'termin płatności': 'termin_platnosci', 'nr zamówienia': 'numer_zamowienia',
    }
    for table in tables:
        if not table or len(table) not in (2, 3): continue
        headers = [str(c or '').lower().strip().replace('\n',' ') for c in table[0]]
        data    = [str(c or '').strip().replace('\n',' ')          for c in table[1]]
        for j, hdr in enumerate(headers):
            field = mapping.get(hdr)
            if field and j < len(data) and data[j] and field not in h:
                h[field] = data[j]
    return h


def _extract_vendor_name(text: str) -> str:
    m = re.search(r'(?:Sprzedawca|Wystawca|Sprzedaj[aą]cy)\s*[:\n]\s*(.+?)(?:\n|NIP|ul\.|Al\.)', text, re.I)
    if m and _looks_like_real_vendor_name(m.group(1)):
        return m.group(1).strip()
    # Nazwa sprzedawcy zwykle stoi w nagłówku/stopce dokumentu (pierwsze
    # ~600 znaków) — szukanie w całym tekście łapało czasem dane nabywcy
    # ("Invoice To:" / "Deliver To:" pojawiają się dalej, ale też pasują
    # do wzorca spółki). `finditer` (nie tylko pierwszy match) + walidacja
    # długości, bo pierwsze wystąpienie formy prawnej w tekście bywa
    # wewnątrz zdania klauzuli prawnej, nie w nazwie nagłówkowej.
    suffix = r'Sp\.\s*z\s*o\.o\.?|S\.A\.|A/S|sp\.j\.|LLC|GmbH|Limited|Ltd\.?|B\.V\.?|Inc\.?'
    for search_text in (text[:600], text):
        for cm in re.finditer(rf'([^\n]{{3,80}}(?:{suffix})[^\n]*)', search_text, re.I):
            if _looks_like_real_vendor_name(cm.group(1)):
                return cm.group(1).strip()
    return "Nieznany"


def extract_header(text: str, tables: list, vendor: str,
                    page0_words: list | None = None,
                    page0_width: float | None = None) -> dict:
    # 1. Próbuj z tabeli nagłówkowej (Rapidrop, ogólne EN)
    h = _from_header_table(tables)

    # 2. Uzupełnij brakujące pola wzorcami tekstowymi
    def fv(*patterns):
        return find_value(text, *patterns)

    if not h.get("numer_faktury"):
        h["numer_faktury"] = {
            "tim":         fv(r"Faktura VAT\s+(FV\S+)"),
            "sonepar":     fv(r"Numer Faktury:\s*(FA_\S+)"),
            "siemens":     fv(r"Faktura numer[^\n]+\n\S+\s+(\d{7,11})"),
            "mercor":      fv(r"Nr\s+(FVSHW[\S]+)"),
            "euroterm":    fv(r"nr\s+(\(S\)FS-\d+/\d+/[A-Z]+)"),
            "fire_eater":  fv(r"Invoice\s*No\.?\s+(\d{5,10})"),
            "tyco":        fv(r"INVOICE\s+(\d{7,12})"),
            # Numer faktury stoi na osobnej linii pod etykietą; linia
            # bezpośrednio pod nim to typ dokumentu ("Faktura podstawowa" /
            # "Faktura korygująca"), NIE numer — trzeba złapać tylko
            # pierwszą linię po etykiecie.
            "ksef_generic": fv(r"Numer Faktury:\s*([^\n]+)"),
        }.get(vendor) or fv(
            r"Invoice\s+No\.?[:\s]+(\d{4,10})",
            r"(?:Faktura\s*(?:VAT|nr|numer)?|Nr\s*faktury)[:\s]*([\w/\-]+)",
        )

    if not h.get("data_faktury"):
        h["data_faktury"] = {
            # Siemens: layout dwukolumnowy - etykieta "Data faktury Waluta"
            # stoi w jednej linii, a wartość ("16.01.2026 PLN") trafia na
            # kolejną linię tekstu, sklejoną z adresem z sąsiedniej kolumny.
            "siemens": fv(r"Data faktury\s+Waluta\s*\n[^\n]*?(\d{2}\.\d{2}\.\d{4})\s+PLN"),
            # Tyco: "Inv No./Date : 9080648368 / 18-Feb-2025"
            "tyco":    fv(r"Inv\s*No\.?/Date\s*:\s*\S+\s*/\s*(\d{2}-[A-Za-z]{3}-\d{4})"),
        }.get(vendor) or fv(
            r"Data\s+(?:faktury|wystawienia)[:\s]*(\d{2}[.\-]\d{2}[.\-]\d{4}|\d{4}-\d{2}-\d{2})",
            # KSeF: "Data wystawienia, z zastrzeżeniem art. 106na ust. 1 ustawy: 15.04.2026"
            r"Data\s+wystawienia[^:\n]*:\s*(\d{2}\.\d{2}\.\d{4})",
            r"Invoice\s+Date[:\s]+(\d{2}[- ][A-Za-z]{3}[- ]\d{4}|\d{2}\.\d{2}\.\d{4})",
        )
    if not h.get("termin_platnosci"):
        h["termin_platnosci"] = fv(
            r"Termin\s+p[łl]atno[śs]ci[:\s]*(\d{2}[.\-]\d{2}[.\-]\d{4}|\d{4}-\d{2}-\d{2})",
            r"Due\s+Date[:\s]+(\d{2}[- ][A-Za-z]{3}[- ]\d{4}|\d{2}\.\d{2}\.\d{4})",
            r"Zahlungsdatum\s*:\s*(\d{2}\.\d{2}\.\d{4})",
            # Euroterm: kolumny "Forma płatności Termin Kwota ..." -> wiersz
            # "Przelew 2025-12-19 166,76 PLN ...".
            r"Przelew\s+(\d{4}-\d{2}-\d{2})",
        )
    if not h.get("numer_zamowienia"):
        h["numer_zamowienia"] = fv(
            r"(?:Nr|Numer)\s+zam[oó]wienia\s+klienta[:\s]*(.+?)(?:\n|$)",
            r"(?:Sales\s+Order\s+No\.?|Your\s+P\.O\.\s+number)[:\s]+(.+?)(?:\n|Page)",
            r"Zamówienia?[:\s]+([\w/\-]+)",
        )

    if not h.get("sprzedawca") and vendor == "ksef_generic" and page0_words:
        # Layout dwukolumnowy "Sprzedawca | Nabywca" — zwykły extract_text()
        # miesza pola z obu kolumn w jednej linii, więc trzeba rozdzielić
        # słowa wg pozycji x0 i czytać tylko lewą kolumnę (sprzedawca).
        left_col, _right_col = _column_texts(page0_words, page0_width or 595)
        h["sprzedawca"] = _extract_party_name(left_col)

    if not h.get("sprzedawca"):
        h["sprzedawca"] = {
            "tim": "TIM S.A.", "sonepar": "Sonepar Polska Sp. z o.o.",
            "siemens": "Siemens Sp. z o.o.", "mercor": "MERCOR Light&Vent sp. z o.o.",
            "euroterm": "EUROTERM TGS sp. z o.o.", "fire_eater": "Fire Eater A/S",
            "tyco": "Tyco Building Services Products GmbH",
            "rapidrop": "Rapidrop Europe Limited",
        }.get(vendor) or _extract_vendor_name(text)

    # Kwoty razem
    if not h.get("razem_brutto"):
        h["razem_brutto"] = clean_amount(fv(
            r"(?:Total\s+[€£$]?\s*Incl\.?\s*VAT|Do\s+zapłaty(?:\s+brutto)?|"
            r"Razem\s+do\s+zapłaty|INVOICE AMOUNT\s+EUR|Kwota należności ogółem|"
            rf"Warto[śs][cć]\s+sprzeda[żz]y\s+brutto)[^\d\n]*({_MONEY})",
            rf"Total\s+(?:EUR|USD|GBP|PLN|CHF)\s+({_MONEY})",
        ))
    if not h.get("razem_netto"):
        # "Subtotal" jest sprawdzany jako ostatni (osobny, niższy priorytet
        # wzorzec) — na fakturach z rabatem (np. Rapidrop 232326) Subtotal
        # to kwota PRZED rabatem, a "Total Excl. VAT" to właściwa netto.
        # find_value zwraca dopasowanie pierwszego wzorca, który cokolwiek
        # złapie, więc kolejność argumentów tu ma znaczenie.
        h["razem_netto"] = clean_amount(fv(
            rf"(?:Total\s+[€£$]?\s*Excl\.?\s*VAT|Total\s+amount\s*\(excl\s*Taxes?\)|"
            rf"Net\s+amount|Razem\s+netto|"
            rf"Warto[śs][cć]\s+sprzeda[żz]y\s+netto)[:\s]*({_MONEY})",
            # Wiersz podsumowania "RAZEM 507,70 116,77 624,47" (TIM) albo
            # "Razem: 135,58 31,18 166,76" (Euroterm/Mercor) — pierwsza
            # liczba to netto. Wyklucza "Razem do zapłaty" (to brutto).
            rf"(?:RAZEM|Razem)(?!\s+do\s+zapłaty)[:\s]+({_MONEY})",
            rf"Subtotal[:\s]*({_MONEY})",
        ))
    if not h.get("razem_netto"):
        # Część faktur (Sonepar, KSeF) nie ma żadnej tekstowej etykiety
        # "Razem netto" — kwoty są tylko w tabeli "Podsumowanie stawek
        # podatku" (Lp./Stawka podatku/Kwota netto/Kwota podatku/Kwota
        # brutto), czasem z kilkoma wierszami (po jednym na stawkę VAT).
        net, _vat, brutto = _ksef_vat_summary(tables)
        if net is not None:
            h["razem_netto"] = net
        if not h.get("razem_brutto") and brutto is not None:
            h["razem_brutto"] = brutto

    # Waluta – jednoznaczne symbole/deklaracje mają pierwszeństwo przed
    # przypadkowym wystąpieniem innego kodu waluty gdzieś w tekście
    # (np. przeliczenie VAT na PLN na fakturze wystawionej w EUR).
    cm = re.search(r'Currency[:\s]+(EUR|USD|GBP|CHF|PLN)\b', text, re.I)
    if cm:
        h["waluta"] = cm.group(1).upper()
    elif '€' in text:
        h["waluta"] = "EUR"
    elif '£' in text:
        h["waluta"] = "GBP"
    else:
        wm = re.search(r'\b(EUR|USD|GBP|CHF|PLN)\b', text)
        h["waluta"] = wm.group(1) if wm else "PLN"

    # Walidacja końcowa niezależna od tego, KTÓRA ścieżka wyżej ustawiła
    # numer_faktury/sprzedawcę (tabela nagłówkowa, wzorzec dla konkretnego
    # dostawcy, czy zachłanny generyczny fallback) — śmieciowa wartość
    # (bez cyfry / całe zdanie z klauzuli) jest gorsza niż jej brak: myli
    # wykrywanie duplikatów (dwie różne faktury z tym samym błędnym
    # "numerem" wyglądają jak ta sama) i tabele/Excel. Lepiej zostawić
    # puste pole — GUI i tak ostrzeże o brakujących danych nagłówka.
    if not _looks_like_real_invoice_number(h.get("numer_faktury")):
        h["numer_faktury"] = None
    if not _looks_like_real_vendor_name(h.get("sprzedawca")):
        h["sprzedawca"] = None

    return h


# ══════════════════════════════════════════════════════════════
#  GŁÓWNA FUNKCJA PARSOWANIA
# ══════════════════════════════════════════════════════════════

def parse_invoice(pdf_path: str) -> tuple[dict, list[dict]]:
    full_text = ""
    all_tables: list = []
    page0_words: list = []
    page0_width: float | None = None
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            full_text += (page.extract_text() or "") + "\n"
            try:
                tbls = page.extract_tables()
                if tbls: all_tables.extend(tbls)
            except Exception: pass
            if i == 0:
                try:
                    page0_words = page.extract_words()
                    page0_width = page.width
                except Exception: pass

    vendor = detect_vendor(full_text)
    header = extract_header(full_text, all_tables, vendor, page0_words, page0_width)
    header["typ"]  = vendor
    header["plik"] = Path(pdf_path).name

    # ── Wybór parsera pozycji ─────────────────────────────────
    # Priorytet: tabele → tekst specyficzny → tekst ogólny
    items = parse_all_tables(all_tables, full_text)

    if not items:
        text_parsers = {
            "tim":        parse_text_tim,
            "siemens":    parse_text_siemens,
            "mercor":     parse_text_mercor,
            "euroterm":   parse_text_euroterm,
            "fire_eater": parse_text_fire_eater,
            "tyco":       parse_text_tyco,
        }
        if vendor in text_parsers:
            items = text_parsers[vendor](full_text)

    if not items:
        items = parse_text_universal(full_text)

    return header, items


# ══════════════════════════════════════════════════════════════
#  BUDOWANIE EXCELA
# ══════════════════════════════════════════════════════════════

CLR = {"hd": "1F3864", "hb": "2E75B6", "alt": "DEEAF1", "wh": "FFFFFF",
       "tot": "FFE699", "gok": "E2EFDA", "rw": "FCE4D6", "orm": "FFF2CC"}

KAT_CLR = {
    "sygnalizacja_pozaru": "FCE4D6", "elektryka": "DEEAF1", "automatyka": "E2EFDA",
    "obudowy_szafy": "EAF0FB", "hydraulika": "D9E1F2", "gazownictwo": "FFF2CC",
    "transport": "F4CCFF", "teletechnika": "D6E4BC", "mechanika": "F0E6FF",
    "narzedzia": "FFE4B5", "ogolnobudowlane": "E8E8E8", "inne": "F2F2F2",
}

def _hc(ws, r, c, v, bg=None, fg="FFFFFF", bold=True, sz=11, al="center"):
    cell = ws.cell(r, c, v)
    cell.font      = Font(bold=bold, color=fg, name="Arial", size=sz)
    cell.fill      = PatternFill("solid", fgColor=bg or CLR["hd"])
    cell.alignment = Alignment(horizontal=al, vertical="center", wrap_text=True)
    s = Side(style="thin", color="BFBFBF")
    cell.border = Border(left=s, right=s, top=s, bottom=s)
    return cell

def _dc(ws, r, c, v, bg=None, bold=False, al="left", fmt=None):
    cell = ws.cell(r, c, v)
    cell.font      = Font(bold=bold, name="Arial", size=10)
    cell.alignment = Alignment(horizontal=al, vertical="center", wrap_text=True)
    if bg:  cell.fill          = PatternFill("solid", fgColor=bg)
    if fmt: cell.number_format = fmt
    s = Side(style="thin", color="D9D9D9")
    cell.border = Border(left=s, right=s, top=s, bottom=s)
    return cell

def build_sheet_items(ws, items):
    ws.title = "Kategoryzacja pozycji"
    ws.freeze_panes = "A3"
    ws.merge_cells("A1:S1")
    tc = ws["A1"]
    tc.value = f"KATEGORYZACJA WYDATKÓW — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    tc.font  = Font(bold=True, size=14, color="FFFFFF", name="Arial")
    tc.fill  = PatternFill("solid", fgColor=CLR["hd"])
    tc.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    COLS = [
        ("Numer faktury",22),("Sprzedawca",24),("Data faktury",14),
        ("Lp.",6),("Indeks/Kod",18),("Opis",44),("PKWiU",13),
        ("Ilość",9),("JM",7),("Cena netto",13),("Wartość netto",14),
        ("VAT",9),("Kwota VAT",12),("Wartość brutto",14),("Waluta",9),
        ("KATEGORIA",28),("Pewność",10),("Źródło",18),("Powód",30),
    ]
    for ci,(h,w) in enumerate(COLS,1):
        _hc(ws,2,ci,h,bg=CLR["hb"])
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.row_dimensions[2].height = 32

    for ri,it in enumerate(items,3):
        bg = KAT_CLR.get(it.get("kategoria_klucz","inne"), CLR["wh"])
        FIELDS = [
            ("numer_faktury",None,"left"),("sprzedawca",None,"left"),("data_faktury",None,"center"),
            ("lp",None,"center"),("indeks",None,"center"),("opis",None,"left"),("pkwiu",None,"center"),
            ("ilosc","#,##0.000","right"),("jm",None,"center"),("cena_netto","#,##0.00","right"),
            ("wartosc_netto","#,##0.00","right"),("stawka_vat",None,"center"),
            ("kwota_vat","#,##0.00","right"),("wartosc_brutto","#,##0.00","right"),
            ("waluta",None,"center"),("kategoria_nazwa",None,"left"),
            ("pewnosc",None,"center"),("zrodlo_dopasowania",None,"center"),("powod",None,"left"),
        ]
        for ci,(fld,fmt,al) in enumerate(FIELDS,1):
            val = it.get(fld)
            c = _dc(ws,ri,ci,val,bg=bg,al=al,fmt=fmt)
            if fld=="pewnosc" and val is not None:
                c.fill = PatternFill("solid", fgColor=(CLR["gok"] if val>=70 else CLR["orm"] if val>=40 else CLR["rw"]))

    nr = len(items)+3
    _dc(ws,nr,9,"SUMA:",bold=True,bg=CLR["tot"],al="right")
    for ci in [11,13,14]:
        cl = get_column_letter(ci)
        c  = _dc(ws,nr,ci,None,bold=True,bg=CLR["tot"],al="right",fmt="#,##0.00")
        c.value = f"=SUM({cl}3:{cl}{nr-1})"
        c.font  = Font(bold=True,name="Arial")

def build_sheet_summary_kat(ws, items):
    ws.title = "Koszty per kategoria"
    ws.freeze_panes = "A3"
    ws.merge_cells("A1:G1")
    tc = ws["A1"]
    tc.value = "ZESTAWIENIE KOSZTÓW PER KATEGORIA"
    tc.font  = Font(bold=True,size=13,color="FFFFFF",name="Arial")
    tc.fill  = PatternFill("solid",fgColor=CLR["hd"])
    tc.alignment = Alignment(horizontal="center",vertical="center")
    ws.row_dimensions[1].height = 26

    for ci,(h,w) in enumerate([("Kategoria",34),("Pozycji",12),("Suma netto",15),
                                ("Suma VAT",13),("Suma brutto",15),("% netto",14),("Avg.pewność",12)],1):
        _hc(ws,2,ci,h,bg=CLR["hb"])
        ws.column_dimensions[get_column_letter(ci)].width = w

    agg = defaultdict(lambda: {"n":0,"net":0.,"vat":0.,"brt":0.,"pew":0})
    for it in items:
        k = it.get("kategoria_klucz","inne")
        agg[k]["n"]   += 1
        agg[k]["net"] += it.get("wartosc_netto") or 0.
        agg[k]["vat"] += it.get("kwota_vat")     or 0.
        agg[k]["brt"] += it.get("wartosc_brutto") or 0.
        agg[k]["pew"] += it.get("pewnosc") or 0

    rows = sorted(agg.items(), key=lambda x: -x[1]["brt"])
    start = 3
    for ri,(k,d) in enumerate(rows,start):
        bg  = KAT_CLR.get(k, CLR["wh"])
        avg = round(d["pew"]/d["n"],0) if d["n"] else 0
        _dc(ws,ri,1,KATEGORIE.get(k,"❓ Inne"),bg=bg,bold=True)
        _dc(ws,ri,2,d["n"],bg=bg,al="center")
        _dc(ws,ri,3,d["net"],bg=bg,al="right",fmt="#,##0.00")
        _dc(ws,ri,4,d["vat"],bg=bg,al="right",fmt="#,##0.00")
        _dc(ws,ri,5,d["brt"],bg=bg,al="right",fmt="#,##0.00")
        pc = ws.cell(ri,6,f"=C{ri}/SUM(C{start}:C{start+len(rows)-1})")
        pc.number_format = "0.00%"; pc.alignment = Alignment(horizontal="right",vertical="center")
        pc.fill = PatternFill("solid",fgColor=bg)
        s = Side(style="thin",color="D9D9D9"); pc.border = Border(left=s,right=s,top=s,bottom=s)
        pw = _dc(ws,ri,7,avg,bg=bg,al="center")
        pw.fill = PatternFill("solid", fgColor=(CLR["gok"] if avg>=70 else CLR["orm"] if avg>=40 else CLR["rw"]))

    sr = start+len(rows)
    _dc(ws,sr,1,"RAZEM",bold=True,bg=CLR["tot"])
    _dc(ws,sr,2,sum(d["n"] for d in agg.values()),bold=True,bg=CLR["tot"],al="center")
    for ci in [3,4,5]:
        cl = get_column_letter(ci)
        c  = _dc(ws,sr,ci,None,bold=True,bg=CLR["tot"],al="right",fmt="#,##0.00")
        c.value = f"=SUM({cl}{start}:{cl}{sr-1})"
        c.font  = Font(bold=True,name="Arial")

def build_sheet_invoices(ws, headers):
    ws.title = "Podsumowanie faktur"
    ws.freeze_panes = "A2"
    ws.merge_cells("A1:I1")
    tc = ws["A1"]
    tc.value = "PODSUMOWANIE FAKTUR"
    tc.font  = Font(bold=True,size=13,color="FFFFFF",name="Arial")
    tc.fill  = PatternFill("solid",fgColor=CLR["hd"])
    tc.alignment = Alignment(horizontal="center",vertical="center")
    ws.row_dimensions[1].height = 24

    for ci,(h,w) in enumerate([("Plik PDF",28),("Numer faktury",22),("Sprzedawca",24),
                                ("Data faktury",14),("Termin płatności",16),("Nr zamówienia",22),
                                ("Waluta",9),("Suma netto",15),("Suma brutto",15)],1):
        _hc(ws,2,ci,h,bg=CLR["hb"])
        ws.column_dimensions[get_column_letter(ci)].width = w

    for ri,h in enumerate(headers,3):
        bg = CLR["alt"] if ri%2==0 else CLR["wh"]
        for ci,(f,fmt,al) in enumerate([
            ("plik",None,"left"),("numer_faktury",None,"left"),("sprzedawca",None,"left"),
            ("data_faktury",None,"center"),("termin_platnosci",None,"center"),
            ("numer_zamowienia",None,"left"),("waluta",None,"center"),
            ("razem_netto","#,##0.00","right"),("razem_brutto","#,##0.00","right"),
        ],1):
            _dc(ws,ri,ci,h.get(f),bg=bg,al=al,fmt=fmt)

    sr = len(headers)+3
    _dc(ws,sr,6,"RAZEM (bez przeliczenia walut):",bold=True,bg=CLR["tot"],al="right")
    for ci in [8,9]:
        cl = get_column_letter(ci)
        c  = _dc(ws,sr,ci,None,bold=True,bg=CLR["tot"],al="right",fmt="#,##0.00")
        c.value = f"=SUM({cl}3:{cl}{sr-1})"
        c.font  = Font(bold=True,name="Arial")

def build_sheet_legend(ws):
    ws.title = "Legenda"
    ws.merge_cells("A1:D1")
    tc = ws["A1"]
    tc.value = "LEGENDA KATEGORII"
    tc.font  = Font(bold=True,size=13,color="FFFFFF",name="Arial")
    tc.fill  = PatternFill("solid",fgColor=CLR["hd"])
    tc.alignment = Alignment(horizontal="center",vertical="center")

    for ci,(h,w) in enumerate([("Klucz",28),("Nazwa",36),("Przykładowe produkty",60),("Kolor",12)],1):
        _hc(ws,2,ci,h,bg=CLR["hb"])
        ws.column_dimensions[get_column_letter(ci)].width = w

    EX = {
        "sygnalizacja_pozaru": "Centrale SAP, czujki, sygnalizatory, klapy pożarowe, tryskacze, zawory alarmowe",
        "elektryka":           "Wyłączniki, kable, zasilacze, lampki, rozłączniki",
        "automatyka":          "Przekaźniki, PLC, gniazda, sterowniki",
        "obudowy_szafy":       "Szafy elektryczne, obudowy IP66, korytka kablowe",
        "hydraulika":          "Rury, zawory, armatura, pompy, zawory motylkowe",
        "gazownictwo":         "Rury gazowe, zawory gazowe, gazomierze",
        "transport":           "Spedycja, kurier, handling, shipping",
        "teletechnika":        "Kable sieciowe, kamery, UPS, punkty dostępowe",
        "mechanika":           "Śruby, wsporniki, szyny montażowe, uchwyty",
        "narzedzia":           "Taśmy, silikony, drobny osprzęt",
        "ogolnobudowlane":     "Materiały budowlane: cement, farby, izolacje",
        "inne":                "Nierozpoznane – wymaga weryfikacji ręcznej",
    }
    for ri,(k,n) in enumerate(KATEGORIE.items(),3):
        bg = KAT_CLR.get(k, CLR["wh"])
        _dc(ws,ri,1,k,bg=bg); _dc(ws,ri,2,n,bold=True,bg=bg); _dc(ws,ri,3,EX.get(k,""),bg=bg)
        c = ws.cell(ri,4,f"#{bg}")
        c.fill = PatternFill("solid",fgColor=bg)
        c.font = Font(name="Arial",size=9)
        c.alignment = Alignment(horizontal="center",vertical="center")


# ══════════════════════════════════════════════════════════════
#  GŁÓWNA PĘTLA PRZETWARZANIA
# ══════════════════════════════════════════════════════════════

def categorize_files(pdf_files: list[str], use_web: bool = True,
                      log=print) -> tuple[list[dict], list[dict]]:
    """Parsuje i kategoryzuje listę PDF-ów. Zwraca (all_headers, all_items).

    `log` przyjmuje pojedynczy string na wywołanie – domyślnie print,
    ale np. API webowe może podać własną funkcję (np. do streamowania postępu).
    """
    all_headers, all_items = [], []

    for idx, path in enumerate(pdf_files, 1):
        log(f"\n[{idx}/{len(pdf_files)}] {Path(path).name}")
        try:
            header, items = parse_invoice(path)
        except Exception as e:
            log(f"  ✗ błąd: {e}"); continue

        all_headers.append(header)
        log(f"  ✓ {header.get('numer_faktury')} | "
            f"{header.get('razem_brutto')} {header.get('waluta','PLN')} | "
            f"{len(items)} pozycji")

        for j, item in enumerate(items, 1):
            kat = kategoryzuj(item.get("opis",""), item.get("indeks",""),
                              item.get("pkwiu",""), use_web=use_web)
            log(f"  [{j:2d}] {item.get('opis','')[:50]:<50} → "
                f"{kat['kategoria_nazwa']:<32} ({kat['pewnosc']}% | {kat['zrodlo_dopasowania']})")
            all_items.append({
                **item,
                "plik":               header.get("plik"),
                "numer_faktury":      header.get("numer_faktury"),
                "sprzedawca":         header.get("sprzedawca"),
                "data_faktury":       header.get("data_faktury"),
                "waluta":             header.get("waluta","PLN"),
                "kategoria_klucz":    kat["kategoria_klucz"],
                "kategoria_nazwa":    kat["kategoria_nazwa"],
                "pewnosc":            kat["pewnosc"],
                "zrodlo_dopasowania": kat["zrodlo_dopasowania"],
                "powod":              kat["powod"],
            })

    return all_headers, all_items


def build_workbook(all_headers: list[dict], all_items: list[dict]) -> Workbook:
    wb = Workbook()
    build_sheet_legend(wb.active)
    build_sheet_items(wb.create_sheet(), all_items)
    build_sheet_summary_kat(wb.create_sheet(), all_items)
    build_sheet_invoices(wb.create_sheet(), all_headers)
    return wb


def process(pdf_files: list[str], output: str, use_web: bool = True):
    all_headers, all_items = categorize_files(pdf_files, use_web=use_web)

    wb = build_workbook(all_headers, all_items)
    wb.save(output)

    print(f"\n{'─'*60}")
    print(f"✓  Zapisano: {output}")
    print(f"   Faktury:   {len(all_headers)}")
    print(f"   Pozycji:   {len(all_items)}")

    cnt = defaultdict(int)
    for it in all_items: cnt[it["kategoria_nazwa"]] += 1
    print("\n   Rozkład kategorii:")
    for kat, n in sorted(cnt.items(), key=lambda x: -x[1]):
        print(f"     {kat:<40} {n:3d}")


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Kategoryzacja faktur PDF → Excel (PL + EN)")
    ap.add_argument("pliki", nargs="*",    help="Pliki PDF lub folder (domyślnie: bieżący)")
    ap.add_argument("--bez-internetu", action="store_true", help="Tylko słownik, bez DuckDuckGo")
    ap.add_argument("-o","--output",
                    default=f"kategoryzacja_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    args = ap.parse_args()

    raw = []
    if not args.pliki:
        raw = glob.glob("*.pdf") + glob.glob("*.PDF")
    elif len(args.pliki) == 1 and os.path.isdir(args.pliki[0]):
        d = args.pliki[0]
        raw = glob.glob(os.path.join(d,"*.pdf")) + glob.glob(os.path.join(d,"*.PDF"))
    else:
        raw = args.pliki

    # Eliminacja duplikatów przez ścieżkę absolutną
    uniq = {Path(p).resolve(): str(Path(p)) for p in raw if Path(p).is_file()}
    pliki = sorted(uniq.values())

    if not pliki:
        print("Nie znaleziono plików PDF.")
        sys.exit(1)

    use_web = not args.bez_internetu
    if use_web and not WEB_AVAILABLE:
        print("Wyszukiwanie niedostępne. Zainstaluj: pip install requests beautifulsoup4\n")
        use_web = False

    print(f"Znaleziono {len(pliki)} plik(ów) PDF")
    print(f"Wyszukiwanie: {'TAK' if use_web else 'NIE'} | Wynik: {args.output}\n")
    process(pliki, args.output, use_web=use_web)