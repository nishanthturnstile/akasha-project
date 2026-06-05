import { useState } from 'react';
import { useApiKeys, useCreateApiKey, useRevokeApiKey } from '@/lib/queries';

export default function ApiSettingsPage() {
  const [name, setName] = useState('Pilot integration');
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const keysQ = useApiKeys();
  const createMutation = useCreateApiKey();
  const revokeMutation = useRevokeApiKey();

  async function createKey() {
    const key = await createMutation.mutateAsync(name);
    setCreatedKey(key.rawKey ?? null);
  }

  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="api-settings-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Account</p>
        <h1 className="mt-1 text-2xl font-semibold">API settings</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Akasha API keys show only metadata after creation. Provider keys are never displayed here.
        </p>
      </section>
      { createdKey && (
        <section className="mt-4 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4">
          <h2 className="font-semibold">Copy this key now</h2>
          <code className="mt-2 block break-all text-sm">{ createdKey }</code>
        </section>
      ) }
      <section className="mt-4 flex gap-3 rounded-xl border border-border/80 bg-card/90 p-4">
        <input className="rounded-md border border-border bg-background px-3 py-2" value={ name } onChange={ (event) => setName(event.target.value) } />
        <button className="rounded-md bg-primary px-4 py-2 text-primary-foreground" onClick={ () => void createKey() } type="button">Create key</button>
      </section>
      <section className="mt-4 grid gap-2 rounded-xl border border-border/80 bg-card/90 p-4">
        { keysQ.data?.map((key) => (
          <article key={ key.id } className="rounded-md border border-border p-3">
            <p className="font-medium">{ key.name }</p>
            <p className="text-sm text-muted-foreground">{ key.prefix }...{ key.last4 }</p>
            <button className="mt-2 rounded-md border border-border px-3 py-1.5 text-sm" onClick={ () => void revokeMutation.mutateAsync(key.id) } type="button">Revoke</button>
          </article>
        )) }
        { !keysQ.data?.length && <p className="text-sm text-muted-foreground">No API keys yet.</p> }
      </section>
    </main>
  );
}
