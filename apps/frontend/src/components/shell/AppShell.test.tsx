import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AppShell } from '@/components/shell/AppShell';

function renderShell(path = '/weather/forecast') {
  return render(
    <MemoryRouter initialEntries={ [path] }>
      <Routes>
        <Route element={ <AppShell /> }>
          <Route path="weather/forecast" element={ <div data-testid="forecast-page">Forecast</div> } />
          <Route
            path="monitoring/field-analytics"
            element={ <div data-testid="field-analytics-page">Field analytics</div> }
          />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('AppShell', () => {
  it('renders persistent product navigation and outlet content', () => {
    renderShell();

    expect(screen.getByTestId('product-shell')).toBeTruthy();
    expect(screen.getByTestId('forecast-page')).toBeTruthy();
    expect(screen.getByTestId('nav-link-forecast').getAttribute('aria-current')).toBe('page');
    expect(screen.getByTestId('nav-link-field-analytics')).toBeTruthy();
  });

  it('highlights the selected monitoring route', () => {
    renderShell('/monitoring/field-analytics');

    expect(screen.getByTestId('field-analytics-page')).toBeTruthy();
    expect(screen.getByTestId('nav-link-field-analytics').getAttribute('aria-current')).toBe(
      'page',
    );
  });
});
