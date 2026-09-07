import { useCallback, useEffect, useMemo, useState } from "react";
import UploadZone from "./UploadZone";
import StatTile from "./StatTile";
import CategoryChart from "./CategoryChart";
import InvoicesTable from "./InvoicesTable";
import ItemsTable from "./ItemsTable";
import YearFilter from "./YearFilter";
import DuplicateWarning from "./DuplicateWarning";
import { fmtMoney } from "../format";
import * as api from "../api";

export default function ProjectDetail({ projectId, onBack }) {
  const [project, setProject] = useState(null);
  const [items, setItems] = useState([]);
  const [year, setYear] = useState(null);
  const [files, setFiles] = useState([]);
  const [useWeb, setUseWeb] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [skippedDuplicates, setSkippedDuplicates] = useState([]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [proj, its] = await Promise.all([
        api.getProject(projectId),
        api.listItems({ projectId, year }),
      ]);
      setProject(proj);
      setItems(its);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [projectId, year]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleUpload() {
    if (!files.length) return;
    setUploading(true);
    setError(null);
    setSkippedDuplicates([]);
    try {
      const res = await api.addInvoicesToProject(projectId, files, useWeb);
      setSkippedDuplicates(res.skipped_duplicates || []);
      setFiles([]);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteInvoice(invoiceId) {
    try {
      await api.deleteInvoice(projectId, invoiceId);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  const invoices = useMemo(() => {
    if (!project) return [];
    return year ? project.invoices.filter((i) => i.rok === year) : project.invoices;
  }, [project, year]);

  const brutoByCurrency = useMemo(() => {
    const agg = new Map();
    for (const h of invoices) {
      const ccy = h.waluta || "PLN";
      agg.set(ccy, (agg.get(ccy) || 0) + (h.razem_brutto || 0));
    }
    return Array.from(agg.entries());
  }, [invoices]);

  if (loading) return <p className="muted-note">Wczytywanie projektu…</p>;
  if (!project) return <p className="muted-note">Nie znaleziono projektu.</p>;

  return (
    <div>
      <div className="view-header">
        <button className="btn btn--ghost" onClick={onBack}>
          ← Projekty
        </button>
        <h2 className="view-header__title">{project.name}</h2>
        <YearFilter years={project.years} value={year} onChange={setYear} />
      </div>

      <section className="panel">
        <UploadZone files={files} onFilesChange={setFiles} disabled={uploading} />
        <div className="panel__controls">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={useWeb}
              onChange={(e) => setUseWeb(e.target.checked)}
              disabled={uploading}
            />
            Użyj wyszukiwania w internecie (wolniejsze, dokładniejsze dla nieznanych produktów)
          </label>
          <button
            className="btn btn--primary"
            onClick={handleUpload}
            disabled={uploading || files.length === 0}
          >
            {uploading ? (
              <>
                <span className="spinner" /> Przetwarzanie…
              </>
            ) : (
              `Dodaj do projektu (${files.length})`
            )}
          </button>
        </div>
        {error && <div className="alert alert--error">{error}</div>}
        <DuplicateWarning duplicates={skippedDuplicates} skipped />
      </section>

      {invoices.length === 0 ? (
        <p className="muted-note">
          {project.invoices.length === 0
            ? "Ten projekt nie ma jeszcze żadnych faktur — wgraj pierwsze powyżej."
            : "Brak faktur dla wybranego roku."}
        </p>
      ) : (
        <>
          <section className="stats-row">
            <StatTile label="Faktury" value={invoices.length} />
            <StatTile label="Pozycje" value={items.length} />
            {brutoByCurrency.map(([ccy, val]) => (
              <StatTile key={ccy} label={`Suma brutto (${ccy})`} value={fmtMoney(val)} />
            ))}
            <div className="stat-tile stat-tile--action">
              <a className="btn btn--primary" href={api.downloadProjectUrl(projectId, year)}>
                ⬇ Pobierz Excel
              </a>
            </div>
          </section>

          <section className="content-grid">
            <CategoryChart items={items} />
            <InvoicesTable invoices={invoices} onDelete={handleDeleteInvoice} />
          </section>

          <section>
            <ItemsTable items={items} />
          </section>
        </>
      )}
    </div>
  );
}
