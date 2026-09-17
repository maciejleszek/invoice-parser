const CRITICAL_FIELDS = [
  { key: "numer_faktury", label: "numer faktury" },
  { key: "sprzedawca", label: "sprzedawca" },
  { key: "razem_brutto", label: "kwota brutto" },
];

function missingLabels(header) {
  return CRITICAL_FIELDS.filter((f) => header[f.key] == null || header[f.key] === "").map(
    (f) => f.label
  );
}

// Komunikat o jakości odczytu (braki w nagłówku, zero pozycji z pliku) i
// kategoryzacji (niska pewność dopasowania) — żeby błędnie odczytana
// faktura nie prześlizgnęła się niezauważona wśród dziesiątek innych.
export default function AnalysisQualityBanner({ invoices, items }) {
  const itemCountByPlik = new Map();
  for (const it of items || []) {
    if (!it.plik) continue;
    itemCountByPlik.set(it.plik, (itemCountByPlik.get(it.plik) || 0) + 1);
  }
  const knowsItemCounts = itemCountByPlik.size > 0;

  const readingProblems = [];
  for (const h of invoices || []) {
    const missing = missingLabels(h);
    const zeroItems = knowsItemCounts && h.plik && !itemCountByPlik.get(h.plik);
    if (zeroItems) {
      readingProblems.push({
        plik: h.plik,
        text: "nie udało się wyciągnąć żadnych pozycji z tego pliku",
      });
    } else if (missing.length) {
      readingProblems.push({ plik: h.plik, text: `brak danych: ${missing.join(", ")}` });
    }
  }

  const lowConf = (items || []).filter((it) => (it.pewnosc ?? 0) < 70).length;
  const veryLowConf = (items || []).filter((it) => (it.pewnosc ?? 0) < 40).length;

  if (!readingProblems.length && !lowConf) return null;

  return (
    <div className="alert alert--warning">
      <strong>Sprawdź jakość odczytu i kategoryzacji:</strong>
      <ul>
        {readingProblems.map((p, i) => (
          <li key={i}>
            <strong>{p.plik}</strong> — {p.text}, popraw ręcznie (✎) albo usuń i wgraj ponownie.
          </li>
        ))}
        {lowConf > 0 && (
          <li>
            {lowConf} {lowConf === 1 ? "pozycja wymaga" : "pozycji wymaga"} sprawdzenia kategorii
            (pewność &lt;70%){veryLowConf > 0 ? `, w tym ${veryLowConf} bardzo niepewnych (<40%)` : ""}
            {" "}— filtr „Do przeglądu” w tabeli pozycji.
          </li>
        )}
      </ul>
    </div>
  );
}
