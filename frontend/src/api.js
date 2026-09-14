// `??` (nie `||`) celowo — na Vercelu backend i frontend są pod tym samym
// origin (vercel.json kieruje /api/* do funkcji serverless), więc
// VITE_API_URL jest tam ustawione na PUSTY STRING (żeby fetch('' + '/api/x')
// trafiał względnie, na ten sam origin). `||` potraktowałoby pusty string
// jak "nieustawione" i i tak wróciłoby do localhost:8000, co zepsułoby
// deployment. Lokalnie/w Dockerze .env normalnie ustawia realny URL.
export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Serwer zwrócił błąd ${res.status}`);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : null;
}

function qs(params) {
  const entries = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (!entries.length) return "";
  return "?" + new URLSearchParams(entries).toString();
}

// ── Szybka analiza (bezstanowa) ─────────────────────────────────────

export async function processQuick(files, useWeb) {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  form.append("use_web", useWeb ? "true" : "false");
  return request("/api/process", { method: "POST", body: form });
}

export function downloadQuickUrl(jobId) {
  return `${API_URL}/api/download/${jobId}`;
}

// ── Projekty ─────────────────────────────────────────────────────────

export function listProjects() {
  return request("/api/projects");
}

export function createProject(name) {
  return request("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function getProject(id) {
  return request(`/api/projects/${id}`);
}

export function deleteProject(id) {
  return request(`/api/projects/${id}`, { method: "DELETE" });
}

export async function addInvoicesToProject(projectId, files, useWeb) {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  form.append("use_web", useWeb ? "true" : "false");
  return request(`/api/projects/${projectId}/invoices`, { method: "POST", body: form });
}

export function deleteInvoice(projectId, invoiceId) {
  return request(`/api/projects/${projectId}/invoices/${invoiceId}`, { method: "DELETE" });
}

export function updateInvoice(projectId, invoiceId, fields) {
  return request(`/api/projects/${projectId}/invoices/${invoiceId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
}

export function downloadProjectUrl(projectId, year) {
  return `${API_URL}/api/projects/${projectId}/download${qs({ year })}`;
}

export function recategorizeProject(projectId, { invoiceId, useWeb, force } = {}) {
  return request(
    `/api/projects/${projectId}/recategorize${qs({
      invoice_id: invoiceId,
      use_web: useWeb ? "true" : undefined,
      force: force ? "true" : undefined,
    })}`,
    { method: "POST" }
  );
}

// ── Pozycje / kategorie (globalnie albo per projekt) ────────────────

export function listItems({ projectId, year } = {}) {
  return request(`/api/items${qs({ project_id: projectId, year })}`);
}

export function listYears({ projectId } = {}) {
  return request(`/api/years${qs({ project_id: projectId })}`);
}

export function updateItemCategory(itemId, kategoriaKlucz) {
  return request(`/api/items/${itemId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kategoria_klucz: kategoriaKlucz }),
  });
}

// ── Kopia zapasowa ───────────────────────────────────────────────────

export function backupUrl() {
  return `${API_URL}/api/backup`;
}
