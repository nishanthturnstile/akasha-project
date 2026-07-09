import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AdminIngestionSources from '@/pages/monitoring/AdminIngestionSources';
import type {
    IngestionSourceProductsResponse,
    IngestionSourcesResponse,
    TriggerIngestionJobResponse,
} from '@/types/api';

function jsonResponse(payload: unknown, status = 200) {
    return {
        ok: status >= 200 && status < 300,
        status,
        headers: new Headers(),
        json: async () => payload,
    };
}

const sourcesPayload: IngestionSourcesResponse = {
    status: 'ok',
    generatedAt: '2026-06-25T12:00:00Z',
    liveTriggerEnabled: true,
    sources: [
        {
            sourceId: 'resourcesat-2a-liss3-boa',
            label: 'ResourceSat-2A LISS-3 BOA',
            provider: 'ISRO/NRSC Bhoonidhi',
            kind: 'optical',
            availabilityStatus: 'active',
            active: true,
            adminManageable: true,
            syncEnabled: true,
            gatedReason: null,
            aoiId: 'bangalore-60km',
            scheduleState: 'routine',
            scheduleEnabled: true,
            productExposure: 'product_active',
            validationState: 'validation_passed',
            capabilities: ['search_enabled', 'download_enabled'],
            cadenceDays: 7,
            lastRunAt: '2026-06-20T01:00:00Z',
            lastSuccessAt: '2026-06-20T01:30:00Z',
            lastFailureAt: '2026-06-18T01:30:00Z',
            nextDueAt: '2026-06-27T01:00:00Z',
            isDue: false,
            isOverdue: false,
            latestCompositeDate: '2026-06-18',
            lastJob: {
                jobId: 'job_20260620T010000Z_liss3',
                state: 'succeeded',
                foundCount: 8,
                selectedCount: 4,
                downloadedCount: 3,
                rejectedCount: 4,
                windowStart: '2026-06-01T00:00:00Z',
                windowEnd: '2026-06-20T00:00:00Z',
                failureKind: null,
                message: null,
            },
        },
        {
            sourceId: 'resourcesat-2a-liss4-mx70-l2',
            label: 'ResourceSat-2A LISS-4 MX70 L2',
            provider: 'ISRO/NRSC Bhoonidhi',
            kind: 'optical',
            availabilityStatus: 'active',
            active: true,
            adminManageable: true,
            syncEnabled: true,
            gatedReason: null,
            aoiId: 'bangalore-60km',
            scheduleState: 'routine',
            scheduleEnabled: true,
            productExposure: 'product_active',
            validationState: 'validation_passed',
            capabilities: ['search_enabled', 'download_enabled'],
            cadenceDays: 7,
            lastRunAt: '2026-06-19T01:00:00Z',
            lastSuccessAt: null,
            lastFailureAt: '2026-06-19T01:30:00Z',
            nextDueAt: '2026-06-26T01:00:00Z',
            isDue: true,
            isOverdue: true,
            latestCompositeDate: null,
            lastJob: {
                jobId: 'job_20260619T010000Z_liss4',
                state: 'failed',
                foundCount: 3,
                selectedCount: 1,
                downloadedCount: 0,
                rejectedCount: 2,
                windowStart: '2026-06-01T00:00:00Z',
                windowEnd: '2026-06-19T00:00:00Z',
                failureKind: 'provider_no_candidates',
                message: 'Provider returned no candidates.',
            },
        },
        {
            sourceId: 'eos-04-sar-mrs-l2b',
            label: 'EOS-04 SAR MRS L2B',
            provider: 'ISRO/NRSC Bhoonidhi',
            kind: 'sar',
            availabilityStatus: 'gated',
            active: false,
            adminManageable: true,
            syncEnabled: true,
            gatedReason: 'EOS-04 is validated for backend SAR-assisted cloudy optical analytics; it is not a directly selectable optical index layer.',
            aoiId: 'bangalore-60km',
            scheduleState: 'manual_only',
            scheduleEnabled: false,
            productExposure: 'background_only',
            validationState: 'validation_passed',
            capabilities: ['search_enabled', 'download_enabled', 'prepare_enabled', 'validate_enabled'],
            cadenceDays: 10,
            lastRunAt: '2026-06-30T05:39:28Z',
            lastSuccessAt: '2026-06-30T05:45:00Z',
            lastFailureAt: null,
            nextDueAt: null,
            isDue: false,
            isOverdue: false,
            latestCompositeDate: null,
            lastJob: {
                jobId: 'job_20260630T053928Z_eos04',
                state: 'succeeded',
                runAt: '2026-06-30T05:45:00Z',
                foundCount: 10,
                selectedCount: 1,
                downloadedCount: 1,
                rejectedCount: null,
                windowStart: '2026-05-17T00:00:00Z',
                windowEnd: '2026-06-30T00:00:00Z',
                failureKind: null,
                message: null,
            },
        },
        {
            sourceId: 'eos-06-ocm-lac-ndvi-8day-360m',
            label: 'EOS-06 OCM-LAC NDVI 8-day 360m',
            provider: 'ISRO/NRSC Bhoonidhi',
            kind: 'context',
            availabilityStatus: 'gated',
            active: false,
            adminManageable: false,
            syncEnabled: false,
            gatedReason: 'No validated EOS-06 NDVI context COG has been ingested.',
            aoiId: null,
            scheduleState: 'disabled',
            scheduleEnabled: false,
            productExposure: 'hidden',
            validationState: 'unvalidated',
            capabilities: [],
            cadenceDays: null,
            lastRunAt: null,
            lastSuccessAt: null,
            lastFailureAt: null,
            nextDueAt: null,
            isDue: false,
            isOverdue: false,
            latestCompositeDate: null,
            lastJob: null,
        },
    ],
};

const productsPayload: IngestionSourceProductsResponse = {
    status: 'ok',
    generatedAt: '2026-06-25T12:00:00Z',
    sourceId: 'resourcesat-2a-liss3-boa',
    products: [
        {
            productId: 'RA319MAR2026048153009900065PSANSTUCSRHTDF',
            sceneKey: 'resourcesat-2a-liss3-boa:BOA:99:65:2026-03-19T00:00:00Z',
            acquisitionDate: '2026-03-19',
            status: 'downloaded',
            bytes: 1048576,
            updatedAt: '2026-06-20T01:30:00Z',
            error: null,
        },
    ],
};

const eos04ProductsPayload: IngestionSourceProductsResponse = {
    status: 'ok',
    generatedAt: '2026-06-30T06:00:00Z',
    sourceId: 'eos-04-sar-mrs-l2b',
    products: [
        {
            productId: 'EOS04_SAR_MRS_L2B_20260622',
            sceneKey: 'eos-04-sar-mrs-l2b:eos-04:MRS:2026-06-22T00:35:37Z',
            acquisitionDate: '2026-06-22',
            status: 'downloaded',
            bytes: 1366884,
            updatedAt: '2026-06-30T05:45:00Z',
            error: null,
        },
    ],
};

function appConfigPayload(liveTriggerEnabled = true) {
    return {
        appName: 'Akasha',
        aoi: {
            id: 'bangalore-60km',
            name: 'Bangalore 60 km',
            center: [77.5946, 12.9716],
            zoom: 9,
            bounds: [77, 12, 78, 13],
        },
        aois: [],
        basemapStyleUrl: '',
        basemap: {
            provider: 'empty',
            style: '',
            styleFamily: 'empty',
            usageModel: 'session',
            places: 'none',
            sessionDurationSeconds: 0,
        },
        maxPolygonAreaHa: 1000,
        maxPolygonVertices: 500,
        usablePixelThresholdPercent: 75,
        supportedIndices: ['NDVI'],
        defaultIndex: 'NDVI',
        adminIngestionLiveTriggerEnabled: liveTriggerEnabled,
    };
}

function renderPage({
    sources = sourcesPayload,
    products = productsPayload,
    liveTriggerEnabled = true,
    triggerResponse = {
        status: 'submitted',
        jobRequestId: 'ingest-ui-20260626-abcdef12',
        dryRun: false,
        jobsUrl: '/admin/ingestion/jobs?sourceId=resourcesat-2a-liss3-boa',
        message: 'Submitted',
    } satisfies TriggerIngestionJobResponse,
    triggerStatus = 200,
}: {
    sources?: IngestionSourcesResponse;
    products?: IngestionSourceProductsResponse;
    liveTriggerEnabled?: boolean;
    triggerResponse?: unknown;
    triggerStatus?: number;
} = {}) {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === '/api/config') {
            return Promise.resolve(jsonResponse(appConfigPayload(liveTriggerEnabled)));
        }
        if (path === '/api/monitoring/ingestion-sources') {
            return Promise.resolve(jsonResponse({ ...sources, liveTriggerEnabled }));
        }
        if (path.includes('/api/monitoring/ingestion-sources/resourcesat-2a-liss3-boa/products')) {
            return Promise.resolve(jsonResponse(products));
        }
        if (path.includes('/api/monitoring/ingestion-sources/eos-04-sar-mrs-l2b/products')) {
            return Promise.resolve(jsonResponse(eos04ProductsPayload));
        }
        if (path.includes('/api/monitoring/ingestion-jobs/trigger') && init?.method === 'POST') {
            return Promise.resolve(jsonResponse(triggerResponse, triggerStatus));
        }
        return Promise.resolve(jsonResponse({ status: 'ok' }));
    });
    vi.stubGlobal('fetch', fetchMock);
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    });
    render(
        <QueryClientProvider client={ queryClient }>
            <MemoryRouter>
                <AdminIngestionSources />
            </MemoryRouter>
        </QueryClientProvider>,
    );
    return fetchMock;
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('AdminIngestionSources', () => {
    it('renders expandable satellite cards with last run, next run, counts, and product rows', async () => {
        renderPage();

        await waitFor(() =>
            expect(screen.getByRole('heading', { name: 'Satellite ingestion' })).toBeTruthy(),
        );
        expect(await screen.findByText('ResourceSat-2A LISS-3 BOA')).toBeTruthy();
        expect(screen.getByText('ResourceSat-2A LISS-4 MX70 L2')).toBeTruthy();
        const liss4Button = screen.getByRole('button', {
            name: /Expand ResourceSat-2A LISS-4 MX70 L2/,
        });
        const liss4Card = liss4Button.closest('div')?.parentElement;
        expect(liss4Card).toBeTruthy();
        expect(within(liss4Card as HTMLElement).getByText('Failed')).toBeTruthy();
        expect(screen.getAllByText('Last run').length).toBeGreaterThan(0);
        expect(screen.getByText('2026-06-20 01:00')).toBeTruthy();
        expect(screen.getByText('2026-06-27 01:00')).toBeTruthy();

        fireEvent.click(screen.getByRole('button', { name: /Expand ResourceSat-2A LISS-3 BOA/ }));

        expect(screen.getByText('Found 8')).toBeTruthy();
        expect(screen.getByText('Downloaded 3')).toBeTruthy();
        expect(screen.getByText('Window 2026-06-01 → 2026-06-20')).toBeTruthy();
        expect(await screen.findByText('RA319MAR2026048153009900065PSANSTUCSRHTDF')).toBeTruthy();
        expect(screen.getByText('2026-03-19')).toBeTruthy();
        expect(screen.getByText('1.0 MB')).toBeTruthy();

        const detailLink = screen.getByRole('link', { name: /View full run details/ });
        expect((detailLink as HTMLAnchorElement).href).toContain(
            '/admin/ingestion/jobs/job_20260620T010000Z_liss3',
        );
    });

    it('submits a live Sync now request after a simple inline confirmation', async () => {
        const fetchMock = renderPage();

        await screen.findByText('ResourceSat-2A LISS-3 BOA');
        fireEvent.click(screen.getByRole('button', { name: /Sync now ResourceSat-2A LISS-3 BOA/ }));
        expect(screen.getByText('Sync ResourceSat-2A LISS-3 BOA now?')).toBeTruthy();
        fireEvent.click(screen.getByRole('button', { name: 'Confirm sync' }));

        await waitFor(() => expect(screen.getByText('Submitted')).toBeTruthy());
        const triggerCall = fetchMock.mock.calls.find((call) =>
            String(call[0]).includes('/api/monitoring/ingestion-jobs/trigger'),
        );
        expect(triggerCall).toBeTruthy();
        expect(JSON.parse(String(triggerCall?.[1]?.body))).toMatchObject({
            sourceId: 'resourcesat-2a-liss3-boa',
            aoiId: 'bangalore-60km',
            dryRun: false,
            confirmLive: true,
            windowDays: 12,
            maxDownloads: 1,
        });
    });

    it('uses plain test-sync wording when live triggers are disabled', async () => {
        renderPage({ liveTriggerEnabled: false });

        await screen.findByText('ResourceSat-2A LISS-3 BOA');

        expect(screen.getByRole('button', { name: /Run test sync ResourceSat-2A LISS-3 BOA/ }))
            .toBeTruthy();
        expect(screen.getByText(/Live downloads are disabled for this environment/i)).toBeTruthy();
    });

    it('shows a clear product-ledger missing message instead of pretending there are no records', async () => {
        renderPage({
            products: {
                status: 'missing',
                generatedAt: '2026-06-25T12:00:00Z',
                sourceId: 'resourcesat-2a-liss3-boa',
                products: [],
            },
        });

        await screen.findByText('ResourceSat-2A LISS-3 BOA');
        fireEvent.click(screen.getByRole('button', { name: /Expand ResourceSat-2A LISS-3 BOA/ }));

        expect(await screen.findByText(/Product download ledger is not available/i)).toBeTruthy();
        expect(screen.queryByText('No per-scene download records yet for this satellite.')).toBeNull();
    });

    it('shows a sync error without throwing when the trigger request is rejected', async () => {
        renderPage({
            triggerResponse: {
                error: {
                    code: 'SOURCE_NOT_SCHEDULABLE',
                    message: 'This source and AOI are not enabled for scheduled ingestion.',
                    details: {},
                },
            } as unknown as TriggerIngestionJobResponse,
            triggerStatus: 400,
        });

        await screen.findByText('ResourceSat-2A LISS-3 BOA');
        fireEvent.click(screen.getByRole('button', { name: /Sync now ResourceSat-2A LISS-3 BOA/ }));
        fireEvent.click(screen.getByRole('button', { name: 'Confirm sync' }));

        expect((await screen.findByRole('alert')).textContent).toContain(
            'Sync request could not be submitted.',
        );
    });

    it('keeps backend-only EOS-04 in the managed satellite section with sync and history', async () => {
        const fetchMock = renderPage();

        await screen.findByText('EOS-04 SAR MRS L2B');
        const managedSection = screen.getByLabelText('Admin-managed satellites');

        expect(within(managedSection).getByText('EOS-04 SAR MRS L2B')).toBeTruthy();
        expect(within(managedSection).getByText('Backend support')).toBeTruthy();
        expect(screen.getByRole('button', { name: /Sync now EOS-04 SAR MRS L2B/ })).toBeTruthy();

        fireEvent.click(screen.getByRole('button', { name: /Expand EOS-04 SAR MRS L2B/ }));

        expect(await screen.findByText('EOS04_SAR_MRS_L2B_20260622')).toBeTruthy();
        expect(screen.getByText('2026-06-30 05:39')).toBeTruthy();
        expect(screen.getByText(/manual only/)).toBeTruthy();

        fireEvent.click(screen.getByRole('button', { name: /Sync now EOS-04 SAR MRS L2B/ }));
        fireEvent.click(screen.getByRole('button', { name: 'Confirm sync' }));

        await waitFor(() => expect(screen.getByText('Submitted')).toBeTruthy());
        const triggerCall = fetchMock.mock.calls.find((call) =>
            String(call[0]).includes('/api/monitoring/ingestion-jobs/trigger'),
        );
        expect(JSON.parse(String(triggerCall?.[1]?.body))).toMatchObject({
            sourceId: 'eos-04-sar-mrs-l2b',
            aoiId: 'bangalore-60km',
            dryRun: false,
            confirmLive: true,
        });
    });

    it('shows unvalidated satellites in a registered not-sync-enabled section', async () => {
        renderPage();

        await screen.findByText('EOS-06 OCM-LAC NDVI 8-day 360m');
        const registeredSection = screen.getByLabelText('Registered satellites not sync-enabled');

        expect(within(registeredSection).getByText('EOS-06 OCM-LAC NDVI 8-day 360m')).toBeTruthy();
        expect(within(registeredSection).getByText('Not sync-enabled')).toBeTruthy();
        expect(
            within(registeredSection).getByText('No validated EOS-06 NDVI context COG has been ingested.'),
        ).toBeTruthy();
    });
});
