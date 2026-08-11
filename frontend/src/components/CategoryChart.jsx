import { useMemo, useState } from "react";
import { categoryColor, categoryLabel } from "../categories";
import { fmtMoney } from "../format";

export default function CategoryChart({ items }) {
  const { rows, mixedCurrencies } = useMemo(() => {
    const agg = new Map();
    const currencies = new Set();
    for (const it of items) {
      const key = it.kategoria_klucz || "inne";
      const cur = agg.get(key) || { key, count: 0, netto: 0, vat: 0, brutto: 0 };
      cur.count += 1;
      cur.netto += it.wartosc_netto || 0;
      cur.vat += it.kwota_vat || 0;
      cur.brutto += it.wartosc_brutto || 0;
      agg.set(key, cur);
      if (it.waluta) currencies.add(it.waluta);
    }
    return {
      rows: Array.from(agg.values()).sort((a, b) => b.brutto - a.brutto),
      mixedCurrencies: currencies.size > 1,
    };
  }, [items]);

  const [hovered, setHovered] = useState(null);
  const max = Math.max(1, ...rows.map((r) => r.brutto));

  if (!rows.length) return null;

  return (
    <div className="chart-card">
      <h3 className="chart-card__title">Koszty per kategoria</h3>
      {mixedCurrencies && (
        <p className="chart-card__note">
          Uwaga: pozycje w różnych walutach zsumowane bez przeliczenia kursu.
        </p>
      )}
      <div className="bar-chart">
        {rows.map((r) => {
          const pct = Math.max((r.brutto / max) * 100, 2);
          return (
            <div
              className="bar-row"
              key={r.key}
              onMouseEnter={() => setHovered(r.key)}
              onMouseLeave={() => setHovered((k) => (k === r.key ? null : k))}
            >
              <div className="bar-row__label">{categoryLabel(r.key)}</div>
              <div className="bar-row__track">
                <div
                  className="bar-row__fill"
                  style={{ width: `${pct}%`, background: categoryColor(r.key) }}
                />
                {hovered === r.key && (
                  <div className="bar-tooltip">
                    <div>
                      <strong>{categoryLabel(r.key)}</strong>
                    </div>
                    <div>Pozycji: {r.count}</div>
                    <div>Netto: {fmtMoney(r.netto)}</div>
                    <div>VAT: {fmtMoney(r.vat)}</div>
                    <div>Brutto: {fmtMoney(r.brutto)}</div>
                  </div>
                )}
              </div>
              <div className="bar-row__value">{fmtMoney(r.brutto)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
