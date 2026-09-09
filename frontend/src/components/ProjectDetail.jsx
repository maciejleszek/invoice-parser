import { useCallback, useEffect, useMemo, useState } from "react";
import UploadZone from "./UploadZone";
import StatTile from "./StatTile";
import CategoryChart from "./CategoryChart";
import TrendChart from "./TrendChart";
import InvoicesTable from "./InvoicesTable";
import ItemsTable from "./ItemsTable";
import YearFilter from "./YearFilter";
import DuplicateWarning from "./DuplicateWarning";
import InvoiceEditModal from "./InvoiceEditModal";
import Loading from "./Loading";
import { fmtMoney } from "../format";
import * as api from "../api";

export default function ProjectDetail({ projectId, onBack }) {
  const [project, setProject] = useState(null);
  const [items, setItems] = useState([]);
  const [year, setYear] = useState(null);
  const [files, setFiles] = useState([]);
  const [useWeb, setUseWeb] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null); // { done, total, current }
  const [recategorizing, setRecategorizing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [skippedDuplicates, setSkippedDuplicates] = useState([]);
  const [editingInvoice, setEditingInvoice] = useState(null);

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
    setUploadProgress({ done: 0, total: files.length, current: files[0].name });
    try {
      // Jeden plik na request zamiast całej paczki naraz — pozwala pokazać
      // realny postęp (który plik akurat się przetwarza), przydatne przy
      // wielu fakturach naraz, zwłaszcza z włączonym wyszukiwaniem w sieci.
      let lastRes = null;
      for (let i = 0; i < files.length; i++) {
        setUploadProgress({ done: i, total: files.length, current: files[i].name });
        lastRes = await api.addInvoicesToProject(projectId, [files[i]], useWeb);
        setSkippedDuplicates((prev) => [...prev, ...(lastRes.skipped_duplicates || [])]);
      }
      setUploadProgress({ done: files.length, total: files.length, current: null });
      setFiles([]);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  }

  async function handleDeleteInvoice(invoice) {
    if (!window.confirm(`Usunąć fakturę „${invoice.plik}” (${invoice.numer_faktury || "?"})?`)) {
      return;
    }
    try {
      await api.deleteInvoice(projectId, invoice.id);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleSaveInvoiceEdit(fields) {
    await api.updateInvoice(projectId, editingInvoice.id, fields);
    await load();
  }

  async function handleCategoryChange(itemId, kategoriaKlucz) {
    // Optymistyczna aktualizacja — nie czekamy na serwer, żeby dropdown
    // nie "mrugał" z powrotem do starej wartości.
    setItems((prev) =>
      prev.map((it) =>
        it.id === itemId
          ? { ...it, kategoria_klucz: kategoriaKlucz, manual_override: 1 }
          : it
      )
    );
    try {
      await api.updateItemCategory(itemId, kategoriaKlucz);
    } catch (e) {
      setError(e.message);
      await load(); // cofnij optymistyczną zmianę, jeśli zapis się nie udał
    }
  }

  async function handleRecategorize() {
    if (
      !window.confirm(
        "Przeliczyć kategorie wszystkich pozycji tego projektu na nowo? Ręczne poprawki zostaną zachowane."
      )
    ) {
      return;
    }
    setRecategorizing(true);
    setError(null);
    try {
      const res = await api.recategorizeProject(projectId, { useWeb });
      await load();
      window.alert(
        `Przeliczono ${res.changed} pozycji` +
          (res.skipped_manual ? ` (pominięto ${res.skipped_manual} poprawionych ręcznie).` : ".")
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setRecategorizing(false);
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

  if (loading) return <Loading label="Wczytywanie projektu…" />;
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
                <span className="spinner" />
                {uploadProgress
                  ? `Plik ${uploadProgress.done + 1}/${uploadProgress.total}…`
                  : "Przetwarzanie…"}
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
            <InvoicesTable
              invoices={invoices}
              onDelete={handleDeleteInvoice}
              onEdit={setEditingInvoice}
            />
          </section>

          <TrendChart items={items} />

          <div className="toolbar-row">
            <button
              className="btn btn--ghost"
              onClick={handleRecategorize}
              disabled={recategorizing}
            >
              {recategorizing ? <span className="spinner" /> : null} Przelicz kategorie ponownie
            </button>
          </div>

          <section>
            <ItemsTable items={items} onCategoryChange={handleCategoryChange} />
          </section>
        </>
      )}

      {editingInvoice && (
        <InvoiceEditModal
          invoice={editingInvoice}
          onClose={() => setEditingInvoice(null)}
          onSave={handleSaveInvoiceEdit}
        />
      )}
    </div>
  );
}
