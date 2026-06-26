import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthGate } from '@/components/auth/AuthGate';
import { MAIN_MONITORING_ROUTE } from '@/routes/productNavigation';

function mockAccount(role: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        user: {
          id: 'u1',
          username: 'dev',
          email: 'dev@example.test',
          displayName: 'Dev',
          onboardingCompleted: true,
        },
        currentTeam: { id: 't1', name: 'Team', role },
        memberships: [{ teamId: 't1', teamName: 'Team', role }],
        authMode: 'enabled',
      }),
    }),
  );
}

function renderProtectedAdminRoute(role: string) {
  mockAccount(role);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  return render(
    <QueryClientProvider client={ queryClient }>
      <MemoryRouter initialEntries={ ['/admin/ingestion/jobs'] }>
        <Routes>
          <Route
            path="/admin/ingestion/jobs"
            element={
              <AuthGate requireOnboardingComplete requiredRoles={ ['owner', 'admin'] }>
                <div data-testid="admin-secret">Admin ingestion jobs</div>
              </AuthGate>
            }
          />
          <Route
            path={ MAIN_MONITORING_ROUTE }
            element={ <div data-testid="monitoring-page">Monitoring</div> }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AuthGate role gating', () => {
  it('renders protected children for an owner role', async () => {
    renderProtectedAdminRoute('owner');

    await waitFor(() => expect(screen.getByTestId('admin-secret')).toBeTruthy());
  });

  it('redirects a member away before rendering admin children', async () => {
    renderProtectedAdminRoute('member');

    await waitFor(() => expect(screen.getByTestId('monitoring-page')).toBeTruthy());
    expect(screen.queryByTestId('admin-secret')).toBeNull();
  });
});
