import { useJohnDeereConnection } from '@/lib/queries';

export default function ConnectionsPage() {
  const connectionQ = useJohnDeereConnection();
  const status = connectionQ.data?.status ?? 'not_connected';
  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="connections-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Connections</p>
        <h1 className="mt-1 text-2xl font-semibold">John Deere</h1>
        <p className="mt-1 text-sm text-muted-foreground">Status: { status.replace('_', ' ') }</p>
        <p className="mt-3 text-sm text-muted-foreground">
          OAuth integration is deferred until customer confirmation. No client IDs or secrets are configured in the browser.
        </p>
      </section>
    </main>
  );
}
