import { useEffect, useState } from 'react';

// Slice 0 deployable frontend SKELETON.
// This is intentionally a placeholder. The product map UX (MapLibre + Terra
// Draw, layer/index panels) arrives in Slices 4-5. Here we only prove the
// same-origin /api/* contract by reading the BFF skeleton service registry.

type ServiceItem = {
  id: string;
  name: string;
  public: boolean;
  status: string;
  healthPath: string | null;
};

type ServicesResponse = {
  app: string;
  slice: number;
  services: ServiceItem[];
};

type LoadState = 'loading' | 'ok' | 'error';

export default function App() {
  const [state, setState] = useState<LoadState>('loading');
  const [data, setData] = useState<ServicesResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/_skeleton/services')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((json: ServicesResponse) => {
        if (!cancelled) {
          setData(json);
          setState('ok');
        }
      })
      .catch(() => {
        if (!cancelled) setState('error');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="shell">
      <header className="hero">
        <span className="badge">Railway MVP · Slice 0 · Skeleton</span>
        <h1>Akasha</h1>
        <p>
          Deployable frontend skeleton. The interactive map experience
          (MapLibre GL JS + Terra Draw, layer &amp; index panels) is delivered
          in Slices 4&ndash;5.
        </p>
      </header>

      <section className="card">
        <h2>Backend connectivity</h2>
        {state === 'loading' && <p className="muted">Checking the BFF via /api/_skeleton/services…</p>}
        {state === 'error' && (
          <p className="error">
            Could not reach the BFF. Start the `api` service (and the gateway in
            production) so /api/* is proxied same-origin.
          </p>
        )}
        {state === 'ok' && data && (
          <>
            <p className="muted">
              Connected to <strong>{data.app}</strong> (slice {data.slice}). Service registry:
            </p>
            <ul className="svc-list">
              {data.services.map((s) => (
                <li key={s.id}>
                  <span className={`dot ${s.status === 'live' ? 'live' : 'defined'}`} />
                  <span className="svc-name">{s.name}</span>
                  <span className="svc-meta">
                    {s.public ? 'public' : 'private'}
                    {s.healthPath ? ` · ${s.healthPath}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <footer className="foot">Akasha · Slice 0 · not for production data without an access gate</footer>
    </main>
  );
}
