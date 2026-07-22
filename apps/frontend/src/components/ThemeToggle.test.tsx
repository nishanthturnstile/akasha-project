import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { ThemeToggle } from '@/components/ThemeToggle';
import { THEME_STORAGE_KEY } from '@/lib/theme';

describe('ThemeToggle', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove('dark');
    document.documentElement.style.colorScheme = '';
  });

  it('starts in light mode and persists dark after toggling', () => {
    render(<ThemeToggle />);
    const toggle = screen.getByTestId('theme-toggle');

    expect(toggle.getAttribute('aria-label')).toBe('Switch to dark theme');
    expect(document.documentElement.style.colorScheme).toBe('light');

    fireEvent.click(toggle);

    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe('dark');
  });

  it('restores a saved dark preference', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    render(<ThemeToggle />);
    expect(screen.getByTestId('theme-toggle').getAttribute('aria-label')).toBe('Switch to light theme');
  });
});
