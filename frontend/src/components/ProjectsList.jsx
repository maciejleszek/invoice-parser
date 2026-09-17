import { useMemo, useState } from "react";
import Loading from "./Loading";
import * as api from "../api";

function ProjectCard({ project: p, onOpen, onDelete, onUpdateKierownik }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(p.kierownik || "");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await onUpdateKierownik(p.id, value.trim());
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="project-card" onClick={() => !editing && onOpen(p.id)}>
      <div className="project-card__header">
        <h3>{p.name}</h3>
        <button
          type="button"
          className="icon-btn icon-btn--danger"
          title="Usuń projekt"
          onClick={(e) => {
            e.stopPropagation();
            onDelete(p.id, p.name);
          }}
        >
          ×
        </button>
      </div>

      <div className="project-card__kierownik" onClick={(e) => e.stopPropagation()}>
        {editing ? (
          <form
            className="project-kierownik-edit"
            onSubmit={(e) => {
              e.preventDefault();
              save();
            }}
          >
            <input
              type="text"
              className="text-input text-input--sm"
              placeholder="Kierownik projektu…"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              disabled={saving}
              autoFocus
            />
            <button className="btn btn--primary btn--sm" type="submit" disabled={saving}>
              Zapisz
            </button>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={saving}
              onClick={() => {
                setValue(p.kierownik || "");
                setEditing(false);
              }}
            >
              Anuluj
            </button>
          </form>
        ) : (
          <span className="project-card__kierownik-label" onClick={() => setEditing(true)} title="Kliknij, aby edytować">
            {p.kierownik ? <>👤 {p.kierownik}</> : <span className="muted-note">+ dodaj kierownika</span>}
          </span>
        )}
      </div>

      <div className="project-card__stats">
        <span>{p.invoice_count} {p.invoice_count === 1 ? "faktura" : "faktur"}</span>
        <span>{p.item_count} {p.item_count === 1 ? "pozycja" : "pozycji"}</span>
      </div>
      <div className="project-card__date">
        utworzono {new Date(p.created_at).toLocaleDateString("pl-PL")}
      </div>
    </div>
  );
}

export default function ProjectsList({ projects, loading, error, onCreate, onOpen, onDelete, onUpdateKierownik }) {
  const [name, setName] = useState("");
  const [kierownik, setKierownik] = useState("");
  const [creating, setCreating] = useState(false);
  const [kierownikFilter, setKierownikFilter] = useState("");

  const kierownicy = useMemo(() => {
    const set = new Set(projects.map((p) => p.kierownik).filter(Boolean));
    return [...set].sort((a, b) => a.localeCompare(b, "pl"));
  }, [projects]);

  const filteredProjects = kierownikFilter
    ? projects.filter((p) => p.kierownik === kierownikFilter)
    : projects;

  async function handleCreate(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    try {
      await onCreate(name.trim(), kierownik.trim());
      setName("");
      setKierownik("");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div>
      <section className="panel">
        <form className="project-create" onSubmit={handleCreate}>
          <input
            type="text"
            className="text-input"
            placeholder="Nazwa nowego projektu…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={creating}
          />
          <input
            type="text"
            className="text-input"
            placeholder="Kierownik projektu (opcjonalnie)…"
            value={kierownik}
            onChange={(e) => setKierownik(e.target.value)}
            disabled={creating}
          />
          <button className="btn btn--primary" type="submit" disabled={creating || !name.trim()}>
            + Nowy projekt
          </button>
          <a className="btn btn--ghost" href={api.backupUrl()} title="Pobierz kopię całej bazy danych">
            ⬇ Kopia zapasowa
          </a>
        </form>
        {error && <div className="alert alert--error">{error}</div>}
      </section>

      {kierownicy.length > 0 && (
        <div className="project-filter-bar">
          <label htmlFor="kierownik-filter">Filtruj po kierowniku:</label>
          <select
            id="kierownik-filter"
            className="select-input"
            value={kierownikFilter}
            onChange={(e) => setKierownikFilter(e.target.value)}
          >
            <option value="">Wszyscy kierownicy</option>
            {kierownicy.map((k) => (
              <option key={k} value={k}>{k}</option>
            ))}
          </select>
        </div>
      )}

      {loading && <Loading label="Wczytywanie projektów…" />}

      {!loading && projects.length === 0 && (
        <p className="muted-note">
          Nie masz jeszcze żadnego projektu. Utwórz pierwszy powyżej, żeby zacząć wgrywać do niego
          faktury.
        </p>
      )}

      {!loading && projects.length > 0 && filteredProjects.length === 0 && (
        <p className="muted-note">Żaden projekt nie pasuje do wybranego kierownika.</p>
      )}

      {filteredProjects.length > 0 && (
        <div className="project-grid">
          {filteredProjects.map((p) => (
            <ProjectCard
              key={p.id}
              project={p}
              onOpen={onOpen}
              onDelete={onDelete}
              onUpdateKierownik={onUpdateKierownik}
            />
          ))}
        </div>
      )}
    </div>
  );
}
