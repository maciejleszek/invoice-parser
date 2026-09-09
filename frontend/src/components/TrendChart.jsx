import { useMemo } from "react";
import { fmtMoney } from "../format";

const MONTH_LABELS = [
  "Sty", "Lut", "Mar", "Kwi", "Maj", "Cze", "Lip", "Sie", "Wrz", "Paź", "Lis", "Gru",
];

function extractYearMonth(dateStr) {
  if (!dateStr) return null;
  // DD.MM.YYYY / DD-MM-YYYY (format polski)
  let m = dateStr.match(/^(\d{2})[.\-](\d{2})[.\-](\d{4})$/);
  if (m) return `${m[3]}-${m[2]}`;
  // YYYY-MM-DD
  m = dateStr.match(/^(\d{4})-(\d{2})-\d{2}/);
  if (m) return `${m[1]}-${m[2]}`;
  // Fallback: formaty angielskie ("11-Aug-2025", "13 April 2026") — Date
  // radzi sobie z nimi natywnie, w przeciwieństwie do formatu kropkowego.
  const d = new Date(dateStr);
  if (!isNaN(d.getTime())) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  }
  return null;
}

export default function TrendChart({ items }) {
  const rows = useMemo(() => {
    const agg = new Map();
    for (const it of items) {
      const ym = extractYearMonth(it.data_faktury);
      if (!ym) continue;
      agg.set(ym, (agg.get(ym) || 0) + (it.wartosc_brutto || 0));
    }
    return Array.from(agg.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([ym, brutto]) => {
        const [y, mo] = ym.split("-");
        return { ym, label: `${MONTH_LABELS[Number(mo) - 1]} ${y}`, brutto };
      });
  }, [items]);

  if (rows.length < 2) return null; // trend nic nie mówi dla jednego miesiąca

  const max = Math.max(1, ...rows.map((r) => r.brutto));

  return (
    <div className="chart-card standalone-card">
      <p className="eyebrow">Trend</p>
      <h3 className="chart-card__title">Wydatki miesięcznie (brutto)</h3>
      <div className="bar-chart">
        {rows.map((r) => (
          <div className="bar-row" key={r.ym}>
            <div className="bar-row__label">{r.label}</div>
            <div className="bar-row__track">
              <div
                className="bar-row__fill"
                style={{
                  width: `${Math.max((r.brutto / max) * 100, 2)}%`,
                  // Neutralny odcień (nie --brand, zarezerwowany dla akcji/
                  // nawigacji) — to pojedyncza seria wielkości, bez
                  // znaczenia kategorii do zakodowania kolorem.
                  background: "color-mix(in srgb, var(--text-primary) 55%, transparent)",
                }}
              />
            </div>
            <div className="bar-row__value">{fmtMoney(r.brutto)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
