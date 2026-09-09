import { useState } from "react";
import Modal from "./Modal";

const FIELDS = [
  { key: "numer_faktury", label: "Numer faktury" },
  { key: "sprzedawca", label: "Sprzedawca" },
  { key: "data_faktury", label: "Data faktury" },
  { key: "termin_platnosci", label: "Termin płatności" },
  { key: "numer_zamowienia", label: "Nr zamówienia" },
  { key: "waluta", label: "Waluta" },
  { key: "razem_netto", label: "Razem netto", type: "number" },
  { key: "razem_brutto", label: "Razem brutto", type: "number" },
];

export default function InvoiceEditModal({ invoice, onClose, onSave }) {
  const [values, setValues] = useState(() =>
    Object.fromEntries(FIELDS.map((f) => [f.key, invoice[f.key] ?? ""]))
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  function setField(key, val) {
    setValues((v) => ({ ...v, [key]: val }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = {};
      for (const f of FIELDS) {
        const raw = values[f.key];
        if (f.type === "number") {
          payload[f.key] = raw === "" ? null : Number(raw);
        } else {
          payload[f.key] = raw === "" ? null : raw;
        }
      }
      await onSave(payload);
      onClose();
    } catch (e2) {
      setError(e2.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={`Popraw fakturę — ${invoice.plik}`} onClose={onClose}>
      <form onSubmit={handleSubmit} className="modal-panel__body" style={{ padding: 0 }}>
        {FIELDS.map((f) => (
          <div className="field" key={f.key}>
            <label className="field-label" htmlFor={`inv-${f.key}`}>
              {f.label}
            </label>
            <input
              id={`inv-${f.key}`}
              className="text-input"
              type={f.type === "number" ? "number" : "text"}
              step={f.type === "number" ? "0.01" : undefined}
              value={values[f.key]}
              onChange={(e) => setField(f.key, e.target.value)}
              disabled={saving}
            />
          </div>
        ))}
        {error && <div className="alert alert--error">{error}</div>}
        <div className="modal-panel__footer" style={{ padding: "4px 0 0" }}>
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={saving}>
            Anuluj
          </button>
          <button type="submit" className="btn btn--primary" disabled={saving}>
            {saving ? <span className="spinner" /> : null} Zapisz
          </button>
        </div>
      </form>
    </Modal>
  );
}
