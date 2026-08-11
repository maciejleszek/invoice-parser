import { useMemo, useState } from "react";
import { CATEGORY_ORDER, categoryColor, categoryLabel } from "../categories";
import { fmtMoney } from "../format";

function ConfidenceBadge({ value }) {
  const level = value >= 70 ? "high" : value >= 40 ? "mid" : "low";
  return (
    <span className={`confidence confidence--${level}`} title="Pewność dopasowania kategorii">
      {value}%
    </span>
  );
}

export default function ItemsTable({ items }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");

  const usedCategories = useMemo(
    () =>
      CATEGORY_ORDER.filter((c) => items.some((it) => it.kategoria_klucz === c)),
    [items]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((it) => {
      if (category !== "all" && it.kategoria_klucz !== category) return false;
      if (!q) return true;
      return (
        (it.opis || "").toLowerCase().includes(q) ||
        (it.indeks || "").toLowerCase().includes(q) ||
        (it.numer_faktury || "").toLowerCase().includes(q)
      );
    });
  }, [items, query, category]);

  if (!items.length) return null;

  return (
    <div className="table-card">
      <div className="table-card__header">
        <h3 className="table-card__title">Pozycje ({filtered.length}/{items.length})</h3>
        <div className="table-card__filters">
          <input
            type="search"
            placeholder="Szukaj po opisie, indeksie, numerze faktury…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="text-input"
          />
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="select-input"
          >
            <option value="all">Wszystkie kategorie</option>
            {usedCategories.map((c) => (
              <option key={c} value={c}>
                {categoryLabel(c)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Faktura</th>
              <th>Opis</th>
              <th>Indeks</th>
              <th className="num">Ilość</th>
              <th>JM</th>
              <th className="num">Cena netto</th>
              <th className="num">Wartość netto</th>
              <th className="num">Wartość brutto</th>
              <th>Kategoria</th>
              <th>Pewność</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((it, i) => (
              <tr key={i}>
                <td className="mono">{it.numer_faktury || "—"}</td>
                <td className="opis-cell" title={it.opis}>
                  {it.opis || "—"}
                </td>
                <td className="mono">{it.indeks || "—"}</td>
                <td className="num">{it.ilosc ?? "—"}</td>
                <td>{it.jm || "—"}</td>
                <td className="num">{fmtMoney(it.cena_netto)}</td>
                <td className="num">{fmtMoney(it.wartosc_netto)}</td>
                <td className="num">{fmtMoney(it.wartosc_brutto)}</td>
                <td>
                  <span
                    className="category-pill"
                    style={{
                      "--pill-color": categoryColor(it.kategoria_klucz),
                    }}
                  >
                    {categoryLabel(it.kategoria_klucz)}
                  </span>
                </td>
                <td>
                  <ConfidenceBadge value={it.pewnosc ?? 0} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p className="table-empty">Brak pozycji spełniających kryteria filtra.</p>
        )}
      </div>
    </div>
  );
}
