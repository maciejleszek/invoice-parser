export default function StatTile({ label, value, sub }) {
  return (
    <div className="stat-tile">
      <div className="stat-tile__label">{label}</div>
      <div className="stat-tile__value">{value}</div>
      {sub && <div className="stat-tile__sub">{sub}</div>}
    </div>
  );
}
