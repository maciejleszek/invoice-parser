import { useEffect, useState } from "react";

function getInitialTheme() {
  try {
    const saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* localStorage niedostępny (np. tryb prywatny) — użyj domyślnego */
  }
  return "light";
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* ignoruj — motyw po prostu nie przetrwa odświeżenia */
    }
  }, [theme]);

  const isDark = theme === "dark";
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      title={isDark ? "Przełącz na jasny motyw" : "Przełącz na ciemny motyw"}
      aria-label="Przełącz motyw"
    >
      {isDark ? "☀️" : "🌙"}
    </button>
  );
}
