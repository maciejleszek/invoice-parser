import { useMemo, useState } from "react";
import UploadZone from "./components/UploadZone";
import StatTile from "./components/StatTile";
import CategoryChart from "./components/CategoryChart";
import InvoicesTable from "./components/InvoicesTable";
import ItemsTable from "./components/ItemsTable";
import { fmtMoney } from "./format";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function App() {
  const [files, setFiles] = useState([]);
  const [useWeb, setUseWeb] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null); // { job_id, invoices, items }

  const brutoByCurrency = useMemo(() => {
    if (!result) return [];
    const agg = new Map();
    for (const h of result.invoices) {
      const ccy = h.waluta || "PLN";
      agg.set(ccy, (agg.get(ccy) || 0) + (h.razem_brutto || 0));
    }
    return Array.from(agg.entries());
  }, [result]);

  async function handleProcess() {
    if (!files.length) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      form.append("use_web", useWeb ? "true" : "false");

      const res = await fetch(`${API_URL}/api/process`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Serwer zwrócił błąd ${res.status}`);
      }
      const data = await res.json();
      setResult(data);
    } catch (e) {
      setError(
        e.message === "Failed to fetch"
          ? `Nie udało się połączyć z API (${API_URL}). Upewnij się, że backend jest uruchomiony.`
          : e.message
      );
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setFiles([]);
    setResult(null);
    setError(null);
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Kategoryzacja faktur</h1>
          <p className="app-header__subtitle">
            Wgraj faktury PDF, a aplikacja rozpozna dostawcę, wyciągnie pozycje
            i przypisze im kategorię kosztową.
          </p>
        </div>
      </header>

      <section className="panel">
        <UploadZone files={files} onFilesChange={setFiles} disabled={loading} />

        <div className="panel__controls">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={useWeb}
              onChange={(e) => setUseWeb(e.target.checked)}
              disabled={loading}
            />
            Użyj wyszukiwania w internecie (wolniejsze, dokładniejsze dla
            nieznanych produktów)
          </label>

          <div className="panel__actions">
            {result && (
              <button className="btn btn--ghost" onClick={handleReset} disabled={loading}>
                Wyczyść
              </button>
            )}
            <button
              className="btn btn--primary"
              onClick={handleProcess}
              disabled={loading || files.length === 0}
            >
              {loading ? (
                <>
                  <span className="spinner" /> Przetwarzanie…
                </>
              ) : (
                `Kategoryzuj (${files.length})`
              )}
            </button>
          </div>
        </div>

        {error && <div className="alert alert--error">{error}</div>}
      </section>

      {result && (
        <>
          <section className="stats-row">
            <StatTile label="Faktury" value={result.invoices.length} />
            <StatTile label="Pozycje" value={result.items.length} />
            {brutoByCurrency.map(([ccy, val]) => (
              <StatTile
                key={ccy}
                label={`Suma brutto (${ccy})`}
                value={fmtMoney(val)}
              />
            ))}
            <div className="stat-tile stat-tile--action">
              <a
                className="btn btn--primary"
                href={`${API_URL}/api/download/${result.job_id}`}
              >
                ⬇ Pobierz Excel
              </a>
            </div>
          </section>

          <section className="content-grid">
            <CategoryChart items={result.items} />
            <InvoicesTable invoices={result.invoices} />
          </section>

          <section>
            <ItemsTable items={result.items} />
          </section>
        </>
      )}
    </div>
  );
}
