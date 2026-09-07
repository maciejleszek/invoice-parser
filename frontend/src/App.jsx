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

  async function handleCreate(name) {
    setError(null);
    try {
      const project = await api.createProject(name);
      setProjects((prev) => [{ ...project, invoice_count: 0, item_count: 0 }, ...prev]);
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
    />
  );
}

function QuickAnalysis() {
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
      setResult(await api.processQuick(files, useWeb));
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
            <InvoicesTable invoices={result.invoices} />
          </section>

          <section>
            <ItemsTable items={result.items} />
          </section>
        </>
      )}
    </>
  );
}
