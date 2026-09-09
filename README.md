# Invoice Parser & Categorizer

Automatyczne wyciąganie danych z faktur PDF (PL + EN) i kategoryzacja pozycji
kosztowych. Dostępne jako:

- **CLI** — `backend/app/categorizer.py`, samodzielny skrypt Python → plik Excel.
- **REST API** — FastAPI (`backend/app/api.py`) opakowujące tę samą logikę.
- **Web GUI** — aplikacja React (`frontend/`) do przeciągnięcia PDF-ów i podglądu
  wyników w przeglądarce.

## Struktura projektu

```
backend/
  app/
    categorizer.py   # parsowanie PDF, kategoryzacja, generowanie XLSX
    api.py            # REST API (FastAPI) dla frontendu
    db.py             # trwałe przechowywanie projektów/faktur (SQLite)
  tests/               # pytest — jednostkowe + end-to-end na prawdziwych PDF-ach
  data/                # plik app.db (gitignored, tworzony automatycznie)
  requirements.txt
  requirements-dev.txt # + pytest
frontend/              # aplikacja React (Vite)
input/                  # folder na przykładowe faktury PDF (gitignored)
```

## Backend — setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r backend/requirements.txt
```

### Testy

```bash
pip install -r backend/requirements-dev.txt
cd backend
pytest tests/ -v
```

Dwa rodzaje testów:
- **Jednostkowe** (`test_categorizer_units.py`) — czyste funkcje (parsowanie
  kwot, wykrywanie dostawcy, mapowanie kolumn tabeli...), bez plików PDF,
  zawsze się uruchamiają. Każdy przypadek odpowiada realnemu bugowi
  znalezionemu i naprawionemu podczas pracy nad appką.
- **End-to-end** (`test_categorizer_fixtures.py`) — `parse_invoice()` na
  prawdziwych fakturach z `input/`/`Nowy folder/`, porównane z ręcznie
  zweryfikowanymi wartościami. Te pliki są celowo poza gitem (mogą zawierać
  rzeczywiste dane firmowe) — na świeżym klonie repo testy są pomijane
  (skipped), nie failują.

### CLI

```bash
cd backend/app
python categorizer.py ../../input          # katalog z PDF-ami
python categorizer.py f1.pdf f2.pdf ...    # konkretne pliki
python categorizer.py --bez-internetu      # tylko słownik, bez wyszukiwania w sieci
```

Wynik: plik `kategoryzacja_<timestamp>.xlsx` z arkuszami: legenda kategorii,
pozycje faktur (z przypisaną kategorią i pewnością dopasowania), zestawienie
kosztów per kategoria, podsumowanie faktur.

### REST API (dla GUI)

```bash
cd backend
uvicorn app.api:app --reload --port 8000
```

Jeśli port 8000 jest zajęty przez inną usługę, wybierz inny port i ustaw go
też w `frontend/.env` (patrz niżej).

Endpointy — szybka analiza (bezstanowa, nic nie jest zapisywane):
- `POST /api/process` — multipart form, pole `files` (wiele PDF), opcjonalnie
  `use_web` (`true`/`false`). Zwraca JSON z fakturami i skategoryzowanymi
  pozycjami oraz `job_id`.
- `GET /api/download/{job_id}` — pobiera wygenerowany plik Excel dla danej sesji.

Endpointy — projekty (trwałe, zapisywane w SQLite pod `backend/data/app.db`):
- `POST /api/projects` `{name}` — tworzy projekt.
- `GET /api/projects` — lista projektów (z liczbą faktur/pozycji).
- `GET /api/projects/{id}` — szczegóły projektu: lista faktur + dostępne lata.
- `DELETE /api/projects/{id}` — usuwa projekt wraz z fakturami.
- `POST /api/projects/{id}/invoices` — jak `/api/process`, ale zapisuje
  sparsowane faktury do projektu zamiast trzymać je tylko w pamięci.
  Duplikaty (ten sam plik albo ten sam numer faktury u tego samego
  sprzedawcy) są pomijane i zwracane w `skipped_duplicates`.
- `PATCH /api/projects/{id}/invoices/{invoice_id}` — ręczna poprawka
  nagłówka faktury (numer, sprzedawca, daty, kwoty...) — parser czasem
  nie trafi idealnie, to naprawia to bez edycji kodu.
- `DELETE /api/projects/{id}/invoices/{invoice_id}` — usuwa jedną fakturę.
- `GET /api/projects/{id}/download?year=2026` — Excel dla projektu,
  opcjonalnie tylko za dany rok.
- `POST /api/projects/{id}/recategorize?use_web=&force=` — przelicza
  kategorie już zapisanych pozycji (np. po rozszerzeniu słownika słów
  kluczowych) bez usuwania i ponownego wgrywania faktur. Domyślnie omija
  pozycje poprawione ręcznie; `force=true` nadpisuje też te.
- `GET /api/items?project_id=&year=` — pozycje (globalnie, dla projektu i/lub
  dla roku) — używane do wykresu kosztów per kategoria i tabeli pozycji.
- `PATCH /api/items/{item_id}` `{kategoria_klucz}` — ręczna korekta kategorii
  jednej pozycji z GUI (oznaczana jako `manual_override`, więc
  `recategorize` jej domyślnie nie nadpisze).
- `GET /api/years?project_id=` — lista lat, dla których są dane (globalnie
  albo w obrębie jednego projektu) — zasila filtr roku w GUI.
- `GET /api/backup` — cała baza (wszystkie projekty/faktury/pozycje) jako
  plik `.db` do pobrania — asekuracja przed `docker compose down -v`/awarią
  dysku (jedyna kopia danych żyje w wolumenie Dockera).

## Frontend — setup

```bash
cd frontend
npm install
cp .env.example .env      # ustaw VITE_API_URL, jeśli backend nie działa na :8000
npm run dev
```

Otwórz adres wypisany przez Vite (domyślnie http://localhost:5173). Aplikacja
ma trzy zakładki:
- **Szybka analiza** — wgraj PDF-y, zobacz wynik, pobierz Excel; nic nie jest
  zapisywane (dokładnie tak jak wcześniej).
- **Projekty** — utwórz projekt, wgrywaj do niego faktury w czasie (dane
  zostają zapisane), przeglądaj jego faktury/pozycje/wykres kategorii i
  trend miesięczny z filtrem roku, pobierz Excel dla projektu (całość albo
  za wybrany rok). Faktury można sortować/wyszukiwać, poprawiać ręcznie
  (przycisk ✎) i usuwać (z potwierdzeniem). Kategorię pozycji można
  poprawić bezpośrednio z listy rozwijanej w tabeli, a przycisk „Przelicz
  kategorie ponownie” przelicza wszystkie pozycje projektu na nowo (z
  poszanowaniem ręcznych poprawek).
- **Podsumowanie roczne** — zestawienie kosztów per kategoria ze wszystkich
  projektów razem, z filtrem roku (np. wszystko za 2026).

Build produkcyjny: `npm run build` (pliki w `frontend/dist/`).

## Docker

Najprostszy sposób odpalenia całości (backend + frontend) bez instalowania
Pythona/Node lokalnie:

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8001

Porty można nadpisać zmiennymi środowiskowymi `BACKEND_PORT` / `FRONTEND_PORT`
(przydatne, jeśli 8001/5173 są już zajęte). Adres API używany przez frontend
jest wypiekany do builda przez `VITE_API_URL` — jeśli zmienisz `BACKEND_PORT`,
ustaw też `VITE_API_URL` na zgodny adres, np.:

```bash
BACKEND_PORT=9000 VITE_API_URL=http://localhost:9000 docker compose up --build
```

Dane projektów żyją w nazwanym wolumenie Dockera (`backend_data`) i przetrwają
`docker compose down` / restart kontenera — znikają dopiero po
`docker compose down -v`.
