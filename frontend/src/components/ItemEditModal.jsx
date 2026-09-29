import { useState } from "react";
import Modal from "./Modal";

const FIELDS = [
  { key: "opis", label: "Opis" },
  { key: "indeks", label: "Indeks" },
  { key: "pkwiu", label: "PKWiU" },
  { key: "ilosc", label: "Ilość", type: "number" },
  { key: "jm", label: "JM" },
  { key: "cena_netto", label: "Cena netto", type: "number" },
  { key: "wartosc_netto", label: "Wartość netto", type: "number" },
  { key: "stawka_vat", label: "Stawka VAT" },
  { key: "kwota_vat", label: "Kwota VAT", type: "number" },
  { key: "wartosc_brutto", label: "Wartość brutto", type: "number" },
];

export default function ItemEditModal({ item, onClose, onSave }) {
  const [values, setValues] = useState(() =>
    Object.fromEntries(FIELDS.map((f) => [f.key, item[f.key] ?? ""]))
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  function setField(key, val) {
    setValues((v) => ({ ...v, [key]: val }));
  }

  // Bug: Enter w dowolnym z 10 pól domyślnie wysyła cały formularz (tak
  // działa zwykły <form> w przeglądarce) — dla użytkownika wyglądało to
  // jak samoistne zamknięcie okna zaraz po wpisaniu wartości w pole, choć
  // w rzeczywistości formularz się zapisywał i zamykał przedwcześnie,
  // zanim zdążył poprawić resztę pól. Enter ma po prostu nic nie robić,
  // dopóki nie jest naciśnięty na samym przycisku „Zapisz”.
  function handleFormKeyDown(e) {
    if (e.key === "Enter" && e.target.tagName === "INPUT") {
      e.preventDefault();
    }
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
    <Modal title={`Popraw pozycję — ${item.numer_faktury || item.plik || ""}`} onClose={onClose}>
      <form
        onSubmit={handleSubmit}
        onKeyDown={handleFormKeyDown}
        className="modal-panel__body"
        style={{ padding: 0 }}
      >
        {FIELDS.map((f) => (
          <div className="field" key={f.key}>
            <label className="field-label" htmlFor={`item-${f.key}`}>
              {f.label}
            </label>
            <input
              id={`item-${f.key}`}
              className="text-input"
              type={f.type === "number" ? "number" : "text"}
              step={f.type === "number" ? "0.001" : undefined}
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
