import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ReportingPage from '@/pages/reports/ReportingPage';

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => payload,
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={ queryClient }>
      <ReportingPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ReportingPage', () => {
  it('creates and edits report templates with selectable columns', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === '/api/reports/templates' && init?.method === 'POST') {
        return Promise.resolve(
          jsonResponse({ id: 'template-1', name: 'Field health summary', columns: ['field'] }, 201),
        );
      }
      if (String(input) === '/api/reports/templates/template-1' && init?.method === 'PATCH') {
        return Promise.resolve(jsonResponse({ id: 'template-1', name: 'Updated', columns: ['field'] }));
      }
      return Promise.resolve(
        jsonResponse([{ id: 'template-1', name: 'Saved summary', columns: ['field'], filters: {}, sort: {} }]),
      );
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPage();

    await waitFor(() => expect(screen.getByText('Saved summary')).toBeTruthy());
    fireEvent.click(screen.getByLabelText('Actual yield'));
    fireEvent.click(screen.getByRole('button', { name: 'Create template' }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/reports/templates',
        expect.objectContaining({ method: 'POST' }),
      ),
    );

    fireEvent.click(screen.getByText('Saved summary'));
    fireEvent.change(screen.getByLabelText('Template name'), { target: { value: 'Updated' } });
    fireEvent.click(screen.getByRole('button', { name: 'Update template' }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/reports/templates/template-1',
        expect.objectContaining({ method: 'PATCH' }),
      ),
    );
  });
});
