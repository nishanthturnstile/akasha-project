import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';

type Theme = 'dark' | 'light';

const THEME_STORAGE_KEY = 'akasha.theme';

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle('dark', theme === 'dark');
  root.style.colorScheme = theme;
}

/** Resolve the initial theme: persisted choice → OS preference → dark default. */
function readInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'dark';
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    /* storage unavailable (private mode / quota) */
  }
  if (window.matchMedia?.('(prefers-color-scheme: light)').matches) return 'light';
  return 'dark';
}

/** Default dark (imagery reads best on ink); the user's choice persists across reloads. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => {
    const initial = readInitialTheme();
    // Apply synchronously during the first render so there is no light→dark flash
    // (the pre-hydration script in index.html covers the very first paint).
    if (typeof document !== 'undefined') applyTheme(initial);
    return initial;
  });

  useEffect(() => {
    applyTheme(theme);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      /* storage unavailable (private mode / quota) */
    }
  }, [theme]);

  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      data-testid="theme-toggle"
      className="glass flex size-10 items-center justify-center rounded-pill text-foreground transition-transform duration-fast ease-standard hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {theme === 'dark' ? (
        <Moon className="size-[18px]" strokeWidth={1.75} />
      ) : (
        <Sun className="size-[18px]" strokeWidth={1.75} />
      )}
    </button>
  );
}
