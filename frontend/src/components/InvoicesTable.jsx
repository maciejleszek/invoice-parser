import { useMemo, useState } from "react";
import { fmtMoney } from "../format";

const COLUMNS = [
  { key: "plik", label: "Plik", className: "mono" },
  { key: "numer_faktury", label: "Numer faktury" },
  { key: "sprzedawca", label: "Sprzedawca" },
  { key: "data_faktury", label: "Data faktury" },
  { key: "termin_platnosci", label: "Termin płatności" },
  { key: "razem_netto", label: "Netto", className: "num", numeric: true },
  { key: "razem_brutto", label: "Brutto", className: "num", numeric: true },
  { key: "waluta", label: "Waluta" },
];

export default function InvoicesTable({ invoices, onDelete, onEdit }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState({ key: null, dir: 1 });

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let rows = !q
      ? invoices
      : invoices.filter((h) =>
          [h.plik, h.numer_faktury, h.sprzedawca].some((v) =>
            (v || "").toLowerCase().includes(q)
          )
        );
    if (sort.key) {
      rows = [...rows].sort((a, b) => {
        const av = a[sort.key], bv = b[sort.key];
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === "number" && typeof bv === "number") return (av - bv) * sort.dir;
        return String(av).localeCompare(String(bv)) * sort.dir;
      });
    }
    return rows;
  }, [invoices, query, sort]);

  if (!invoices.length) return null;

  function toggleSort(key) {
    setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: 1 }));
  }

  return (
    <div className="table-card">
      <div className="table-card__header">
        <h3 className="table-card__title">
          Faktury ({filtered.length}/{invoices.length})
        </h3>
        <div className="table-card__filters">
          <input
            type="search"
            placeholder="Szukaj po pliku, numerze, sprzedawcy…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="text-input"
          />
        </div>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th
                  key={c.key}
                  className={`${c.className || ""} sortable`}
                  onClick={() => toggleSort(c.key)}
                >
                  {c.label}
                  {sort.key === c.key && (sort.dir === 1 ? " ▲" : " ▼")}
                </th>
              ))}
              {(onDelete || onEdit) && <th></th>}
            </tr>
          </thead>
          <tbody>
            {filtered.map((h, i) => (
              <tr key={h.id ?? i}>
                <td className="mono" title={h.plik}>
                  {h.plik}
                </td>
                <td>{h.numer_faktury || "—"}</td>
                <td>{h.sprzedawca || "—"}</td>
                <td>{h.data_faktury || "—"}</td>
                <td>{h.termin_platnosci || "—"}</td>
                <td className="num">{fmtMoney(h.razem_netto)}</td>
                <td className="num">{fmtMoney(h.razem_brutto)}</td>
                <td>{h.waluta || "—"}</td>
                {(onDelete || onEdit) && (
                  <td className="row-actions">
                    {onEdit && (
                      <button
                        type="button"
                        className="icon-btn"
                        title="Popraw dane faktury"
                        onClick={() => onEdit(h)}
                      >
                        ✎
                      </button>
                    )}
                    {onDelete && (
                      <button
                        type="button"
                        className="icon-btn icon-btn--danger"
                        title="Usuń fakturę"
                        onClick={() => onDelete(h)}
                      >
                        ×
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p className="table-empty">Brak faktur spełniających kryteria wyszukiwania.</p>
        )}
      </div>
    </div>
  );
}
