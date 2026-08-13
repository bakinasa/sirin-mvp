import { NavLink } from "react-router-dom";
import { Moon, Sun } from "lucide-react";
import { useAuthStore } from "../store/auth";
import clsx from "clsx";

const links = [
  { to: "/", label: "Проекты" },
  { to: "/models", label: "Модели" },
  { to: "/prompts", label: "Промты" },
  { to: "/future", label: "Скоро" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { dark, toggleDark, setToken, token } = useAuthStore();

  return (
    <div className="min-h-screen bg-white text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      <header className="sticky top-0 z-40 border-b border-neutral-200 bg-white/95 backdrop-blur dark:border-neutral-800 dark:bg-neutral-950/95">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2">
            <span className="text-lg font-semibold tracking-tight">Сирин · AI Studio 360</span>
          </NavLink>
          <nav className="hidden items-center gap-1 md:flex">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  clsx(
                    "rounded-md px-3 py-1.5 text-sm font-medium transition",
                    isActive
                      ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
                      : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
                  )
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <button className="btn-ghost" onClick={toggleDark} aria-label="Тема">
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            {token && (
              <button className="btn-ghost" onClick={() => setToken(null)}>
                Выйти
              </button>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8">{children}</main>
    </div>
  );
}
