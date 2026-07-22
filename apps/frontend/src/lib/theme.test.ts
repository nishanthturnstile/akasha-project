import { beforeEach, describe, expect, it } from 'vitest';
import { applyTheme, readInitialTheme, THEME_STORAGE_KEY } from '@/lib/theme';

describe('CIDSA theme resolution', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove('dark');
    document.documentElement.style.colorScheme = '';
  });

  it('defaults to light when no preference exists', () => {
    expect(readInitialTheme()).toBe('light');
  });

  it('restores an explicit stored dark preference', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    expect(readInitialTheme()).toBe('dark');
  });

  it('applies matching class and color-scheme state', () => {
    applyTheme('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe('dark');

    applyTheme('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe('light');
  });
});
