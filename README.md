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
  requirements.txt
frontend/              # aplikacja React (Vite)
input/                  # folder na przykładowe faktury PDF (gitignored)
```

## Backend — setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r backend/requirements.txt
```

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

Endpointy:
- `POST /api/process` — multipart form, pole `files` (wiele PDF), opcjonalnie
  `use_web` (`true`/`false`). Zwraca JSON z fakturami i skategoryzowanymi
  pozycjami oraz `job_id`.
- `GET /api/download/{job_id}` — pobiera wygenerowany plik Excel dla danej sesji.

## Frontend — setup

```bash
cd frontend
npm install
cp .env.example .env      # ustaw VITE_API_URL, jeśli backend nie działa na :8000
npm run dev
```

Otwórz adres wypisany przez Vite (domyślnie http://localhost:5173). Wgraj
pliki PDF przeciągając je na stronę lub wybierając z dysku, kliknij
„Kategoryzuj”, przejrzyj wyniki (wykres kosztów per kategoria, tabela faktur,
filtrowana tabela pozycji) i pobierz gotowy plik Excel.

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
