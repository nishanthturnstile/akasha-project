import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
    AlertTriangle,
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    Database,
    Download,
    Loader2,
    RefreshCw,
    Satellite,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
    useConfig,
    useIngestionSourceProducts,
    useIngestionSources,
    useTriggerIngestionJob,
} from '@/lib/queries';
import type { IngestionProductItem, IngestionSourceSummary } from '@/types/api';

type BadgeVariant = 'success' | 'warning' | 'destructive' | 'info' | 'neutral';

const JOBS_ROUTE = '/admin/ingestion/jobs';
const DEFAULT_WINDOW_DAYS = 12;
const DEFAULT_MAX_DOWNLOADS = 1;

function fmtDateTime(value: string | null | undefined): string {
    if (!value) return '—';
    const date = value.slice(0, 10);
    const time = value.length >= 16 ? value.slice(11, 16) : '';
    return time ? `${date} ${time}` : date;
}

function fmtDate(value: string | null | undefined): string {
    if (!value) return '—';
    return value.slice(0, 10);
}

function formatNumber(value: number | null | undefined): string {
    if (value == null || !Number.isFinite(value)) return '—';
    return new Intl.NumberFormat().format(value);
}

function formatBytes(value: number | null | undefined): string {
    if (value == null || !Number.isFinite(value)) return '—';
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
    return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function statusText(value: string | null | undefined): string {
    if (!value) return 'Unknown';
    return value.replace(/_/g, ' ');
}

function isAdminManageable(source: IngestionSourceSummary): boolean {
    return Boolean(source.adminManageable ?? source.active);
}

function isSyncEnabled(source: IngestionSourceSummary): boolean {
    return Boolean(source.syncEnabled ?? (source.active && source.aoiId));
}

function exposureBadge(source: IngestionSourceSummary): { label: string; variant: BadgeVariant } | null {
    if (source.productExposure === 'background_only') {
        return { label: 'Backend support', variant: 'info' };
    }
    if (source.productExposure === 'reference_only') {
        return { label: 'Reference only', variant: 'neutral' };
    }
    if (source.productExposure === 'product_active' || source.active) {
        return { label: 'Map layer', variant: 'success' };
    }
    return null;
}

function sourceBadge(source: IngestionSourceSummary): { label: string; variant: BadgeVariant } {
    if (!isAdminManageable(source)) return { label: 'Not sync-enabled', variant: 'neutral' };
    const state = source.lastJob?.state?.toLowerCase();
    if (state === 'succeeded') return { label: 'Success', variant: 'success' };
    if (state === 'failed' || state === 'validation_failed' || state === 'cancelled') {
        return { label: 'Failed', variant: 'destructive' };
    }
    if (source.isOverdue) return { label: 'Overdue', variant: 'destructive' };
    if (state === 'running' || state === 'queued') return { label: 'Running', variant: 'info' };
    if (source.isDue) return { label: 'Due', variant: 'warning' };
    if (!state && source.scheduleState === 'manual_only') return { label: 'Manual sync', variant: 'info' };
    if (!state) return { label: 'Never run', variant: 'warning' };
    return { label: statusText(state), variant: 'neutral' };
}

function ProductRows({ sourceId, enabled }: { sourceId: string; enabled: boolean }) {
    const productsQ = useIngestionSourceProducts(sourceId, { enabled, limit: 10 });

    if (!enabled) return null;
    if (productsQ.isLoading) {
        return <Skeleton className="h-28 w-full" aria-label="Loading downloaded products" />;
    }
    if (
        productsQ.error
        || productsQ.data?.status === 'unavailable'
        || productsQ.data?.status === 'missing'
        || productsQ.data?.status === 'unconfigured'
    ) {
        return (
            <p className="rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning" role="status">
                Product download ledger is not available right now. The latest run summary is still shown above.
            </p>
        );
    }

    const products = productsQ.data?.products ?? [];
    if (products.length === 0) {
        return (
            <p className="rounded-md border border-border/70 bg-muted/30 p-3 text-sm text-muted-foreground">
                No per-scene download records yet for this satellite.
            </p>
        );
    }

    return (
        <div className="overflow-x-auto rounded-lg border border-border/70">
            <table className="min-w-full divide-y divide-border text-sm">
                <thead className="bg-muted/40 text-xs uppercase tracking-[0.14em] text-muted-foreground">
                    <tr>
                        <th scope="col" className="px-3 py-2 text-left font-medium">Product</th>
                        <th scope="col" className="px-3 py-2 text-left font-medium">Acquisition</th>
                        <th scope="col" className="px-3 py-2 text-left font-medium">Status</th>
                        <th scope="col" className="px-3 py-2 text-right font-medium">Size</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-border/70 bg-card/60">
                    { products.map((product: IngestionProductItem) => (
                        <tr key={ `${product.productId}:${product.updatedAt ?? ''}` }>
                            <td className="max-w-90 px-3 py-2 font-mono text-xs text-foreground">
                                { product.productId }
                                { product.error && (
                                    <p className="mt-1 font-sans text-xs text-destructive">{ product.error }</p>
                                ) }
                            </td>
                            <td className="px-3 py-2 text-muted-foreground">{ fmtDate(product.acquisitionDate) }</td>
                            <td className="px-3 py-2">
                                <Badge variant={ product.status === 'downloaded' ? 'success' : product.status === 'failed' ? 'destructive' : 'neutral' }>
                                    { statusText(product.status) }
                                </Badge>
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                                { formatBytes(product.bytes) }
                            </td>
                        </tr>
                    )) }
                </tbody>
            </table>
        </div>
    );
}

function StatCard({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-lg border border-border/70 bg-background/60 p-3">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{ label }</p>
            <p className="mt-1 text-lg font-semibold">{ value }</p>
        </div>
    );
}

function SatelliteCard({
    source,
    isOpen,
    isConfirming,
    liveTriggerEnabled,
    onToggle,
    onAskSync,
    onCancelSync,
}: {
    source: IngestionSourceSummary;
    isOpen: boolean;
    isConfirming: boolean;
    liveTriggerEnabled: boolean;
    onToggle: () => void;
    onAskSync: () => void;
    onCancelSync: () => void;
}) {
    const trigger = useTriggerIngestionJob();
    const badge = sourceBadge(source);
    const exposure = exposureBadge(source);
    const lastJob = source.lastJob;
    const syncLabel = liveTriggerEnabled ? `Sync now ${source.label}` : `Run test sync ${source.label}`;
    const canSync = isSyncEnabled(source) && Boolean(source.aoiId);

    async function confirmSync() {
        if (!source.aoiId) return;
        try {
            await trigger.mutateAsync({
                sourceId: source.sourceId,
                aoiId: source.aoiId,
                dryRun: !liveTriggerEnabled,
                confirmLive: liveTriggerEnabled,
                windowDays: DEFAULT_WINDOW_DAYS,
                maxDownloads: DEFAULT_MAX_DOWNLOADS,
                notes: `Manual ${liveTriggerEnabled ? 'sync' : 'test sync'} from satellite ingestion admin`,
            });
            onCancelSync();
        } catch {
            // React Query stores the error in mutation state; keep the inline confirm open
            // and render the calm operator-facing alert below.
        }
    }

    return (
        <Card className="overflow-hidden border-border/80 bg-card/90 shadow-sm">
            <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(240px,0.8fr)_auto] lg:items-center">
                <button
                    type="button"
                    onClick={ onToggle }
                    aria-expanded={ isOpen }
                    aria-label={ `${isOpen ? 'Collapse' : 'Expand'} ${source.label}` }
                    className="group flex min-w-0 items-start gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                    <span className="mt-0.5 rounded-lg border border-border/80 bg-background/70 p-2 text-info">
                        <Satellite className="h-5 w-5" aria-hidden="true" />
                    </span>
                    <span className="min-w-0">
                        <span className="flex flex-wrap items-center gap-2">
                            <span className="text-lg font-semibold tracking-[-0.01em]">{ source.label }</span>
                            <Badge variant={ badge.variant }>{ badge.label }</Badge>
                            { exposure && <Badge variant={ exposure.variant }>{ exposure.label }</Badge> }
                        </span>
                        <span className="mt-1 block text-sm text-muted-foreground">
                            { source.provider ?? 'Unknown provider' } · { source.kind ?? 'source' } · { statusText(source.scheduleState) } · { source.aoiId ?? 'No AOI configured' }
                        </span>
                    </span>
                    { isOpen ? (
                        <ChevronDown className="mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-y-0.5" aria-hidden="true" />
                    ) : (
                        <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                    ) }
                </button>

                <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                        <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Last run</p>
                        <p className="mt-1 font-medium">{ fmtDateTime(source.lastRunAt) }</p>
                    </div>
                    <div>
                        <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Next run</p>
                        <p className="mt-1 font-medium">{ fmtDateTime(source.nextDueAt) }</p>
                    </div>
                </div>

                <Button
                    type="button"
                    variant={ liveTriggerEnabled ? 'primary' : 'outline' }
                    size="sm"
                    disabled={ !canSync }
                    onClick={ onAskSync }
                    aria-label={ syncLabel }
                >
                    { liveTriggerEnabled ? <Download className="h-3.5 w-3.5" aria-hidden="true" /> : <Database className="h-3.5 w-3.5" aria-hidden="true" /> }
                    { liveTriggerEnabled ? 'Sync now' : 'Run test sync' }
                </Button>
            </div>

            { isConfirming && (
                <div className="mx-4 mb-4 rounded-lg border border-info/30 bg-info/10 p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                            <p className="font-medium text-foreground">Sync { source.label } now?</p>
                            <p className="mt-1 text-muted-foreground">
                                { liveTriggerEnabled
                                    ? `This checks Bhoonidhi and downloads up to ${DEFAULT_MAX_DOWNLOADS} new product for backend ingestion.`
                                    : 'Live downloads are disabled for this environment, so this will run a safe test sync.' }
                            </p>
                        </div>
                        <div className="flex items-center gap-2">
                            <Button type="button" variant="ghost" size="sm" onClick={ onCancelSync }>Cancel</Button>
                            <Button type="button" size="sm" onClick={ () => { void confirmSync(); } } disabled={ trigger.isPending }>
                                { trigger.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> }
                                Confirm sync
                            </Button>
                        </div>
                    </div>
                </div>
            ) }

            { trigger.data && (
                <div className="mx-4 mb-4 rounded-lg border border-success/30 bg-success/10 p-3 text-sm text-success" role="status">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <span>{ trigger.data.message }</span>
                        <Link className="font-medium underline-offset-4 hover:underline" to={ trigger.data.jobsUrl }>
                            View run history
                        </Link>
                    </div>
                </div>
            ) }

            { trigger.error && (
                <div className="mx-4 mb-4 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
                    Sync request could not be submitted.
                </div>
            ) }

            { isOpen && (
                <CardContent className="space-y-4 border-t border-border/70 bg-background/35 p-4">
                    <div className="grid gap-3 md:grid-cols-4">
                        <StatCard label="Last status" value={ statusText(lastJob?.state) } />
                        <StatCard label="Found" value={ `Found ${formatNumber(lastJob?.foundCount)}` } />
                        <StatCard label="Downloaded" value={ `Downloaded ${formatNumber(lastJob?.downloadedCount)}` } />
                        <StatCard label="Latest composite" value={ fmtDate(source.latestCompositeDate) } />
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/70 bg-card/70 p-3 text-sm text-muted-foreground">
                        <span>
                            Window { fmtDate(lastJob?.windowStart) } → { fmtDate(lastJob?.windowEnd) }
                        </span>
                        { lastJob?.jobId && (
                            <Link className="font-medium text-info underline-offset-4 hover:underline" to={ `${JOBS_ROUTE}/${encodeURIComponent(lastJob.jobId)}` }>
                                View full run details
                            </Link>
                        ) }
                    </div>
                    { lastJob?.message && (
                        <p className="rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
                            { lastJob.message }
                        </p>
                    ) }
                    <div className="space-y-2">
                        <div className="flex items-center gap-2">
                            <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />
                            <h2 className="text-sm font-semibold">Downloaded satellite data</h2>
                        </div>
                        <ProductRows sourceId={ source.sourceId } enabled={ isOpen && isAdminManageable(source) } />
                    </div>
                </CardContent>
            ) }
        </Card>
    );
}

function RegisteredSources({ sources }: { sources: IngestionSourceSummary[] }) {
    if (sources.length === 0) return null;
    return (
        <section className="mt-4 rounded-xl border border-border/70 bg-muted/20 p-4" aria-label="Registered satellites not sync-enabled">
            <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                <h2 className="text-sm font-semibold">Registered but not sync-enabled</h2>
            </div>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
                { sources.map((source) => (
                    <article key={ source.sourceId } className="rounded-lg border border-border/60 bg-card/55 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                            <p className="font-medium">{ source.label }</p>
                            <Badge variant="neutral">Not sync-enabled</Badge>
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground">
                            { source.gatedReason ?? 'This source is registered but not validated or configured for operator sync yet.' }
                        </p>
                    </article>
                )) }
            </div>
        </section>
    );
}

export default function AdminIngestionSources() {
    const sourcesQ = useIngestionSources();
    const configQ = useConfig();
    const [openSources, setOpenSources] = useState<Set<string>>(() => new Set());
    const [confirmingSourceId, setConfirmingSourceId] = useState<string | null>(null);

    const liveTriggerEnabled = Boolean(
        configQ.data?.adminIngestionLiveTriggerEnabled ?? sourcesQ.data?.liveTriggerEnabled,
    );
    const sources = sourcesQ.data?.sources ?? [];
    const managedSources = sources.filter(isAdminManageable);
    const registeredSources = sources.filter((source) => !isAdminManageable(source));

    function toggleSource(sourceId: string) {
        setOpenSources((current) => {
            const next = new Set(current);
            if (next.has(sourceId)) next.delete(sourceId);
            else next.add(sourceId);
            return next;
        });
    }

    return (
        <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="admin-ingestion-sources-page">
            <section className="relative overflow-hidden rounded-xl border border-border/80 bg-card/90 p-4">
                <div className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-linear-to-r from-success via-info to-warning opacity-80" />
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">
                            Admin · Satellite operations
                        </p>
                        <h1 className="mt-1 text-2xl font-semibold">Satellite ingestion</h1>
                        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                            One place to manage satellite ingestion, including backend-only support sources that are not selectable map layers.
                        </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <Button asChild variant="outline" size="sm">
                            <Link to={ JOBS_ROUTE }>All run history</Link>
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={ sourcesQ.isFetching }
                            onClick={ () => { void sourcesQ.refetch(); } }
                            aria-label="Refresh satellite ingestion"
                        >
                            <RefreshCw className={ `h-3.5 w-3.5 ${sourcesQ.isFetching ? 'animate-spin' : ''}` } aria-hidden="true" />
                            Refresh
                        </Button>
                    </div>
                </div>
                { !liveTriggerEnabled && (
                    <p className="mt-3 rounded-md border border-info/30 bg-info/10 p-3 text-sm text-info" role="status">
                        Live downloads are disabled for this environment. Sync buttons run a safe test sync.
                    </p>
                ) }
            </section>

            { sourcesQ.error && (
                <p className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
                    Satellite ingestion status could not be loaded.
                </p>
            ) }
            { sourcesQ.data?.lastError && (
                <p className="mt-4 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm text-warning" role="status">
                    Satellite status loaded with a warning. Operator-only details are in the API logs.
                </p>
            ) }

            { sourcesQ.isLoading && (
                <div className="mt-4 grid gap-3">
                    <Skeleton className="h-28 w-full" />
                    <Skeleton className="h-28 w-full" />
                    <Skeleton className="h-28 w-full" />
                </div>
            ) }

            { !sourcesQ.isLoading && managedSources.length === 0 && (
                <p className="mt-4 rounded-xl border border-border/70 bg-card/70 p-6 text-sm text-muted-foreground">
                    No admin-manageable ingestion satellites are reported yet.
                </p>
            ) }

            <section className="mt-4 space-y-3" aria-label="Admin-managed satellites">
                { managedSources.map((source) => (
                    <SatelliteCard
                        key={ source.sourceId }
                        source={ source }
                        isOpen={ openSources.has(source.sourceId) }
                        isConfirming={ confirmingSourceId === source.sourceId }
                        liveTriggerEnabled={ liveTriggerEnabled }
                        onToggle={ () => toggleSource(source.sourceId) }
                        onAskSync={ () => setConfirmingSourceId(source.sourceId) }
                        onCancelSync={ () => setConfirmingSourceId(null) }
                    />
                )) }
            </section>

            <RegisteredSources sources={ registeredSources } />
        </main>
    );
}
