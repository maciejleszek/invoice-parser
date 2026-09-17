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
- `POST /api/process/rebuild` `{invoices, items}` — odbudowuje plik Excel
  (nowy `job_id`) z podanych nagłówków/pozycji bez ponownego parsowania
  PDF-ów. Używane przez GUI po ręcznej poprawce faktury albo usunięciu
  błędnie odczytanej pozycji z wyników szybkiej analizy, żeby pobrany
  plik odzwierciedlał to, co widać na ekranie.

Endpointy — projekty (trwałe, zapisywane w SQLite pod `backend/data/app.db`):
- `POST /api/projects` `{name, kierownik?}` — tworzy projekt, opcjonalnie
  z kierownikiem projektu.
- `GET /api/projects` — lista projektów (z liczbą faktur/pozycji, kierownikiem).
- `GET /api/projects/{id}` — szczegóły projektu: lista faktur + dostępne lata.
- `PATCH /api/projects/{id}` `{name?, kierownik?}` — edycja nazwy/kierownika
  już istniejącego projektu (np. dopisanie kierownika projektom założonym
  zanim to pole istniało).
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
- `GET /api/items?project_id=&year=&kierownik=` — pozycje (globalnie, dla
  projektu i/lub dla roku i/lub dla kierownika projektu) — używane do
  wykresu kosztów per kategoria i tabeli pozycji.
- `PATCH /api/items/{item_id}` `{kategoria_klucz}` — ręczna korekta kategorii
  jednej pozycji z GUI (oznaczana jako `manual_override`, więc
  `recategorize` jej domyślnie nie nadpisze).
- `GET /api/years?project_id=` — lista lat, dla których są dane (globalnie
  albo w obrębie jednego projektu) — zasila filtr roku w GUI.
- `GET /api/kierownicy` — lista unikalnych kierowników projektów — zasila
  filtr kierownika w GUI.
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
  trwale zapisywane (dane żyją tylko w przeglądarce, w pamięci karty).
  Fakturę źle odczytaną przez parser można poprawić ręcznie (przycisk ✎)
  albo usunąć (×) i wgrać ponownie poprawiony/inny plik — kolejne wgrania
  dokładają się do już wyświetlonych wyników zamiast je zastępować (z
  ochroną przed przypadkowym wgraniem tego samego pliku/faktury drugi
  raz). Pobierany Excel zawsze odzwierciedla to, co widać na ekranie,
  łącznie z ręcznymi poprawkami. Nad wynikami wyświetla się ostrzeżenie,
  jeśli którejś fakturze brakuje kluczowych danych nagłówka, nie udało
  się wyciągnąć z niej żadnych pozycji, albo część pozycji ma niską
  pewność kategoryzacji.
- **Projekty** — utwórz projekt (opcjonalnie z kierownikiem projektu — pole
  można też dopisać/zmienić później, klikając w jego nazwę na karcie
  projektu), wgrywaj do niego faktury w czasie (dane zostają zapisane),
  przeglądaj jego faktury/pozycje/wykres kategorii i trend miesięczny z
  filtrem roku, pobierz Excel dla projektu (całość albo za wybrany rok).
  Listę projektów można filtrować po kierowniku. Faktury można
  sortować/wyszukiwać, poprawiać ręcznie (przycisk ✎) i usuwać (z
  potwierdzeniem) — usuniętą fakturę można wgrać ponownie (np. po
  poprawieniu pliku) tak samo jak nową. Kategorię pozycji można poprawić
  bezpośrednio z listy rozwijanej w tabeli, a przycisk „Przelicz kategorie
  ponownie” przelicza wszystkie pozycje projektu na nowo (z poszanowaniem
  ręcznych poprawek). Tak samo jak w szybkiej analizie, nad wynikami
  wyświetla się ostrzeżenie o niekompletnie odczytanych fakturach i
  pozycjach o niskiej pewności kategoryzacji.
- **Podsumowanie roczne** — zestawienie kosztów per kategoria ze wszystkich
  projektów razem, z filtrem roku i kierownika projektu (np. wszystko za
  2026 dla danego kierownika).

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

## Deployment na Vercel

Backend i frontend jako jeden projekt Vercel (`vercel.json` w korzeniu:
frontend budowany statycznie, backend jako funkcja serverless Python pod
`/api/*` — patrz `api/index.py`).

**Kluczowa różnica względem Dockera: baza danych.** Docker/lokalnie backend
trzyma dane w pliku SQLite — to nie zadziała na Vercelu, bo system plików
funkcji serverless jest efemeryczny (znika między wywołaniami). `backend/app/db.py`
obsługuje oba silniki przez SQLAlchemy; na Vercelu **musisz** ustawić
`DATABASE_URL` na prawdziwego, trwałego Postgresa:

1. Dodaj do projektu Vercel bazę Postgres (zakładka *Storage* → Vercel
   Postgres, albo zewnętrzny dostawca jak Neon/Supabase) i połącz ją z
   projektem — Vercel doda connection string do środowiska, ale **nie
   zawsze pod nazwą `DATABASE_URL`** (bywa `POSTGRES_URL`,
   `POSTGRES_PRISMA_URL`...). `db.py` sprawdza kilka wariantów nazwy po
   kolei, więc zwykle zadziała bez ręcznej zmiany — jeśli mimo podłączonej
   bazy backend dalej krzyczy o brakującej zmiennej, sprawdź w **Settings
   → Environment Variables**, pod jaką dokładnie nazwą pojawił się
   connection string (komunikat błędu w logach wypisuje sprawdzane nazwy).
   Po dodaniu/zmianie zmiennej zawsze zrób nowy **Redeploy** — sama zmiana
   w Environment Variables nie wpływa na już zbudowane funkcje.
   `db.py` normalizuje URL automatycznie do formatu wymaganego przez
   SQLAlchemy+psycopg niezależnie od tego, pod jaką nazwą go znajdzie.
2. W **Project Settings → Environment Variables** ustaw `VITE_API_URL` na
   **pusty string** (nie zostawiaj nieustawionej!) — frontend i backend są
   pod tym samym originem (routing z `vercel.json`), więc wywołania mają iść
   względnie (`/api/...`), nie na `localhost:8000`.
3. Deploy: połącz repo w dashboardzie Vercel (auto-deploy na każdy push) albo
   `npx vercel deploy --prod` z CLI.

Tabele tworzą się same przy pierwszym request (`db.init_db()` w evencie
startowym FastAPI).

**Ograniczenia, o których warto wiedzieć** (nie zweryfikowane na żywym
deployu — przygotowane i przetestowane lokalnie względem Postgresa, ale
sam `vercel deploy` wymaga Twojego konta):
- Limit czasu wykonania funkcji serverless (domyślnie krótki na planie
  Hobby) może być za ciasny dla dużej paczki faktur, zwłaszcza z włączonym
  „użyj wyszukiwania w internecie” (każde nowe zapytanie do DuckDuckGo to
  ~0.8s pauzy w kodzie).
- Limit rozmiaru requestu (multipart upload) na planie Hobby to ok. 4.5 MB
  — duża paczka PDF-ów na raz może go przekroczyć; wgrywaj mniejszymi
  partiami, jeśli trafisz na błąd.
- `GET /api/backup` zwraca teraz zrzut **JSON** (wcześniej: kopia pliku
  `.db`) — działa identycznie na SQLite i Postgresie.
