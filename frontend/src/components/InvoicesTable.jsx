import { fmtMoney } from "../format";

export default function InvoicesTable({ invoices, onDelete }) {
  if (!invoices.length) return null;

  return (
    <div className="table-card">
      <h3 className="table-card__title">Faktury ({invoices.length})</h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Plik</th>
              <th>Numer faktury</th>
              <th>Sprzedawca</th>
              <th>Data faktury</th>
              <th>Termin płatności</th>
              <th className="num">Netto</th>
              <th className="num">Brutto</th>
              <th>Waluta</th>
              {onDelete && <th></th>}
            </tr>
          </thead>
          <tbody>
            {invoices.map((h, i) => (
              <tr key={h.id ?? i}>
                <td className="mono" title={h.plik}>
                  {h.plik}
                </td>
                <td>{h.numer_faktury || "—"}</td>
                <td>{h.sprzedawca || "—"}</td>
                <td>{h.data_faktury || "—"}</td>
                <td>{h.termin_platnosci || "—"}</td>
                <td className="num">{fmtMoney(h.razem_netto)}</td>
                <td className="num">{fmtMoney(h.razem_brutto)}</td>
                <td>{h.waluta || "—"}</td>
                {onDelete && (
                  <td>
                    <button
                      type="button"
                      className="icon-btn icon-btn--danger"
                      title="Usuń fakturę"
                      onClick={() => onDelete(h.id)}
                    >
                      ×
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
