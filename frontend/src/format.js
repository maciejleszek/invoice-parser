export function fmtMoney(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("pl-PL", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function fmtMoneyCcy(value, ccy) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${fmtMoney(value)} ${ccy || ""}`.trim();
}
