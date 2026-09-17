import { useEffect, useMemo, useState } from "react";
import StatTile from "./StatTile";
import CategoryChart from "./CategoryChart";
import TrendChart from "./TrendChart";
import ItemsTable from "./ItemsTable";
import YearFilter from "./YearFilter";
import KierownikFilter from "./KierownikFilter";
import Loading from "./Loading";
import { fmtMoney } from "../format";
import * as api from "../api";

export default function Dashboard() {
  const [years, setYears] = useState([]);
  const [year, setYear] = useState(null);
  const [kierownicy, setKierownicy] = useState([]);
  const [kierownik, setKierownik] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.listYears().then(setYears).catch((e) => setError(e.message));
    api.listKierownicy().then(setKierownicy).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .listItems({ year, kierownik })
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [year, kierownik]);

  async function handleCategoryChange(itemId, kategoriaKlucz) {
    setItems((prev) =>
      prev.map((it) =>
        it.id === itemId ? { ...it, kategoria_klucz: kategoriaKlucz, manual_override: 1 } : it
      )
    );
    try {
      await api.updateItemCategory(itemId, kategoriaKlucz);
    } catch (e) {
      setError(e.message);
      api.listItems({ year, kierownik }).then(setItems);
    }
  }

  const invoiceCount = useMemo(
    () => new Set(items.map((it) => it.invoice_id)).size,
    [items]
  );
  const brutoByCurrency = useMemo(() => {
    const agg = new Map();
    for (const it of items) {
      const ccy = it.waluta || "PLN";
      agg.set(ccy, (agg.get(ccy) || 0) + (it.wartosc_brutto || 0));
    }
    return Array.from(agg.entries());
  }, [items]);

  return (
    <div>
      <div className="view-header">
        <h2 className="view-header__title">Podsumowanie roczne — wszystkie projekty</h2>
        <div className="view-header__filters">
          <YearFilter years={years} value={year} onChange={setYear} />
          <KierownikFilter kierownicy={kierownicy} value={kierownik} onChange={setKierownik} />
        </div>
      </div>

      {error && <div className="alert alert--error">{error}</div>}
      {loading && <Loading label="Wczytywanie podsumowania…" />}

      {!loading && items.length === 0 && (
        <p className="muted-note">
          Brak danych{year ? ` za ${year} rok` : ""}{kierownik ? ` dla kierownika „${kierownik}”` : ""}.
          Dodaj faktury do dowolnego projektu, żeby zobaczyć tu zestawienie.
        </p>
      )}

      {!loading && items.length > 0 && (
        <>
          <section className="stats-row">
            <StatTile label="Faktury" value={invoiceCount} />
            <StatTile label="Pozycje" value={items.length} />
            {brutoByCurrency.map(([ccy, val]) => (
              <StatTile key={ccy} label={`Suma brutto (${ccy})`} value={fmtMoney(val)} />
            ))}
          </section>

          <section className="content-grid content-grid--single">
            <CategoryChart items={items} />
          </section>

          <TrendChart items={items} />

          <section>
            <ItemsTable items={items} onCategoryChange={handleCategoryChange} />
          </section>
        </>
      )}
    </div>
  );
}
