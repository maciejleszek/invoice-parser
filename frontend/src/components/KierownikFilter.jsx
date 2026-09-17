export default function KierownikFilter({ kierownicy, value, onChange }) {
  if (!kierownicy.length) return null;
  return (
    <select
      className="select-input"
      value={value ?? "all"}
      onChange={(e) => onChange(e.target.value === "all" ? null : e.target.value)}
    >
      <option value="all">Wszyscy kierownicy</option>
      {kierownicy.map((k) => (
        <option key={k} value={k}>
          {k}
        </option>
      ))}
    </select>
  );
}
