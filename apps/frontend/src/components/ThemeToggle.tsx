import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { applyTheme, readInitialTheme, THEME_STORAGE_KEY, type Theme } from '@/lib/theme';

/** Light-first CIDSA theme toggle; an explicit user choice persists across reloads. */
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
      className="glass-card flex size-10 items-center justify-center rounded-pill text-foreground transition-transform duration-fast ease-standard hover:-translate-y-0.5 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {theme === 'dark' ? (
        <Moon className="size-[18px]" strokeWidth={1.75} />
      ) : (
        <Sun className="size-[18px]" strokeWidth={1.75} />
      )}
    </button>
  );
}
