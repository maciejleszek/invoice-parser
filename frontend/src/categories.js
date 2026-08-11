// Musi być spójne z KATEGORIE / KAT_CLR w backend/app/categorizer.py
export const CATEGORY_ORDER = [
  "sygnalizacja_pozaru",
  "elektryka",
  "automatyka",
  "hydraulika",
  "gazownictwo",
  "transport",
  "teletechnika",
  "mechanika",
  "obudowy_szafy",
  "narzedzia",
  "ogolnobudowlane",
  "inne",
];

export const CATEGORY_LABELS = {
  sygnalizacja_pozaru: "Sygnalizacja pożaru",
  elektryka: "Elektryka",
  automatyka: "Automatyka / Sterowniki",
  hydraulika: "Hydraulika / P.poż",
  gazownictwo: "Gazownictwo",
  transport: "Transport / Logistyka",
  teletechnika: "Teletechnika / IT",
  mechanika: "Mechanika / Ślusarka",
  obudowy_szafy: "Obudowy / Szafy elektryczne",
  narzedzia: "Narzędzia / Materiały pomocnicze",
  ogolnobudowlane: "Ogólnobudowlane",
  inne: "Inne / Nieokreślone",
};

export const CATEGORY_COLOR = {
  sygnalizacja_pozaru: "#f87171",
  elektryka: "#60a5fa",
  automatyka: "#34d399",
  hydraulika: "#38bdf8",
  gazownictwo: "#fbbf24",
  transport: "#c084fc",
  teletechnika: "#a3e635",
  mechanika: "#fb923c",
  obudowy_szafy: "#818cf8",
  narzedzia: "#facc15",
  ogolnobudowlane: "#94a3b8",
  inne: "#6b7280",
};

export function categoryColor(key) {
  return CATEGORY_COLOR[key] || CATEGORY_COLOR.inne;
}

export function categoryLabel(key) {
  return CATEGORY_LABELS[key] || key;
}
