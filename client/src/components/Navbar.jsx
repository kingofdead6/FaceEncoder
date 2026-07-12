/** Top navigation: brand, page links, backend status, theme switch. */
import { NavLink } from "react-router-dom";
import { FiMoon, FiSun } from "react-icons/fi";
import { useApp } from "../context/AppContext";
import ConnectionStatus from "./ConnectionStatus";

function Aperture({ className = "" }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <circle cx="16" cy="16" r="13" fill="none" stroke="#22D3EE" strokeWidth="2.4" />
      <circle cx="16" cy="16" r="5.2" fill="#8B5CF6" />
      <path d="M16 3v6M29 16h-6M16 29v-6M3 16h6" stroke="#22D3EE" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

const linkClass = ({ isActive }) =>
  `rounded-lg px-3 py-1.5 text-sm transition-colors ${
    isActive ? "bg-panel2 text-ink border border-edge" : "text-muted hover:text-ink"
  }`;

export default function Navbar() {
  const { theme, setTheme } = useApp();

  return (
    <header className="sticky top-0 z-40 border-b border-edge bg-surface/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6">
        <NavLink to="/" className="flex items-center gap-2.5">
          <Aperture className="h-7 w-7" />
          <span className="font-display text-lg font-bold tracking-tight">
            Vision<span className="text-signal">Shield</span>
          </span>
        </NavLink>

        <nav className="ml-2 hidden items-center gap-1 sm:flex" aria-label="Primary">
          <NavLink to="/" end className={linkClass}>
            Dashboard
          </NavLink>
      
        </nav>

        <div className="ml-auto flex items-center gap-2.5">
          <ConnectionStatus />
          <button
            type="button"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="btn-ghost h-9 w-9 !p-0"
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme === "dark" ? "Light mode" : "Dark mode"}
          >
            {theme === "dark" ? <FiSun /> : <FiMoon />}
          </button>
        </div>
      </div>

      {/* Mobile page links */}
      <nav className="flex gap-1 px-4 pb-2 sm:hidden" aria-label="Primary mobile">
        <NavLink to="/" end className={linkClass}>
          Dashboard
        </NavLink>
        <NavLink to="/api-docs" className={linkClass}>
          API docs
        </NavLink>
      </nav>
    </header>
  );
}
