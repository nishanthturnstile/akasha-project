import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import "@/App.css";
import {
  Satellite,
  Globe,
  Server,
  Map as MapIcon,
  Boxes,
  Database,
  HardDrive,
  SquareTerminal,
  Activity,
  ShieldCheck,
  GitBranch,
  Layers,
  Package,
  ArrowRight,
  CheckCircle2,
  MinusCircle,
  AlertTriangle,
  FolderTree,
  Network,
  ChevronDown,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const SERVICE_ICON = {
  web: Globe,
  api: Server,
  titiler: MapIcon,
  "stac-api": Boxes,
  postgis: Database,
  minio: HardDrive,
  "ingestion-worker": SquareTerminal,
};

function useSkeletonData() {
  const [state, setState] = useState({ status: "loading", services: null, manifest: null, env: null });

  const load = () => {
    setState((s) => ({ ...s, status: "loading" }));
    Promise.all([
      axios.get(`${API}/_skeleton/services`),
      axios.get(`${API}/_skeleton/manifest`),
      axios.get(`${API}/_skeleton/env-matrix`),
    ])
      .then(([svc, man, env]) => {
        setState({ status: "ok", services: svc.data, manifest: man.data, env: env.data });
      })
      .catch(() => setState((s) => ({ ...s, status: "error" })));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ...state, reload: load };
}

function useHealthChecks() {
  const [checks, setChecks] = useState([
    { key: "api-health", label: "API liveness", path: "/api/health", res: "pending" },
    { key: "services", label: "Service registry", path: "/api/_skeleton/services", res: "pending" },
    { key: "manifest", label: "Slice manifest", path: "/api/_skeleton/manifest", res: "pending" },
  ]);

  useEffect(() => {
    let active = true;
    const run = async () => {
      const next = await Promise.all(
        checks.map(async (c) => {
          try {
            const r = await axios.get(`${BACKEND_URL}${c.path}`, { timeout: 8000 });
            return { ...c, res: r.status === 200 ? "ok" : "fail" };
          } catch {
            return { ...c, res: "fail" };
          }
        }),
      );
      if (active) setChecks(next);
    };
    run();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return checks;
}

const SectionHead = ({ icon: Icon, title, kicker }) => (
  <div className="ak-section-head">
    <span className="ak-ico">
      <Icon size={18} />
    </span>
    <h2>{title}</h2>
    {kicker ? <span className="ak-kicker">{kicker}</span> : null}
  </div>
);

function ServiceCard({ svc }) {
  const Icon = SERVICE_ICON[svc.id] || Package;
  const live = svc.status === "live";
  return (
    <div className={`ak-card ${svc.public ? "public" : ""}`} data-testid={`service-card-${svc.id}`}>
      <div className="ak-card-top">
        <span className="ak-svc-ico">
          <Icon size={20} />
        </span>
        <div style={{ minWidth: 0 }}>
          <div className="ak-svc-name">{svc.name}</div>
          <div className="ak-svc-id">{svc.id}</div>
        </div>
        <span className="ak-status">
          <span className={`ak-dot ${live ? "live" : "defined"}`} />
          {live ? "Live" : "Defined"}
        </span>
      </div>

      <p className="ak-role">{svc.role}</p>

      <div className="ak-meta">
        <div>
          <div className="k">Runtime</div>
          <div className="v">{svc.runtime}</div>
        </div>
        <div>
          <div className="k">Internal port</div>
          <div className="v">{svc.internalPort ?? "—"}</div>
        </div>
        <div>
          <div className="k">Health</div>
          <div className="v">{svc.healthPath || svc.healthType}</div>
        </div>
        <div>
          <div className="k">Image</div>
          <div className="v">{svc.image}</div>
        </div>
      </div>

      <div className="ak-tags">
        <span className={`ak-tag ${svc.public ? "pub" : "priv"}`}>
          {svc.public ? "public origin" : "private"}
        </span>
        {svc.persistentVolume ? <span className="ak-tag vol">persistent volume</span> : null}
        {svc.dependsOn && svc.dependsOn.length ? (
          <span className="ak-tag">depends: {svc.dependsOn.join(", ")}</span>
        ) : null}
      </div>
    </div>
  );
}

function ArchitectureDiagram() {
  return (
    <div className="ak-panelbox ak-diagram" data-testid="architecture-diagram">
      <div className="ak-flow">
        <span className="ak-flow-label">Public</span>
        <span className="ak-node pub">
          <Globe size={15} /> browser
        </span>
        <span className="ak-arrow">
          <ArrowRight size={14} />
        </span>
        <span className="ak-node pub">
          <Network size={15} /> web · gateway
        </span>
      </div>
      <div className="ak-flow">
        <span className="ak-flow-label">/api/*</span>
        <span className="ak-node pub">web</span>
        <span className="ak-arrow">
          <ArrowRight size={14} /> proxy
        </span>
        <span className="ak-node priv">
          <Server size={15} /> api (BFF)
        </span>
        <span className="ak-arrow">
          <ArrowRight size={14} />
        </span>
        <span className="ak-node priv">
          <Boxes size={15} /> stac-api
        </span>
        <span className="ak-arrow">
          <ArrowRight size={14} />
        </span>
        <span className="ak-node priv">
          <Database size={15} /> postgis
        </span>
      </div>
      <div className="ak-flow">
        <span className="ak-flow-label">/tiles/*</span>
        <span className="ak-node pub">web</span>
        <span className="ak-arrow">
          <ArrowRight size={14} /> proxy
        </span>
        <span className="ak-node priv">
          <MapIcon size={15} /> titiler
        </span>
        <span className="ak-arrow">
          <ArrowRight size={14} />
        </span>
        <span className="ak-node priv">
          <HardDrive size={15} /> minio (COGs)
        </span>
      </div>
      <div style={{ color: "var(--ak-muted)", fontSize: 13, lineHeight: 1.55 }}>
        Only the <strong style={{ color: "var(--ak-teal)" }}>web</strong> gateway is publicly
        reachable. The browser calls <code>/api/*</code> and <code>/tiles/*</code> on that same
        origin; the gateway proxies to internal services. <code>api</code>, <code>titiler</code>,{" "}
        <code>stac-api</code>, <code>postgis</code>, and <code>minio</code> never get a public domain.
      </div>
    </div>
  );
}

function EnvAccordion({ env }) {
  const services = env?.services || {};
  const keys = Object.keys(services);
  const [open, setOpen] = useState(keys[0] || null);

  return (
    <div data-testid="env-matrix">
      <p style={{ color: "var(--ak-muted)", fontSize: 13, marginTop: 0 }}>{env?.note}</p>
      {keys.map((svc) => {
        const vars = services[svc] || {};
        const entries = Object.entries(vars);
        const isOpen = open === svc;
        return (
          <div className="ak-acc" key={svc}>
            <button
              className="ak-acc-head"
              onClick={() => setOpen(isOpen ? null : svc)}
              data-testid={`env-toggle-${svc}`}
            >
              <ChevronDown
                size={16}
                style={{ transform: isOpen ? "rotate(0)" : "rotate(-90deg)", transition: "transform .15s" }}
              />
              {svc}
              <span className="ak-acc-count">{entries.length} vars</span>
            </button>
            {isOpen ? (
              <div className="ak-acc-body">
                {entries.map(([name, val]) => (
                  <div className="ak-env-row" key={name}>
                    <span className="name">{name}</span>
                    <span className="val">{val === "" ? "(empty)" : val}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function LoadingView() {
  return (
    <div className="ak-center" data-testid="dashboard-loading">
      <div>
        <div className="ak-spinner" />
        <p style={{ color: "var(--ak-muted)" }}>Loading Akasha service skeleton…</p>
      </div>
    </div>
  );
}

function ErrorView({ onRetry }) {
  return (
    <div className="ak-center" data-testid="dashboard-error">
      <div>
        <AlertTriangle size={40} color="var(--ak-red)" style={{ marginBottom: 12 }} />
        <h2 style={{ margin: "0 0 8px" }}>Cannot reach the BFF</h2>
        <p style={{ color: "var(--ak-muted)", maxWidth: 460 }}>
          The api skeleton service did not respond. It exposes{" "}
          <code>/api/_skeleton/services</code>. Check that the backend is running.
        </p>
        <button
          className="ak-pill"
          style={{ marginTop: 16, cursor: "pointer" }}
          onClick={onRetry}
          data-testid="retry-btn"
        >
          <Activity size={15} /> Retry
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const { status, services, manifest, env, reload } = useSkeletonData();
  const health = useHealthChecks();

  const apiOnline = useMemo(
    () => health.find((h) => h.key === "api-health")?.res === "ok",
    [health],
  );

  if (status === "loading") {
    return (
      <div className="ak-root">
        <LoadingView />
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="ak-root">
        <ErrorView onRetry={reload} />
      </div>
    );
  }

  const svcList = services?.services || [];
  const pinned = manifest?.pinnedImages || {};
  const repoTree = manifest?.repoTree || null;
  const roadmap = manifest?.roadmap || [];
  const inScope = manifest?.inScope || [];
  const outScope = manifest?.outOfScope || [];

  return (
    <div className="ak-root" data-testid="dashboard-root">
      <div className="ak-wrap">
        {/* Header */}
        <header className="ak-header">
          <div className="ak-brand">
            <span className="ak-logo">
              <Satellite size={24} />
            </span>
            <div className="ak-title">
              <h1>Akasha</h1>
              <p>Railway MVP · Slice 0 — Service Skeleton</p>
            </div>
          </div>
          <span className="ak-pill" data-testid="api-status-pill">
            <span className={`ak-dot ${apiOnline ? "live" : "red"}`} />
            {apiOnline ? "API online" : "API unreachable"}
            <span style={{ color: "var(--ak-faint)", fontWeight: 500 }}>
              · {manifest?.version || "slice0"}
            </span>
          </span>
        </header>

        {/* Banner */}
        <div className="ak-banner" data-testid="env-banner">
          <Activity size={18} style={{ flex: "none", marginTop: 1 }} />
          <div>
            <strong>This is the live skeleton dashboard.</strong> The Emergent preview runs the
            FastAPI <code>api</code> service live (mounted from <code>apps/api</code>) plus this React
            status view. The full Dockerized multi-service stack (web, api, titiler, stac-api,
            postgis, minio, ingestion) builds and runs via Docker Compose locally and as separate
            Railway services. Storage/catalog, raster, BFF product contracts, and map UX arrive in
            later slices.
          </div>
        </div>

        {/* Services */}
        <section className="ak-section" data-testid="services-section">
          <SectionHead
            icon={Layers}
            title="Service topology"
            kicker={`${svcList.length} services · 1 public`}
          />
          <div className="ak-grid">
            {svcList.map((svc) => (
              <ServiceCard key={svc.id} svc={svc} />
            ))}
          </div>
        </section>

        {/* Architecture */}
        <section className="ak-section">
          <SectionHead icon={Network} title="Request flow & public-origin rule" />
          <ArchitectureDiagram />
        </section>

        {/* Live health */}
        <section className="ak-section" data-testid="health-section">
          <SectionHead icon={ShieldCheck} title="Live health checks (this environment)" />
          <div className="ak-health">
            {health.map((h) => (
              <div className="ak-health-item" key={h.key} data-testid={`health-${h.key}`}>
                <span
                  className={`ak-dot ${h.res === "ok" ? "green" : h.res === "fail" ? "red" : "defined"}`}
                />
                <span>
                  {h.label}
                  <br />
                  <span className="path">{h.path}</span>
                </span>
                <span className={`res ${h.res}`}>
                  {h.res === "ok" ? "200 OK" : h.res === "fail" ? "FAIL" : "…"}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* Pinned images */}
        <section className="ak-section">
          <SectionHead icon={Package} title="Pinned container images" />
          <div className="ak-panelbox" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ak-table" data-testid="pinned-images">
              <thead>
                <tr>
                  <th>Component</th>
                  <th>Image / version</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(pinned).map(([k, v]) => (
                  <tr key={k}>
                    <td>{k}</td>
                    <td className="mono">{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Repo tree */}
        <section className="ak-section">
          <SectionHead
            icon={FolderTree}
            title="Monorepo structure"
            kicker={manifest?.repoTreeSource === "filesystem" ? "from filesystem" : "canonical"}
          />
          <div className="ak-panelbox ak-tree" data-testid="repo-tree">
            {repoTree ? (
              Object.entries(repoTree).map(([dir, children]) => (
                <div key={dir}>
                  <div className="dir">{dir}</div>
                  {children.map((c) => (
                    <div className="child" key={c}>
                      {c}
                    </div>
                  ))}
                </div>
              ))
            ) : (
              <div style={{ color: "var(--ak-muted)" }}>Structure manifest unavailable.</div>
            )}
          </div>
        </section>

        {/* Scope */}
        <section className="ak-section" data-testid="scope-section">
          <SectionHead icon={CheckCircle2} title="Scope for this slice" />
          <div className="ak-scope">
            <div className="ak-panelbox ak-in">
              <h3 style={{ margin: "0 0 12px", fontSize: 14, color: "var(--ak-green)" }}>
                In scope · Slice 0
              </h3>
              <ul>
                {inScope.map((item, i) => (
                  <li key={i}>
                    <CheckCircle2 size={16} className="mk" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="ak-panelbox ak-out">
              <h3 style={{ margin: "0 0 12px", fontSize: 14, color: "var(--ak-muted)" }}>
                Deferred · later slices
              </h3>
              <ul>
                {outScope.map((item, i) => (
                  <li key={i}>
                    <MinusCircle size={16} className="mk" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* Roadmap */}
        <section className="ak-section" data-testid="roadmap-section">
          <SectionHead icon={GitBranch} title="Slice roadmap" />
          <div className="ak-road">
            {roadmap.map((r) => (
              <div className={`ak-step ${r.status === "active" ? "active" : ""}`} key={r.id}>
                <div className="ph">{r.phase}</div>
                <div className="nm">{r.name}</div>
                <div className={`st ${r.status === "active" ? "active" : "planned"}`}>
                  {r.status === "active" ? "● ACTIVE" : "PLANNED"}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Env matrix */}
        <section className="ak-section">
          <SectionHead icon={Database} title="Environment matrix (placeholders only)" />
          <EnvAccordion env={env} />
        </section>

        <footer className="ak-footer">
          <ShieldCheck size={15} />
          <span>
            Akasha · Slice 0 · Only the web gateway is public · No default credentials · Public demos
            only with non-sensitive seed data unless an access gate is enabled.
          </span>
        </footer>
      </div>
    </div>
  );
}
