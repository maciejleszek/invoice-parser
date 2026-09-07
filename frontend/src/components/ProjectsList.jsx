import { useState } from "react";

export default function ProjectsList({ projects, loading, error, onCreate, onOpen, onDelete }) {
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  async function handleCreate(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    try {
      await onCreate(name.trim());
      setName("");
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
          <button className="btn btn--primary" type="submit" disabled={creating || !name.trim()}>
            + Nowy projekt
          </button>
        </form>
        {error && <div className="alert alert--error">{error}</div>}
      </section>

      {loading && <p className="muted-note">Wczytywanie projektów…</p>}

      {!loading && projects.length === 0 && (
        <p className="muted-note">
          Nie masz jeszcze żadnego projektu. Utwórz pierwszy powyżej, żeby zacząć wgrywać do niego
          faktury.
        </p>
      )}

      {projects.length > 0 && (
        <div className="project-grid">
          {projects.map((p) => (
            <div className="project-card" key={p.id} onClick={() => onOpen(p.id)}>
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
              <div className="project-card__stats">
                <span>{p.invoice_count} {p.invoice_count === 1 ? "faktura" : "faktur"}</span>
                <span>{p.item_count} {p.item_count === 1 ? "pozycja" : "pozycji"}</span>
              </div>
              <div className="project-card__date">
                utworzono {new Date(p.created_at).toLocaleDateString("pl-PL")}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
