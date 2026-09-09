export default function Loading({ label = "Wczytywanie…" }) {
  return (
    <div className="loading-state">
      <div className="loading-bars" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      {label}
    </div>
  );
}
