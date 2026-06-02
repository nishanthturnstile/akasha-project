import { useCallback, useSyncExternalStore } from 'react';

/**
 * Subscribe to a CSS media query. Drives the responsive Layers surface
 * (desktop left drawer vs. mobile bottom sheet) without coupling to a
 * specific breakpoint at the call site.
 *
 * Implemented with `useSyncExternalStore` so the match is read during render
 * (no setState-in-effect) and stays in sync with the external `matchMedia`.
 * SSR/test-safe: returns `false` when `matchMedia` is unavailable.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
        return () => {};
      }
      const mql = window.matchMedia(query);
      // Safari < 14 only supports the deprecated addListener API.
      if (typeof mql.addEventListener === 'function') {
        mql.addEventListener('change', onChange);
        return () => mql.removeEventListener('change', onChange);
      }
      mql.addListener(onChange);
      return () => mql.removeListener(onChange);
    },
    [query],
  );

  const getSnapshot = useCallback(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return false;
    }
    return window.matchMedia(query).matches;
  }, [query]);

  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}

/** Tailwind `md` breakpoint. Above this we render the desktop drawer. */
export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 768px)');
}
