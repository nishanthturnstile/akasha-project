import { useAccountMe } from '@/lib/queries';

export default function AccountSettingsPage() {
  const accountQ = useAccountMe();
  const account = accountQ.data;
  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="account-settings-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Account</p>
        <h1 className="mt-1 text-2xl font-semibold">Account settings</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          { account ? `${account.user.email} · ${account.currentTeam.name}` : 'Loading account...' }
        </p>
        { account?.authMode === 'dev' && (
          <p className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100">
            Local development auth is active. Enable AUTH_MODE before customer data is used.
          </p>
        ) }
      </section>
      <section className="mt-4 rounded-xl border border-border/80 bg-card/90 p-4">
        <h2 className="text-lg font-semibold">Team memberships</h2>
        { account?.memberships.map((membership) => (
          <p key={ membership.teamId } className="mt-2 text-sm text-muted-foreground">
            { membership.teamName } — { membership.role }
          </p>
        )) }
      </section>
    </main>
  );
}
