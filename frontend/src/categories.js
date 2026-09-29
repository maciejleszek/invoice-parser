// Musi być spójne z KATEGORIE / KAT_CLR w backend/app/categorizer.py
export const CATEGORY_ORDER = [
  "rurociagi_prefabrykacja",
  "armatura_tryskaczowa",
  "mocowania_podwieszenia",
  "urzadzenia_pompownie",
  "instalacje_elektryczne",
  "detekcja_sygnalizacja",
  "zabezpieczenia_ogniochronne",
  "uslugi_podwykonawcow",
  "uslugi_obce",
  "wynajem_sprzetu",
  "zaplecze_budowy",
  "transport_logistyka",
  "materialy_pomocnicze",
  "rozliczenia_pracownicze",
  "bez_wplywu_na_koszt",
  "inne",
];

export const CATEGORY_LABELS = {
  rurociagi_prefabrykacja: "Rurociągi i prefabrykacja",
  armatura_tryskaczowa: "Rurociągi, armatura i osprzęt tryskaczowy",
  mocowania_podwieszenia: "Systemy mocowań i podwieszeń",
  urzadzenia_pompownie: "Urządzenia, pompownie i zestawy hydrantowe",
  instalacje_elektryczne: "Instalacje elektryczne i okablowanie ppoż.",
  detekcja_sygnalizacja: "Systemy detekcji i sygnalizacji pożaru (SSP)",
  zabezpieczenia_ogniochronne: "Zabezpieczenia ogniochronne i izolacje",
  uslugi_podwykonawcow: "Usługi podwykonawców – montaż",
  uslugi_obce: "Usługi obce – rozruch, odbiory, pomiary",
  wynajem_sprzetu: "Wynajem sprzętu i transport maszyn",
  zaplecze_budowy: "Zaplecze budowy i wynajem kontenerów",
  transport_logistyka: "Transport i logistyka",
  materialy_pomocnicze: "Materiały pomocnicze, BHP i chemia",
  rozliczenia_pracownicze: "Rozliczenia pracownicze, paliwo i delegacje",
  bez_wplywu_na_koszt: "Pozycje bez wpływu na koszt",
  inne: "Inne / Nieokreślone",
};

export const CATEGORY_COLOR = {
  rurociagi_prefabrykacja: "#38bdf8",
  armatura_tryskaczowa: "#0ea5e9",
  mocowania_podwieszenia: "#fb923c",
  urzadzenia_pompownie: "#06b6d4",
  instalacje_elektryczne: "#60a5fa",
  detekcja_sygnalizacja: "#f87171",
  zabezpieczenia_ogniochronne: "#fbbf24",
  uslugi_podwykonawcow: "#a78bfa",
  uslugi_obce: "#e879f9",
  wynajem_sprzetu: "#fb7185",
  zaplecze_budowy: "#94a3b8",
  transport_logistyka: "#c084fc",
  materialy_pomocnicze: "#facc15",
  rozliczenia_pracownicze: "#a3e635",
  bez_wplywu_na_koszt: "#d1d5db",
  inne: "#6b7280",
};

export function categoryColor(key) {
  return CATEGORY_COLOR[key] || CATEGORY_COLOR.inne;
}

export function categoryLabel(key) {
  return CATEGORY_LABELS[key] || key;
}
