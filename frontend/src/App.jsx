import { useEffect, useMemo, useState } from "react";
import UploadZone from "./components/UploadZone";
import StatTile from "./components/StatTile";
import CategoryChart from "./components/CategoryChart";
import InvoicesTable from "./components/InvoicesTable";
import ItemsTable from "./components/ItemsTable";
import ProjectsList from "./components/ProjectsList";
import ProjectDetail from "./components/ProjectDetail";
import Dashboard from "./components/Dashboard";
import ThemeToggle from "./components/ThemeToggle";
import DuplicateWarning from "./components/DuplicateWarning";
import AnalysisQualityBanner from "./components/AnalysisQualityBanner";
import InvoiceEditModal from "./components/InvoiceEditModal";
import { fmtMoney } from "./format";
import * as api from "./api";
import "./App.css";

const TABS = [
  { key: "quick", label: "Szybka analiza" },
  { key: "projects", label: "Projekty" },
  { key: "dashboard", label: "Podsumowanie roczne" },
];

export default function App() {
  const [tab, setTab] = useState("quick");
  const [activeProjectId, setActiveProjectId] = useState(null);

  function goToProjects() {
    setActiveProjectId(null);
    setTab("projects");
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__top">
          <div className="app-header__brand">
            <div className="app-logo">
              <img src="/dekk-logo.png" alt="DEKK Fire Solutions" />
            </div>
            <div>
              <h1>Kategoryzacja faktur</h1>
              <p className="app-header__subtitle">
                Wgraj faktury PDF, a aplikacja rozpozna dostawcę, wyciągnie pozycje i przypisze im
                kategorię kosztową.
              </p>
            </div>
          </div>
          <ThemeToggle />
        </div>
        <nav className="app-nav">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`app-nav__item ${tab === t.key ? "app-nav__item--active" : ""}`}
              onClick={() => (t.key === "projects" ? goToProjects() : setTab(t.key))}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      {tab === "quick" && <QuickAnalysis />}
      {tab === "projects" &&
        (activeProjectId ? (
          <ProjectDetail projectId={activeProjectId} onBack={goToProjects} />
        ) : (
          <ProjectsPanel onOpen={setActiveProjectId} />
        ))}
      {tab === "dashboard" && <Dashboard />}
    </div>
  );
}

function ProjectsPanel({ onOpen }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  function reload() {
    setLoading(true);
    api
      .listProjects()
      .then(setProjects)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(reload, []);

  async function handleCreate(name, kierownik) {
    setError(null);
    try {
      const project = await api.createProject(name, kierownik);
      setProjects((prev) => [{ ...project, invoice_count: 0, item_count: 0 }, ...prev]);
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleUpdateKierownik(id, kierownik) {
    setError(null);
    try {
      const updated = await api.updateProject(id, { kierownik });
      setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, ...updated } : p)));
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleDelete(id, name) {
    if (!window.confirm(`Usunąć projekt „${name}” wraz ze wszystkimi fakturami?`)) return;
    try {
      await api.deleteProject(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <ProjectsList
      projects={projects}
      loading={loading}
      error={error}
      onCreate={handleCreate}
      onOpen={onOpen}
      onDelete={handleDelete}
      onUpdateKierownik={handleUpdateKierownik}
    />
  );
}

// Klucz (numer faktury, sprzedawca) do wykrywania duplikatów po stronie
// klienta — ta sama logika co _invoice_key() w backendzie, potrzebna tu
// osobno, bo scalanie wyników kolejnych partii plików dzieje się w GUI.
function quickInvoiceKey(h) {
  const numer = (h.numer_faktury || "").trim().toLowerCase();
  const sprzedawca = (h.sprzedawca || "").trim().toLowerCase();
  return numer && sprzedawca ? `${numer}|${sprzedawca}` : null;
}

function QuickAnalysis() {
  const [files, setFiles] = useState([]);
  const [useWeb, setUseWeb] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null); // { job_id, invoices, items, duplicate_warnings }
  const [editingInvoice, setEditingInvoice] = useState(null);
  const [skippedDuplicates, setSkippedDuplicates] = useState([]);

  const brutoByCurrency = useMemo(() => {
    if (!result) return [];
    const agg = new Map();
    for (const h of result.invoices) {
      const ccy = h.waluta || "PLN";
      agg.set(ccy, (agg.get(ccy) || 0) + (h.razem_brutto || 0));
    }
    return Array.from(agg.entries());
  }, [result]);

  // Excel do pobrania jest budowany po stronie backendu z aktualnego stanu
  // (invoices/items) za każdym razem, gdy coś się zmienia (nowa paczka,
  // ręczna poprawka, usunięcie faktury) — żeby plik zawsze odzwierciedlał
  // to, co widać na ekranie, a nie tylko pierwotny (błędny) odczyt.
  async function syncJob(invoices, items) {
    const { job_id } = await api.rebuildQuickWorkbook(invoices, items);
    return job_id;
  }

  async function handleProcess() {
    if (!files.length) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.processQuick(files, useWeb);
      const baseInvoices = result ? result.invoices : [];
      const baseItems = result ? result.items : [];
      const seenPliki = new Set(baseInvoices.map((h) => h.plik));
      const seenKeys = new Set(baseInvoices.map(quickInvoiceKey).filter(Boolean));

      const mergeDuplicates = [];
      const newInvoices = [];
      for (const h of res.invoices) {
        const key = quickInvoiceKey(h);
        if (seenPliki.has(h.plik)) {
          mergeDuplicates.push({ plik: h.plik, reason: "identical_file" });
          continue;
        }
        if (key && seenKeys.has(key)) {
          mergeDuplicates.push({
            plik: h.plik,
            numer_faktury: h.numer_faktury,
            sprzedawca: h.sprzedawca,
            reason: "same_invoice_number",
          });
          continue;
        }
        newInvoices.push(h);
        seenPliki.add(h.plik);
        if (key) seenKeys.add(key);
      }
      const keptPliki = new Set(newInvoices.map((h) => h.plik));
      const newItems = res.items.filter((it) => keptPliki.has(it.plik));

      const mergedInvoices = [...baseInvoices, ...newInvoices];
      const mergedItems = [...baseItems, ...newItems];
      const jobId = await syncJob(mergedInvoices, mergedItems);

      setResult({
        job_id: jobId,
        invoices: mergedInvoices,
        items: mergedItems,
        duplicate_warnings: res.duplicate_warnings || [],
      });
      if (mergeDuplicates.length) {
        setSkippedDuplicates((prev) => [...prev, ...mergeDuplicates]);
      }
      setFiles([]);
    } catch (e) {
      setError(
        e.message === "Failed to fetch"
          ? `Nie udało się połączyć z API (${api.API_URL}). Upewnij się, że backend jest uruchomiony.`
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
    setSkippedDuplicates([]);
  }

  async function handleSaveInvoiceEdit(fields) {
    const old = editingInvoice;
    const updatedInvoices = result.invoices.map((h) =>
      h.plik === old.plik ? { ...h, ...fields } : h
    );
    const cascade = {
      numer_faktury: fields.numer_faktury,
      sprzedawca: fields.sprzedawca,
      data_faktury: fields.data_faktury,
      waluta: fields.waluta,
    };
    const updatedItems = result.items.map((it) =>
      it.plik === old.plik ? { ...it, ...cascade } : it
    );
    const jobId = await syncJob(updatedInvoices, updatedItems);
    setResult({ ...result, job_id: jobId, invoices: updatedInvoices, items: updatedItems });
  }

  async function handleDeleteInvoice(h) {
    if (
      !window.confirm(
        `Usunąć fakturę „${h.plik}” (${h.numer_faktury || "?"}) z wyników? Będziesz mógł wgrać poprawiony plik ponownie.`
      )
    ) {
      return;
    }
    const remainingInvoices = result.invoices.filter((x) => x.plik !== h.plik);
    const remainingItems = result.items.filter((it) => it.plik !== h.plik);
    if (!remainingInvoices.length) {
      setResult(null);
      return;
    }
    try {
      const jobId = await syncJob(remainingInvoices, remainingItems);
      setResult({ ...result, job_id: jobId, invoices: remainingInvoices, items: remainingItems });
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <>
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
            Użyj wyszukiwania w internecie (wolniejsze, dokładniejsze dla nieznanych produktów)
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
              ) : result ? (
                `Dodaj do wyników (${files.length})`
              ) : (
                `Kategoryzuj (${files.length})`
              )}
            </button>
          </div>
        </div>

        {error && <div className="alert alert--error">{error}</div>}
        {result && <DuplicateWarning duplicates={result.duplicate_warnings} />}
        <DuplicateWarning duplicates={skippedDuplicates} skipped />
      </section>

      {result && (
        <>
          <AnalysisQualityBanner invoices={result.invoices} items={result.items} />

          <section className="stats-row">
            <StatTile label="Faktury" value={result.invoices.length} />
            <StatTile label="Pozycje" value={result.items.length} />
            {brutoByCurrency.map(([ccy, val]) => (
              <StatTile key={ccy} label={`Suma brutto (${ccy})`} value={fmtMoney(val)} />
            ))}
            <div className="stat-tile stat-tile--action">
              <a className="btn btn--primary" href={api.downloadQuickUrl(result.job_id)}>
                ⬇ Pobierz Excel
              </a>
            </div>
          </section>

          <section className="content-grid">
            <CategoryChart items={result.items} />
            <InvoicesTable
              invoices={result.invoices}
              onEdit={setEditingInvoice}
              onDelete={handleDeleteInvoice}
            />
          </section>

          <section>
            <ItemsTable items={result.items} />
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
    </>
  );
}
