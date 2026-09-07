# DEKK Design System — "arkusz warsztatowy"

Wyciągnięty z aplikacji **prefabrykacja** (ten katalog), która jest bazą
wizualną dla wszystkich appek firmowych. Ten dokument jest **niezależny
od frameworka** — appka referencyjna jest w React + Tailwind, ale opisy
komponentów niżej dają czysty CSS/HTML, żeby dało się je wdrożyć
w dowolnym stacku (Vue, Django templates, plain HTML+CSS, cokolwiek).

Towarzyszy mu [`tokens.css`](./tokens.css) — gotowy do wklejenia plik
zmiennych CSS z pełną obsługą jasnego/ciemnego motywu. **Zacznij od
niego** w każdej appce, którą standaryzujesz.

## Filozofia

Appka referencyjna to w większości liczby w kolumnach (mm, sztuki, %) —
stąd metafora "tabliczki rysunkowej" (nagłówek z linią jak na rysunku
technicznym) i cyfry tabularne wszędzie. Twoje appki nie muszą mieć
tej samej domeny, ale **trzy zasady warto przenieść wprost**:

1. **Kolor ma znaczenie, nie dekorację.** Marka (czerwień) = wyłącznie
   akcja główna i aktywna nawigacja. Błękit = wyłącznie rysunki/dane
   techniczne. Zielony/bursztynowy/czerwony semantyczny = wyłącznie
   stany (sukces/ostrzeżenie/błąd). Nic nie jest kolorowe "bo ładnie".
2. **Ciemny motyw to przełącznik ręczny**, nie tylko podążanie za
   systemem — użytkownik ma świadomy wybór, zapisany trwale.
3. **Jeden zestaw komponentów, zero duplikacji stylu.** Karta, przycisk,
   badge, input wyglądają zawsze tak samo, bo pochodzą z jednego miejsca
   (`ui.jsx` w appce referencyjnej) — nie kopiuj klas ręcznie po komponentach.

## Paleta kolorów

| Token | Hex | Zastosowanie |
|---|---|---|
| `--ink` | `#10151f` | Najgłębsza warstwa: szyna nawigacji (zawsze ciemna, patrz niżej), tło strony w dark mode |
| `--graphite` | `#1c2230` | Karty/panele w dark mode, kolor marki w elementach strukturalnych |
| `--brand` | `#c9384a` | **Wyłącznie** akcja główna (przycisk primary) i aktywna nawigacja |
| `--brand-dark` | `#a72f3e` | Hover/active stanu `--brand` |
| `--blueprint` | `#2563eb` | **Wyłącznie** rysunki techniczne, wymiary, dane geometryczne |
| `--ok` / `--warn` / `--bad` | `#059669` / `#d97706` / `#dc2626` | Stany semantyczne (sukces/ostrzeżenie/błąd) — **inny odcień czerwieni niż `--brand`**, nie mylić |
| skala neutralna | standardowa skala `slate` (Tailwind) 50→900 | cały tekst drugorzędny, obramowania, tła subtelne |

Tło strony w jasnym motywie to **`#f1f4f8`, nie czysty biały** — karty
(`--surface: #ffffff`) odcinają się od tła appki. To celowe, nie literówka.

## Typografia

- Krój tekstu: **Inter** (fallback: Segoe UI, system-ui)
- Krój danych: **JetBrains Mono** (fallback: Consolas) — używany dla
  wszystkiego co numeryczne/tabelaryczne, z `font-variant-numeric: tabular-nums`
- Nagłówki (`h1/h2/h3`) mają `letter-spacing: -0.02em` (lekko ściśnięte)
- Skala rozmiarów faktycznie używana w appce: `17px` (H1 widoku),
  `20px` (H2 sekcji), `13-15px` (treść/podtytuły), `12px` (drugorzędne),
  `11px` (etykiety pól), `10px` (mikro-etykiety, "eyebrow")
- **Wzorzec "eyebrow"**: `10-11px`, uppercase, `font-weight: 600`,
  `letter-spacing: 0.12em`, kolor `--text-faint` — mikro-etykieta nad
  KAŻDĄ sekcją/polem/KPI. To najbardziej rozpoznawalny element stylu.

```css
.eyebrow {
  font-size: 0.625rem;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--text-faint);
}
```

## Kształt i cień

- Przyciski/inputy: `border-radius: 0.5rem` (`--radius-md`)
- Karty/modale: `border-radius: 0.75rem` (`--radius-lg`)
- Odznaki/statusy/kropki: `border-radius: 9999px` (pełne)
- Cień karty: bardzo subtelny (`--shadow-card`), **wyłączony całkowicie
  w dark mode** (`box-shadow: none` — na ciemnym tle cień jest zbędny,
  kontrast daje sam kolor tła karty vs strony)
- Cień hover/uniesienia: `--shadow-lift`, razem z `translateY(-2px)`
- Przejścia: `150ms` na wszystkim co interaktywne (hover, focus, toggle)

## Ciemny motyw — mechanizm

Appka referencyjna: `ThemeContext.jsx` — hook `useTheme()` zwracający
`{ theme, toggleTheme, setTheme }`. Wybór zapisywany w `localStorage`
**przed** zmianą stanu, klasa `dark` przełączana na `<html>` przez
`useEffect`, `document.documentElement.style.colorScheme` synchronizowany
żeby natywne kontrolki (`<input type="date">` itp.) też się przemalowały.
Brak wyboru w localStorage → fallback na `prefers-color-scheme`.

`tokens.css` odwzorowuje to jako `:root.dark` / `:root[data-theme="dark"]`
(oba warianty, wybierz który pasuje do stacku appki) plus automatyczny
fallback pod `@media (prefers-color-scheme: dark)`.

**Wyjątek świadomy**: szyna nawigacji i ekran logowania appki referencyjnej
są **zawsze ciemne**, niezależnie od wybranego motywu — jak pasek boczny
w VS Code czy Linear. To nie przeoczenie; jeśli Twoja appka ma stały,
rozpoznawalny "chrome" (sidebar, top bar marki), rozważ to samo zamiast
przepuszczać go przez przełącznik.

### Mapowanie jasny → ciemny (Tailwind, jeśli appka go używa)

| Jasny | Ciemny | Gdzie |
|---|---|---|
| `bg-white` | `dark:bg-graphite` | karty, inputy, modale |
| `bg-slate-50` | `dark:bg-white/5` | nagłówki tabel, hover wierszy |
| `bg-slate-100` | `dark:bg-slate-800` | odznaki neutralne, ikony |
| `text-slate-700/800/900` | `dark:text-slate-100/200` | nagłówki, wartości |
| `text-slate-500/600` | `dark:text-slate-300/400` | opisy, etykiety |
| `text-slate-400` | `dark:text-slate-500` | tekst wyciszony |
| `border-slate-200/300` | `dark:border-slate-700/600` | obramowania |
| `border-slate-100` | `dark:border-slate-800` | separatory subtelne |

Bez Tailwinda: to samo mapowanie robi `tokens.css` automatycznie przez
zmienne (`var(--surface)`, `var(--text-primary)` itd.) — nie trzeba
pisać osobnych reguł dla każdego elementu.

**Pułapka, na którą wpadliśmy przy wdrażaniu** (zanotowana, żeby się nie
powtórzyła): masowa podmiana `bg-slate-50` → `bg-slate-50 dark:bg-white/5`
przez sed/regex łatwo psuje `hover:bg-slate-50`, bo dopisuje ciemny
wariant BEZ prefiksu `hover:` (efekt: tło "ucieka" w dark mode nawet bez
najechania myszą). Po każdej masowej podmianie **zweryfikuj occurrences
z `hover:` osobno**.

## Komponenty

Każdy opisany jako: kiedy używać → recepta CSS → uwagi.

### Karta (`.card`)

Podstawowy kontener treści — tabele, formularze, KPI, wszystko poza
samym tłem strony.

```css
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}
```

### Przycisk

Warianty — używane wyłącznie zgodnie z rolą, nie z upodobaniem:

| Wariant | Kiedy | Recepta |
|---|---|---|
| `primary` | JEDNA akcja główna na widoku (zapisz, dodaj, wyślij) | `background: var(--brand)`, hover `var(--brand-dark)`, tekst biały |
| `secondary` | Akcja drugorzędna ale ważna | `background: var(--graphite)`, tekst biały |
| `ghost` | Większość przycisków — anuluj, filtruj, drugorzędne akcje | obramowanie `var(--border)`, tło `var(--surface)`, tekst `var(--text-secondary)` |
| `danger` | Usuń, nieodwracalne | `background: var(--bad)`, tekst biały |
| `success` | Potwierdź/zatwierdź | `background: var(--ok)`, tekst biały |

Rozmiary: `sm` (36px), `md` (42px), `lg` (52px) — **`lg` obowiązkowy
wszędzie, gdzie appka może być używana na tablecie dotykowym** (min. 44px
to twardy próg accessibility dla celu dotykowego).

```css
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: .5rem;
  border-radius: var(--radius-md);
  font-weight: 600;
  transition: all var(--transition);
  padding: .5rem 1rem; min-height: 42px;
}
.btn:active { transform: scale(.97); }
.btn:disabled { opacity: .45; cursor: not-allowed; box-shadow: none; }
.btn-primary   { background: var(--brand); color: #fff; }
.btn-primary:hover { background: var(--brand-dark); }
.btn-ghost     { background: var(--surface); color: var(--text-secondary); border: 1px solid var(--border); }
```

### Odznaka / tonalna pigułka (statusy, kategorie)

Recepta powtórzona identycznie dla każdego tonu — jasne tło + ciemniejszy
tekst tego samego koloru w jasnym motywie, odwrotnie (bardzo ciemne tło,
jasny tekst) w ciemnym:

```css
.badge {
  font-size: 11px; font-weight: 500;
  padding: .125rem .5rem; border-radius: 9999px;
}
/* Jasny motyw */
.badge-ok    { background: #d1fae5; color: #047857; border: 1px solid #a7f3d0; }
.badge-warn  { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
.badge-bad   { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }
/* Ciemny motyw — tło prawie czarne w danym odcieniu (~40% opacity
   na bazie 950), tekst rozjaśniony do 300 */
.dark .badge-ok   { background: rgba(6,78,59,.4);  color: #6ee7b7; border-color: rgba(6,95,70,.6); }
.dark .badge-warn { background: rgba(120,53,15,.4); color: #fcd34d; border-color: rgba(146,64,14,.6); }
.dark .badge-bad  { background: rgba(127,29,29,.4); color: #fca5a5; border-color: rgba(153,27,27,.6); }
```

To samo rozumowanie zastosuj do **każdego** koloru kategorii w appce
(np. kategorie faktur, priorytety zamówień) — jasne tło+ciemny tekst /
ciemne tło+jasny tekst, ten sam odcień bazowy po obu stronach.

### Kafelek KPI

Karta z kolorowym paskiem po lewej (2-4px, kolor marki albo `--bad` jeśli
alarm), eyebrow-label, i dużą wartością w foncie mono:

```
┌─┬──────────────────────┐
│▌│ AKTYWNE ZAMÓWIENIA   │  ← eyebrow
│▌│ 12                   │  ← .mono, bold, 24px
└─┴──────────────────────┘
```

### Input / Select

```css
.input {
  width: 100%; border: 1px solid var(--border); border-radius: var(--radius-md);
  padding: .625rem .75rem; font-size: .875rem;
  background: var(--surface); color: var(--text-primary);
}
.input:hover   { border-color: var(--text-faint); }
.input:focus   { outline: none; border-color: var(--brand); box-shadow: 0 0 0 3px rgba(201,56,74,.15); }
.input:disabled{ background: var(--surface-alt); color: var(--text-faint); }
```

Etykieta zawsze nad polem, styl "eyebrow" ale nie uppercase — `11px
font-weight:600 color:var(--text-muted)`.

### Tabela

- Nagłówek: `background: var(--surface-alt)`, tekst `--text-muted`,
  `11px uppercase letter-spacing: 0.05em`
- Wiersze: separator `1px solid var(--border-subtle)` (subtelniejszy niż
  obramowanie karty), hover `background: var(--surface-alt)`
- Liczby zawsze prawo-wyrównane i `.mono`

### Modal

- Tło (backdrop): `rgba(0,0,0,.3-.4)`, fade-in `150ms`
- Panel: styl `.card` + `border-radius: var(--radius-lg)`, cień mocniejszy
  (`--shadow-lift` albo mocniejszy), wjazd z lekkim `translateY(6px)→0`
  + `scale(.98)→1` w `180ms` (`cubic-bezier(.16,1,.3,1)` — "wyskakuje"
  zamiast pojawiać się z klatki na klatkę)

### Nagłówek strony ("titleblock")

Najbardziej charakterystyczny motyw appki referencyjnej: eyebrow + H1 +
podtytuł, z cienką linią pod spodem, gdzie **pierwsze ~72px linii są
w kolorze marki, reszta to hairline neutralny** — jak podpis na tabliczce
rysunku technicznego:

```css
.page-header { position: relative; padding-bottom: .75rem; }
.page-header::after {
  content: ''; position: absolute; left: 0; bottom: 0; height: 1px; width: 100%;
  background: linear-gradient(to right, var(--brand) 0 72px, var(--hairline) 72px 100%);
}
```

### Stany: pusty / ładowanie / błąd

Wszystkie trzy: wyśrodkowane pionowo i poziomo, `padding: 4rem 0`.
- **Ładowanie**: trzy pionowe kreski rosnącej wysokości, pulsujące
  z przesunięciem fazowym (`animation-delay` co ~140ms) w kolorze marki
  — nie generyczny spinner.
- **Błąd**: karta z czerwonawym tłem (`--bad` @ niska opacity), komunikat
  + surowy błąd w `.mono` osobno od komunikatu user-friendly.
- **Pusty**: traktowany jako **zaproszenie do działania**, nie komunikat
  o braku danych — tytuł + podpowiedź + ewentualny przycisk akcji, nie
  samo "Brak danych".

## Jak to wdrożyć w innej appce (dowolny stack)

1. **Wklej `tokens.css`** do appki, zaimportuj na samej górze głównego
   arkusza stylów (przed regułami appki, żeby zmienne były dostępne).
2. **Podmień tło strony i tekst** na `var(--bg-app)` / `var(--text-primary)`
   na najwyższym poziomie (`body` albo root layout).
3. **Dodaj przełącznik ciemnego motywu**, jeśli appka go jeszcze nie ma:
   przycisk który przełącza klasę `dark` (albo atrybut `data-theme`) na
   `<html>` i zapisuje wybór w `localStorage` — reszta zadziała sama
   przez zmienne w `tokens.css`.
4. **Zamień hardkodowane kolory marki** (`#jakiśCzerwony`, `#jakiśNiebieski`
   itd. rozsiane po kodzie) na `var(--brand)` / `var(--blueprint)` itd.
   To zwykle największa, ale najbardziej wartościowa robota.
5. **Wdrażaj komponent po komponencie**, zaczynając od tych używanych
   wszędzie (przyciski → karty → tabele), a nie strona po stronie —
   największa dźwignia jest we wspólnych elementach.
6. Jeśli appka jest w React/Vue/podobnym: rozważ też wydzielenie
   właściwych **komponentów** (nie tylko CSS) odpowiadających sekcji
   "Komponenty" wyżej — appka referencyjna trzyma je w jednym pliku
   (`components/ui.jsx`), żeby zmiana stylu przycisku działała się
   raz, a nie w 40 miejscach.
7. Poproś Claude Code w tamtym repo, żeby przeszedł strona po stronie
   i zamienił lokalne, ręczne style na te z tego dokumentu — dokładnie
   tak, jak zrobiliśmy tu wdrożenie ciemnego motywu: partiami, z
   commitem i szybką weryfikacją wizualną po każdej partii, zamiast
   jednego wielkiego, trudnego do zrecenzowania patcha.

## Czego świadomie NIE ma w tym dokumencie

- Ikonografii — appka referencyjna używa emoji jako ikon (`📋`, `⚙`, `✂`)
  zamiast biblioteki ikon; to działa dla tej appki, ale nie jest częścią
  "systemu" do skopiowania 1:1, jeśli inna appka ma już spójny zestaw SVG.
- Treści/kopii/tłumaczeń — appka referencyjna jest dwujęzyczna (PL/EN)
  przez własny mechanizm i18n; to osobna decyzja per-appka.
- Layoutu strony logowania i szyny nawigacji 1:1 — te są opisane wyżej
  jako *zasada* ("chrome appki może być na stałe ciemny"), nie jako
  gotowy layout do skopiowania, bo struktura nawigacji różni appki.
