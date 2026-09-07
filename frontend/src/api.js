export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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

export function downloadProjectUrl(projectId, year) {
  return `${API_URL}/api/projects/${projectId}/download${qs({ year })}`;
}

// ── Pozycje / kategorie (globalnie albo per projekt) ────────────────

export function listItems({ projectId, year } = {}) {
  return request(`/api/items${qs({ project_id: projectId, year })}`);
}

export function listYears({ projectId } = {}) {
  return request(`/api/years${qs({ project_id: projectId })}`);
}
