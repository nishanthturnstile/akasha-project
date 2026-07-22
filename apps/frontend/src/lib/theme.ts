export type Theme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'akasha.theme';

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle('dark', theme === 'dark');
  root.style.colorScheme = theme;
}

/** CIDSA is light-first. Only an explicit saved choice overrides the light default. */
export function readInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light';
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    // Storage can be unavailable in private or hardened browser contexts.
  }
  return 'light';
}
