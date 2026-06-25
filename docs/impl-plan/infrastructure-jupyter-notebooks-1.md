---
goal: Add a public JupyterLab notebooks service to Akasha staging through the existing Coolify/web gateway
version: 1.0
date_created: 2026-06-24
last_updated: 2026-06-24
owner: Akasha Engineering (platform + operations)
tags: [infrastructure, coolify, notebooks, jupyterlab, staging, operations]
---

# Introduction

This plan adds a dedicated **Akasha JupyterLab notebooks service** to the self-hosted Coolify deployment path. The service is deployed to the existing `akasha-staging` VM, stores user notebooks under `/srv/akasha/notebooks`, and is reachable from the internet through a notebooks domain such as `https://notebooks.gis.cidsaglobal.com`.

The implementation must preserve Akasha's one-public-service architecture: only the `web` gateway is publicly exposed by Coolify. The new `notebooks` service remains private on the Docker Compose network with no host `ports:` mapping and no direct Coolify FQDN. Browser traffic for the notebooks hostname is routed by the existing `web`/Caddy gateway to `http://notebooks:8888`.

The first release intentionally does **not** add SSO, OAuth, Cloudflare Access, Caddy Basic Auth, or app-level RBAC for notebooks. However, Jupyter's built-in token/password protection remains mandatory. A fully unauthenticated public JupyterLab endpoint is explicitly out of scope because it would expose remote code execution on the staging VM.

## 1. Requirements & Constraints

### Functional requirements

- **REQ-001**: Add a separate deployable notebook image named `akasha-notebooks`.
- **REQ-002**: Add a private Compose service named `notebooks` to `infra/selfhosted/coolify-compose.yml`.
- **REQ-003**: Persist notebook files on the staging VM at `/srv/akasha/notebooks`.
- **REQ-004**: Mount `/srv/akasha/notebooks` into the notebook container at `/home/jovyan/work`.
- **REQ-005**: Expose the notebooks UI through a public notebooks hostname, expected initial value `notebooks.gis.cidsaglobal.com` unless changed during deployment.
- **REQ-006**: Route notebooks traffic through the existing `web` gateway and Caddy, not by making the `notebooks` container directly public.
- **REQ-007**: Keep existing Akasha app routes unchanged: `/health`, `/api/*`, `/tiles/*`, and the React SPA fallback must continue working.
- **REQ-008**: Support JupyterLab WebSockets through the gateway so notebook kernels and terminals work.
- **REQ-009**: Add the notebook image to staging CI build/push workflows.
- **REQ-010**: Add the notebook image to immutable deployment verification before Coolify is patched.
- **REQ-011**: Update canonical service metadata so the BFF skeleton registry includes `notebooks` while keeping only `web` public.
- **REQ-012**: Document staging setup, Coolify env values, DNS, validation, rollback, and operational guardrails.

### Security requirements

- **SEC-001**: The `notebooks` service must not have a Compose `ports:` mapping.
- **SEC-002**: The `notebooks` service must not define any `SERVICE_FQDN_*` environment variable.
- **SEC-003**: Azure NSG port `8888` must not be opened for direct internet access.
- **SEC-004**: Jupyter built-in token/password authentication must be enabled for the public notebooks URL.
- **SEC-005**: `JUPYTER_TOKEN` or equivalent Jupyter password configuration must be provided through Coolify secrets/environment variables only.
- **SEC-006**: Real Jupyter tokens, passwords, generated URLs containing tokens, Azure credentials, provider credentials, MinIO credentials, Postgres credentials, and Bhoonidhi credentials must never be committed to the repository.
- **SEC-007**: The notebook image must not bake secrets, SSH keys, Azure CLI credentials, provider credentials, or staging service credentials into image layers.
- **SEC-008**: The first implementation must not mount `/srv/akasha/data`, `/srv/akasha/ingestion`, MinIO data, Postgres data, Docker socket, or provider raw archives into the notebook container.
- **SEC-009**: Public documentation must instruct users to share the base notebooks URL only, not URLs that include Jupyter tokens.
- **SEC-010**: The plan excludes fully unauthenticated public JupyterLab. If token/password is disabled, deployment must be considered a security failure.

### Operational constraints

- **OPS-001**: The new notebook service must deploy through the existing Coolify self-hosted Compose stack.
- **OPS-002**: The first runtime target is `akasha-staging`, not production.
- **OPS-003**: `/srv/akasha/notebooks` must be created on the staging VM before deployment.
- **OPS-004**: The host notebook directory must be owned by the Jupyter container user/group. For Jupyter Docker Stacks images, the expected host ownership is `1000:100` unless the chosen base image documents otherwise.
- **OPS-005**: Notebook workloads must not interfere with staging ingestion. Add conservative CPU/memory limits where supported by Coolify Compose, or document manual operator limits if Coolify rejects those fields.
- **OPS-006**: The custom notebook image must use pinned base image tags. Do not use `latest`.
- **OPS-007**: Notebook dependencies must be reproducible from files committed under `services/notebooks/`.
- **OPS-008**: Rollback must preserve `/srv/akasha/notebooks` unless an operator explicitly approves deletion.
- **OPS-009**: Existing staging deployment workflows must continue to build immutable Git SHA image tags.
- **OPS-010**: Existing production deployment workflow must verify the notebook image because production and staging share the self-hosted Compose template, even if notebooks are initially used only on staging.

### Architecture constraints

- **CON-001**: Preserve the Akasha one-public-service rule: only `web` is publicly reachable.
- **CON-002**: Browser access to notebooks must use HTTPS through the same public gateway path as other hosted services.
- **CON-003**: The `notebooks` service must be reachable only on the private Docker network by `web`.
- **CON-004**: The initial notebook service must not become an alternate access path to MinIO, PostGIS, pgSTAC, TiTiler, Bhoonidhi, or raw provider archives.
- **CON-005**: The implementation must not change production raster/source behavior, ingestion behavior, or app authentication behavior.
- **CON-006**: Keep all documentation under `docs/` and deployment artifacts under existing `infra/`, `.github/`, `services/`, `tests/`, and `apps/` paths.

### Guidelines and patterns

- **GUD-001**: Follow the existing `infra/selfhosted/coolify-compose.yml` style: prebuilt images, immutable Git SHA tags, `pull_policy: always`, `expose` for private ports, and no public host `ports:`.
- **GUD-002**: Follow the existing gateway pattern in `infra/gateway/Caddyfile`: one Caddy container handles public routing and proxies to private upstreams.
- **GUD-003**: Add tests before implementation where practical, especially for deployment guardrails.
- **GUD-004**: Prefer explicit environment-variable names over hidden defaults.
- **GUD-005**: Add documentation that an operator can follow without reading this implementation plan.
- **GUD-006**: Avoid overloading the first release with JupyterHub, per-user accounts, SSO, or direct internal data mounts.

### Environment variables

- **ENV-001**: `SERVICE_FQDN_NOTEBOOKS` — public notebooks FQDN consumed by Coolify/web routing, for example `https://notebooks.gis.cidsaglobal.com`.
- **ENV-002**: `NOTEBOOKS_HOST` — hostname matcher for Caddy, for example `notebooks.gis.cidsaglobal.com`.
- **ENV-003**: `NOTEBOOKS_PUBLIC_ORIGIN` — exact public notebooks origin, for example `https://notebooks.gis.cidsaglobal.com`.
- **ENV-004**: `NOTEBOOKS_UPSTREAM_URL` — private upstream for Caddy, default `http://notebooks:8888`.
- **ENV-005**: `JUPYTER_TOKEN` — required secret used by JupyterLab token auth.
- **ENV-006**: `NOTEBOOKS_CPU_LIMIT` — optional staging CPU limit if implemented as an environment-driven Compose value.
- **ENV-007**: `NOTEBOOKS_MEMORY_LIMIT` — optional staging memory limit if implemented as an environment-driven Compose value.

## 2. Implementation Steps

### Implementation Phase 1 — Deployment contract and tests

- GOAL-001: Lock the notebook exposure contract before adding runtime implementation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Create `tests/test_selfhosted_notebooks_compose.py` with YAML parsing for `infra/selfhosted/coolify-compose.yml`. Assert service `notebooks` exists, uses the custom `akasha-notebooks` image expression, has `expose: ["8888"]`, has no `ports` key, has no environment key starting with `SERVICE_FQDN_`, and mounts `/srv/akasha/notebooks:/home/jovyan/work`. | | |
| TASK-002 | In `tests/test_selfhosted_notebooks_compose.py`, add assertions that service `web` has `SERVICE_FQDN_NOTEBOOKS`, `NOTEBOOKS_HOST`, and `NOTEBOOKS_UPSTREAM_URL` environment values, and that `web.depends_on.notebooks.condition` is `service_started`. | | |
| TASK-003 | In `tests/test_selfhosted_notebooks_compose.py`, add Caddyfile text assertions for `NOTEBOOKS_HOST`, `NOTEBOOKS_UPSTREAM_URL`, and a notebooks reverse proxy route that appears before the default SPA `handle` block. | | |
| TASK-004 | Modify `tests/test_deploy_workflows.py` so `AKASHA_IMAGES` includes `akasha-notebooks`. Ensure existing staging and production tests verify the notebook image before Coolify patching. | | |
| TASK-005 | Modify `apps/api/tests/test_health.py` so expected skeleton service IDs include `notebooks`, the registry length expectation becomes 8, and public services remain exactly `["web"]`. | | |
| TASK-006 | Search for hard-coded service count `7`, public service assumptions, or deployable image lists in `backend_test.py`, validators, and tests. Update only expectations directly affected by adding the private notebook service. | | |

### Implementation Phase 2 — Custom notebook image

- GOAL-002: Add a reproducible custom Akasha JupyterLab image without committing secrets or notebooks.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | Create directory `services/notebooks/`. | | |
| TASK-008 | Create `services/notebooks/environment.yml` with the pinned runtime dependencies needed for first-phase Akasha notebooks: Python 3.11, JupyterLab, pandas, numpy, matplotlib, requests, geopandas, shapely, pyproj, rasterio, rio-cogeo, folium, and ipyleaflet. | | |
| TASK-009 | Create `services/notebooks/Dockerfile` using a pinned Jupyter Docker Stacks base image. The Dockerfile must copy `environment.yml`, install dependencies reproducibly, set `/home/jovyan/work` as the work directory, and continue running as the non-root Jupyter user. | | |
| TASK-010 | Add a Dockerfile comment explaining that secrets, provider credentials, Azure credentials, SSH keys, raw provider archives, and staging service credentials must not be copied into the notebook image. | | |
| TASK-011 | Validate that the selected base image tag is pinned and not `latest`. If the initially chosen tag is unavailable, replace it with a documented fixed tag and update `apps/api/app/skeleton.py` pinned image metadata in Phase 6. | | |

### Implementation Phase 3 — CI/CD workflow integration

- GOAL-003: Build, push, and verify the custom notebook image as part of the existing immutable deployment flow.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | Modify `.github/workflows/deploy-staging.yml` build matrix to include image `akasha-notebooks`, context `services/notebooks`, Dockerfile `services/notebooks/Dockerfile`, and empty build args. | | |
| TASK-013 | Modify `.github/workflows/deploy-staging.yml` `Verify immutable image tags exist` step to check `akasha-notebooks:${IMAGE_TAG}` before patching Coolify. | | |
| TASK-014 | Modify `.github/workflows/deploy-production.yml` `Verify immutable image tags exist` step to check `akasha-notebooks:${IMAGE_TAG}` before patching Coolify. | | |
| TASK-015 | Run `python -m pytest tests/test_deploy_workflows.py -q`. Expected result: workflow image verification tests pass and inline Python snippets compile. | | |

### Implementation Phase 4 — Coolify Compose service

- GOAL-004: Add the private notebook service to the self-hosted Compose template while keeping only `web` public.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-016 | Modify `infra/selfhosted/coolify-compose.yml` service `web.environment` to include `SERVICE_FQDN_NOTEBOOKS`, `NOTEBOOKS_HOST`, and `NOTEBOOKS_UPSTREAM_URL`. Use `NOTEBOOKS_UPSTREAM_URL` default `http://notebooks:8888`. | | |
| TASK-017 | Modify `infra/selfhosted/coolify-compose.yml` service `web.depends_on` to include `notebooks` with `condition: service_started`. | | |
| TASK-018 | Add service `notebooks` to `infra/selfhosted/coolify-compose.yml` using image `${IMAGE_REGISTRY:-ghcr.io}/${IMAGE_NAMESPACE:-akasha-techcatalyst}/akasha-notebooks:${IMAGE_TAG:?IMAGE_TAG must be set to a Git SHA}` and `pull_policy: always`. | | |
| TASK-019 | Configure service `notebooks` with environment value `JUPYTER_TOKEN: "${JUPYTER_TOKEN:?JUPYTER_TOKEN must be set for public notebooks}"`. | | |
| TASK-020 | Configure service `notebooks` command to start JupyterLab on `0.0.0.0:8888`, disable browser launch, set notebook root to `/home/jovyan/work`, and use the configured token. | | |
| TASK-021 | Configure service `notebooks` with `expose: ["8888"]`, `volumes: [/srv/akasha/notebooks:/home/jovyan/work]`, and `restart: unless-stopped`. | | |
| TASK-022 | Do not add a `ports:` mapping to service `notebooks`. Do not add any `SERVICE_FQDN_*` environment value to service `notebooks`. | | |
| TASK-023 | Add compatible CPU/memory guardrails to service `notebooks` if Coolify accepts them. If Coolify rejects `cpus` or `mem_limit`, remove those fields and document resource limits as operator guidance in `infra/selfhosted/README.md`. | | |
| TASK-024 | Run `python -m pytest tests/test_selfhosted_notebooks_compose.py -q`. Expected result: compose guardrails pass. | | |

### Implementation Phase 5 — Gateway routing

- GOAL-005: Route the notebooks hostname through the existing public Caddy gateway without changing existing app routes.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-025 | Modify `infra/gateway/Caddyfile` inside the existing `:{$PORT:80}` server block to add a host matcher named `@notebooks` using `{$NOTEBOOKS_HOST:notebooks.invalid}`. | | |
| TASK-026 | Add `handle @notebooks` before `/api/*`, `/tiles/*`, and the default SPA fallback handler. | | |
| TASK-027 | Inside `handle @notebooks`, reverse proxy to `{$NOTEBOOKS_UPSTREAM_URL:http://notebooks:8888}`. | | |
| TASK-028 | Preserve existing `/health`, `/api/*`, `/tiles/*`, and SPA fallback behavior. | | |
| TASK-029 | Run `python -m pytest tests/test_selfhosted_notebooks_compose.py -q`. Expected result: Caddyfile route assertions pass. | | |

### Implementation Phase 6 — Canonical service metadata

- GOAL-006: Keep Akasha's service registry, env matrix, and skeleton tests consistent with the new private service.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-030 | Modify `apps/api/app/skeleton.py` `PINNED_IMAGES` to include the pinned Jupyter base image or `akasha-notebooks` image metadata. | | |
| TASK-031 | Modify `apps/api/app/skeleton.py` `SERVICES` to add a `notebooks` entry with `public: False`, runtime `JupyterLab`, image `akasha-notebooks`, build path `services/notebooks/Dockerfile`, internal port `8888`, health type `http`, persistent volume `True`, and dependency relationship through the `web` gateway. | | |
| TASK-032 | Modify `apps/api/app/skeleton.py` `ENV_MATRIX` to add a `notebooks` section with placeholder-only values for `JUPYTER_TOKEN`, `NOTEBOOKS_HOST`, `NOTEBOOKS_PUBLIC_ORIGIN`, and `NOTEBOOKS_UPSTREAM_URL`. | | |
| TASK-033 | Update `apps/api/tests/test_health.py` registry consistency checks so `len(skeleton.SERVICES) == 8` and `notebooks` is included in expected service IDs. | | |
| TASK-034 | Run `cd apps/api && python -m pytest tests/test_health.py -q`. Expected result: skeleton metadata tests pass. | | |

### Implementation Phase 7 — Environment template and operator documentation

- GOAL-007: Document exactly how operators configure, deploy, validate, and roll back notebooks on staging.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-035 | Modify `infra/selfhosted/env.example` to add a `JupyterLab notebooks` section with `SERVICE_FQDN_NOTEBOOKS`, `NOTEBOOKS_HOST`, `NOTEBOOKS_PUBLIC_ORIGIN`, `NOTEBOOKS_UPSTREAM_URL`, and `JUPYTER_TOKEN=CHANGE_ME_JUPYTER_TOKEN`. | | |
| TASK-036 | Modify `infra/selfhosted/README.md` required target directories to include `/srv/akasha/notebooks`. | | |
| TASK-037 | Add staging host setup commands to `infra/selfhosted/README.md`: create `/srv/akasha/notebooks` and set ownership to the Jupyter container user/group, expected `sudo chown -R 1000:100 /srv/akasha/notebooks`. | | |
| TASK-038 | Add Coolify environment setup instructions to `infra/selfhosted/README.md`, including generation of a strong `JUPYTER_TOKEN` without printing it in chat or committing it. | | |
| TASK-039 | Add DNS instructions to `infra/selfhosted/README.md`: the notebooks hostname must point to the same staging/Coolify ingress used by `web`; direct port `8888` must not be exposed. | | |
| TASK-040 | Add security notes to `infra/selfhosted/README.md`: Jupyter token/password is the first-phase minimum, tokenized URLs must not be shared, SSO/proxy auth is deferred, and fully unauthenticated public Jupyter is not allowed. | | |
| TASK-041 | Add rollback instructions to `infra/selfhosted/README.md`: remove notebooks FQDN/env from Coolify, redeploy previous SHA or a compose without `notebooks`, confirm the main app still works, and preserve `/srv/akasha/notebooks` unless deletion is explicitly approved. | | |

### Implementation Phase 8 — Validation and staging rollout

- GOAL-008: Verify the implementation locally and on staging without weakening network security.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-042 | Run `python -m pytest tests/test_deploy_workflows.py tests/test_selfhosted_notebooks_compose.py -q`. Expected result: deployment and compose guardrail tests pass. | | |
| TASK-043 | Run `cd apps/api && python -m pytest tests/test_health.py -q`. Expected result: skeleton tests pass. | | |
| TASK-044 | Run `python scripts/validate_slice0.py`. Expected result: slice 0 skeleton validation passes with the updated service registry. | | |
| TASK-045 | Trigger or wait for the staging workflow to build and push `ghcr.io/akasha-techcatalyst/akasha-notebooks:<git-sha>`. Expected result: GHCR contains the immutable notebook image tag. | | |
| TASK-046 | On `akasha-staging`, create `/srv/akasha/notebooks` and set ownership to the Jupyter image user/group before deployment. | | |
| TASK-047 | In Coolify staging env, set `SERVICE_FQDN_NOTEBOOKS`, `NOTEBOOKS_HOST`, `NOTEBOOKS_PUBLIC_ORIGIN`, `NOTEBOOKS_UPSTREAM_URL`, and `JUPYTER_TOKEN`. Expected result: no `CHANGE_ME` placeholders remain for notebook variables. | | |
| TASK-048 | Configure DNS for the notebooks hostname to target the same staging/Coolify ingress. Expected result: the hostname resolves to the staging public ingress. | | |
| TASK-049 | Deploy staging through the existing workflow. Expected result: Coolify stack runs `akasha-notebooks:<git-sha>`. | | |
| TASK-050 | Verify `https://notebooks.gis.cidsaglobal.com/lab` or the chosen notebooks URL reaches JupyterLab and requires a token/password. | | |
| TASK-051 | Verify direct TCP access to `20.219.3.35:8888` remains closed or filtered. | | |
| TASK-052 | Verify existing staging app health, for example `https://<staging-app-domain>/api/health`, still returns OK. | | |
| TASK-053 | Create a small test notebook through JupyterLab, restart the notebooks container, and verify the notebook still exists under `/srv/akasha/notebooks`. | | |

## 3. Alternatives

- **ALT-001**: Expose Jupyter directly on `20.219.3.35:8888`. Rejected because it bypasses the web gateway, requires an Azure NSG rule for a remote-code-execution service, and violates the one-public-service rule.
- **ALT-002**: Give the `notebooks` service its own direct Coolify FQDN with `SERVICE_FQDN_NOTEBOOKS` on the notebook container. Rejected because it creates a second public service and weakens the current deployment invariant that only `web` is public.
- **ALT-003**: Use an upstream Jupyter image directly in Compose without a custom image. Rejected by team preference for a custom Akasha image with reproducible project-specific dependencies.
- **ALT-004**: Add JupyterHub with per-user accounts. Deferred because it is a larger platform change than the current need.
- **ALT-005**: Add Entra ID/OAuth/Cloudflare Access/Caddy Basic Auth immediately. Deferred by product decision for this first phase, but recommended as a follow-up if notebooks become long-lived team infrastructure.
- **ALT-006**: Run notebooks on `akasha-control`. Rejected for this first implementation because `akasha-control` is the Coolify/control server and should not become a compute notebook host.
- **ALT-007**: Create a new `akasha-notebooks` VM. Deferred as a better long-term isolation option if notebook use grows.
- **ALT-008**: Mount all staging data and secrets into notebooks for convenience. Rejected because it increases data exfiltration and credential leakage risk.

## 4. Dependencies

- **DEP-001**: Existing Coolify staging stack `infra/selfhosted/coolify-compose.yml`.
- **DEP-002**: Existing web gateway image built from `infra/gateway/Dockerfile` and configured by `infra/gateway/Caddyfile`.
- **DEP-003**: Existing staging workflow `.github/workflows/deploy-staging.yml` running on the `akasha-control` self-hosted runner.
- **DEP-004**: Existing production workflow `.github/workflows/deploy-production.yml` sharing the same Compose template.
- **DEP-005**: GHCR namespace `ghcr.io/akasha-techcatalyst` for `akasha-notebooks` image publication.
- **DEP-006**: Staging VM `akasha-staging` with persistent host path `/srv/akasha`.
- **DEP-007**: DNS control for the selected notebooks hostname.
- **DEP-008**: Coolify environment variable management for `SERVICE_FQDN_NOTEBOOKS`, `NOTEBOOKS_HOST`, `NOTEBOOKS_PUBLIC_ORIGIN`, `NOTEBOOKS_UPSTREAM_URL`, and `JUPYTER_TOKEN`.
- **DEP-009**: Jupyter Docker Stacks or another approved pinned base image.
- **DEP-010**: Python geospatial packages in the notebook image must have compatible binary dependencies for the selected base image.

## 5. Files

- **FILE-001**: `docs/impl-plan/infrastructure-jupyter-notebooks-1.md` — This implementation plan.
- **FILE-002**: `services/notebooks/Dockerfile` — New custom Akasha JupyterLab image.
- **FILE-003**: `services/notebooks/environment.yml` — New notebook dependency manifest.
- **FILE-004**: `infra/selfhosted/coolify-compose.yml` — Add private `notebooks` service and notebooks gateway environment values on `web`.
- **FILE-005**: `infra/gateway/Caddyfile` — Add host-based notebooks reverse proxy route.
- **FILE-006**: `infra/selfhosted/env.example` — Add notebooks public hostname and token placeholders.
- **FILE-007**: `infra/selfhosted/README.md` — Add notebook setup, deployment, validation, security, and rollback runbook.
- **FILE-008**: `.github/workflows/deploy-staging.yml` — Build, push, and verify `akasha-notebooks` image.
- **FILE-009**: `.github/workflows/deploy-production.yml` — Verify `akasha-notebooks` image before production Coolify patching.
- **FILE-010**: `tests/test_deploy_workflows.py` — Update deployable image set to include `akasha-notebooks`.
- **FILE-011**: `tests/test_selfhosted_notebooks_compose.py` — New static tests for Compose and Caddy notebook exposure guardrails.
- **FILE-012**: `apps/api/app/skeleton.py` — Add notebook service metadata while keeping `public=False`.
- **FILE-013**: `apps/api/tests/test_health.py` — Update skeleton service expectations.
- **FILE-014**: `backend_test.py` — Update external skeleton expectations if hard-coded.
- **FILE-015**: `scripts/validate_slice0.py` — Update only if it has hard-coded service counts or public-service assumptions.

## 6. Testing

- **TEST-001**: Run `python -m pytest tests/test_selfhosted_notebooks_compose.py -q`. Expected: `notebooks` is private, has no `ports`, has no `SERVICE_FQDN_*`, mounts `/srv/akasha/notebooks`, and Caddy routes `NOTEBOOKS_HOST` to `NOTEBOOKS_UPSTREAM_URL`.
- **TEST-002**: Run `python -m pytest tests/test_deploy_workflows.py -q`. Expected: staging build matrix includes `akasha-notebooks`; staging and production verification loops check the immutable notebook image before Coolify patching.
- **TEST-003**: Run `cd apps/api && python -m pytest tests/test_health.py -q`. Expected: skeleton registry contains 8 services including `notebooks`; public service list remains exactly `['web']`.
- **TEST-004**: Run `python scripts/validate_slice0.py`. Expected: skeleton validation passes after service metadata updates.
- **TEST-005**: Run a Docker build for the notebook image, for example through the staging workflow or locally if Docker is available. Expected: `services/notebooks/Dockerfile` builds without using `latest` or secrets.
- **TEST-006**: After staging deployment, inspect GHCR/Coolify. Expected: `akasha-notebooks:<git-sha>` exists and is deployed in the Coolify stack.
- **TEST-007**: After staging deployment, open `https://notebooks.gis.cidsaglobal.com/lab` or the selected notebooks URL. Expected: JupyterLab loads and requires token/password.
- **TEST-008**: After staging deployment, verify direct public port access to `20.219.3.35:8888` is closed or filtered. Expected: direct TCP access fails.
- **TEST-009**: After staging deployment, verify the existing staging app health endpoint. Expected: `GET /api/health` through the main staging domain returns OK.
- **TEST-010**: Create a test notebook through the public notebooks URL, restart the `notebooks` container, and verify the file persists. Expected: notebook remains under `/srv/akasha/notebooks`.
- **TEST-011**: Review repository diff before merge. Expected: no real `JUPYTER_TOKEN`, tokenized URLs, provider credentials, SSH keys, or staging secrets appear in committed files.

## 7. Risks & Assumptions

- **RISK-001**: Public JupyterLab is remote code execution by design. Mitigation: require Jupyter token/password, avoid direct port exposure, and add SSO/proxy auth in a follow-up if usage grows.
- **RISK-002**: Users may share tokenized URLs. Mitigation: document that only the base notebooks URL should be shared.
- **RISK-003**: Notebook workloads may consume staging CPU/RAM and affect the app or ingestion. Mitigation: add resource limits where supported and document staging usage guardrails.
- **RISK-004**: Notebook outputs may fill disk under `/srv/akasha/notebooks`. Mitigation: document retention/cleanup and monitor disk usage.
- **RISK-005**: Adding geospatial Python packages can make the notebook image large or slow to build. Mitigation: pin dependencies and keep the first image minimal.
- **RISK-006**: Coolify may not accept some Compose resource-limit fields. Mitigation: validate in staging and remove incompatible fields while retaining operator guidance.
- **RISK-007**: A misconfigured Caddy route could break the main SPA fallback or API/tile routes. Mitigation: add static tests and smoke `/api/health` after deployment.
- **RISK-008**: A direct `SERVICE_FQDN_*` on `notebooks` could accidentally make it public. Mitigation: static tests fail if notebook service has direct FQDN configuration.
- **RISK-009**: Future operators may mount secrets or raw data into notebooks for convenience. Mitigation: document first-phase mount restrictions and require a separate security review for broader access.
- **RISK-010**: Production workflow may fail if shared Compose references `akasha-notebooks` but the image is not built for a production image tag. Mitigation: add the image to immutable verification and staging build workflow now.
- **ASSUMPTION-001**: The selected initial public hostname is `notebooks.gis.cidsaglobal.com`; if the team chooses another hostname, all plan references must be replaced consistently.
- **ASSUMPTION-002**: Coolify can route multiple FQDNs to the `web` service or pass the notebooks hostname to Caddy through environment variables.
- **ASSUMPTION-003**: The chosen Jupyter base image uses user/group compatible with host ownership `1000:100`.
- **ASSUMPTION-004**: The first notebook release does not require direct access to MinIO, PostGIS, pgSTAC, or raw raster archives.
- **ASSUMPTION-005**: The team accepts Jupyter token/password as the minimum first-phase access control.

## 8. Related Specifications / Further Reading

- [Akasha self-hosted Coolify deployment](../../infra/selfhosted/README.md)
- [Akasha web gateway Caddyfile](../../infra/gateway/Caddyfile)
- [Architecture and Tech Stack](../architecture-tech-stack.md)
- [Engineering Do's and Don'ts](../engineering-dos-donts.md)
- [Developer Setup Guide](../developer-setup-guide.md)
- [Staging Ingestion Developer Guide](../staging-ingestion-developer-guide.md)
- [Data Ingestion and Satellite Rules](../data-ingestion-and-satellite-rules.md)
- Jupyter Docker Stacks documentation: https://jupyter-docker-stacks.readthedocs.io/
- Jupyter Server security documentation: https://jupyter-server.readthedocs.io/en/latest/operators/security.html
- Caddy reverse proxy documentation: https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
