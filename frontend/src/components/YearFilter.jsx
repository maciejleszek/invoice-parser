export default function YearFilter({ years, value, onChange }) {
  if (!years.length) return null;
  return (
    <select
      className="select-input"
      value={value ?? "all"}
      onChange={(e) => onChange(e.target.value === "all" ? null : Number(e.target.value))}
    >
      <option value="all">Wszystkie lata</option>
      {years.map((y) => (
        <option key={y} value={y}>
          {y}
        </option>
      ))}
    </select>
  );
}
