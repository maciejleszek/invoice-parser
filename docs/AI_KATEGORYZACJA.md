# Import faktur czytanych przez Claude Code (zamiast regexowego parsera)

Alternatywna ścieżka wgrywania faktur do projektu: zamiast polegać na
`parse_invoice()`/`kategoryzuj()` w `backend/app/categorizer.py` (regex +
pdfplumber), Claude Code czyta PDF bezpośrednio (wizualnie, narzędziem
Read) i sam produkuje gotowe dane. Zaimportowane tak faktury trafiają do
tej samej bazy, tą samą drogą (`find_duplicate`/`save_invoice`) co zwykły
upload przez GUI — duplikaty, podgląd PDF-u, edycja pozycji, „Przelicz
kategorie ponownie” działają identycznie.

**Dlaczego to w ogóle istnieje:** na prawdziwych fakturach z projektów 601
i 626 ten sposób poprawnie odczytał i skategoryzował dokumenty, na których
regexowy parser miał poważne dziury — zepsute kodowanie fontów w PDF-ie
(sprzedawca wychodził jako fragment zupełnie innego zdania), zeskanowane
dokumenty bez żadnej warstwy tekstowej (zero danych), sklejone w jedną
linię dwie różne pozycje tabeli. Nie zastępuje to appki — to osobna,
półautomatyczna ścieżka importu z człowiekiem w pętli (przegląd przed
zapisem), używana obok normalnego wgrywania przez GUI.

## Jak z tego skorzystać

1. W sesji Claude Code wskaż projekt (jego `project_id` z `GET /api/projects`)
   i folder z nowymi PDF-ami.
2. Dla każdego pliku: przeczytaj go narzędziem Read, oceń czy to w ogóle
   faktura (patrz „Dokumenty, które nie są fakturą” niżej), i jeśli tak —
   zbuduj wpis wg `schema()` z `backend/app/ai_import.py` (nagłówek +
   pozycje, z `kategoria_klucz` dla każdej pozycji — klucze z
   `categorizer.KATEGORIE`, a dla dostawców usługowych sprawdź najpierw
   `categorizer._VENDOR_CATEGORY_HINTS`).
3. Zapisz wszystkie wpisy jako jedną listę JSON.
4. Uruchom najpierw z podglądem, potem naprawdę:
   ```
   python -m app.ai_import <project_id> batch.json --dry-run
   python -m app.ai_import <project_id> batch.json
   ```
5. Zweryfikuj wynik w GUI appki (karta projektu) — to wciąż faktury do
   przejrzenia, nie ślepo zaufany wynik.

## Reguły brzegowe (nauczone na prawdziwych fakturach)

Bez tego Claude radzi sobie świetnie z czystym odczytem, ale te konkretne
konwencje są specyficzne dla tej firmy/działu i nie da się ich wywnioskować
z samej treści jednego dokumentu:

- **Dokumenty WZ („DOKUMENT WYDANIA nr WZ...”) to NIE faktury.** To
  załączniki magazynowe bez własnej wartości kosztowej — zawsze odwołują
  się do właściwej faktury przez „Nr faktury: F/.../..”. Pomiń je całkowicie
  (nie twórz dla nich wpisu) — ich koszt jest już w fakturze, do której się
  odnoszą.

- **Faktury zaliczkowe („F.ZAL/...”) netują się z fakturą końcową.**
  Kategoria: `bez_wplywu_na_koszt`, kwoty zerowe w rejestrze — realny koszt
  jest rozliczony dopiero na fakturze końcowej (`F.VAT/...`), która
  pokrywa całość zaliczki.

- **Noty korygujące / Credit Note** — kwota ujemna (zwrot/pomniejszenie
  kosztu), kategoria wg treści KREDYTOWANYCH pozycji (nie osobna kategoria
  „korekta”). Dla faktur walutowych (najczęściej Rapidrop, Reliable Fire
  Sprinkler — EUR): dokument zwykle podaje tylko PLN-owy odpowiednik kwoty
  VAT, nie całej kwoty. Kurs przeliczeniowy wyprowadź z tej jednej znanej
  pary: `kurs = kwota_VAT_PLN / kwota_VAT_walutowa`, i zastosuj ten sam
  kurs do całej kwoty faktury. To dokładnie metoda, jaką przyjęto w
  dotychczasowym ręcznym rejestrze kosztów — nie zgaduj/nie pomijaj kursu.

- **Zbiorcze rozliczenia pracownicze („Rozliczenie [imię nazwisko]
  [data]”)** to zwykle zeskanowane papierowe druki delegacji + czasem
  doklejone osobne faktury za zakupy opłacone przez pracownika. W
  dotychczasowym rejestrze całość takiego zestawienia dostawała JEDNĄ
  kategorię dla całej kwoty — `rozliczenia_pracownicze`, jeśli dominują
  delegacje/diety/paliwo, albo konkretną kategorię materiałową (np.
  `materialy_pomocnicze`), jeśli dominują zakupy materiałowe. To bywa
  subiektywny wybór księgowej, nie twarda reguła — jeśli nie jest oczywiste,
  które dominuje, zaznacz to wprost w opisie zamiast zgadywać pewnie.

- **Projekt = folder na dysku, nigdy treść faktury.** Nie przypisuj
  faktury do innego projektu na podstawie wzmianki w treści (np. numeru
  zamówienia) — `project_id` zawsze pochodzi z tego, gdzie plik faktycznie
  leży.

## Taksonomia kategorii

Zawsze aktualna lista i słowa kluczowe: `backend/app/categorizer.py` —
`KATEGORIE` (15 kategorii + `inne`) i `_VENDOR_CATEGORY_HINTS` (dostawcy,
których tożsamość sama w sobie jest pewnym sygnałem kategorii — głównie
usługi: podwykonawstwo, wynajem sprzętu, zaplecze budowy). Ta dokumentacja
celowo nie duplikuje tej listy — źródłem prawdy jest kod.
