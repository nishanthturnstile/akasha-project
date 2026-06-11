---
goal: Phase 7 repository deployment artifacts for Akasha self-hosted Coolify staging and production
version: 1.0
date_created: 2026-06-11
last_updated: 2026-06-11
owner: Akasha deployment operator
tags:
  - infrastructure
  - self-hosted
  - coolify
  - deployment
  - ci-cd
---

# Introduction

This implementation plan expands Phase 7 of `docs/impl-plan/infrastructure-selfhosted-coolify-azure-start-1.md` into executable repository tasks. The goal is to prepare the repository artifacts required before the first Coolify-managed staging deployment: a self-hosted Docker Compose file, environment-variable template, operator runbook, GitHub Actions deployment workflows, CI security scans, and authenticated smoke-test support.

The plan intentionally does not deploy Akasha to staging or production. Deployment begins in Phase 8 only after these artifacts are committed, reviewed, synced to the client repository, configured in Coolify, and supplied with environment-specific secrets outside the repository.

## 1. Requirements & Constraints

- **REQ-001**: Create `infra/selfhosted/coolify-compose.yml` as the self-hosted Coolify Compose source of truth for staging and production.
- **REQ-002**: Base `infra/selfhosted/coolify-compose.yml` on the existing service topology in `infra/docker/docker-compose.yml`.
- **REQ-003**: Preserve Akasha's multi-service topology: `web`, `api`, `titiler`, `stac-api`, `postgis`, `minio`, `ingestion-worker`, and `ingestion-sar` remain distinct services.
- **REQ-004**: Use prebuilt GHCR images for Akasha-built services: `akasha-web`, `akasha-api`, `akasha-ingestion-worker`, and `akasha-ingestion-sar`.
- **REQ-005**: Use Git SHA tags for Akasha-built image deployment references.
- **REQ-006**: Use pinned upstream images for `titiler`, `stac-api`, `postgis`, and `minio`.
- **REQ-007**: Create `infra/selfhosted/env.example` documenting all required Coolify variables without real secrets.
- **REQ-008**: Create `infra/selfhosted/README.md` documenting setup, first staging deploy, one-shot jobs, smoke tests, rollback, and production promotion.
- **REQ-009**: Extend `.github/workflows/ci.yml` with gitleaks and Trivy scans.
- **REQ-010**: Create `.github/workflows/deploy-staging.yml` to build and push the four Akasha images with the Git SHA tag and update/trigger the Coolify staging service stack.
- **REQ-011**: Create `.github/workflows/deploy-production.yml` to deploy only an operator-provided Git SHA tag after GitHub Environment approval.
- **REQ-012**: Extend `scripts/smoke-test.py` with optional `--login` mode using environment-provided credentials and cookie reuse.
- **SEC-001**: Do not commit real production or staging secrets.
- **SEC-002**: Do not publish host ports for `api`, `titiler`, `stac-api`, `postgis`, `minio`, `ingestion-worker`, or `ingestion-sar`.
- **SEC-003**: Only `web` may receive a Coolify FQDN/public route.
- **SEC-004**: Authenticated smoke credentials must be supplied only through environment variables at runtime.
- **SEC-005**: Production deployment workflow must not build images and must require an explicit immutable image SHA.
- **CON-001**: Do not use Azure App Service, Azure Database, Azure Blob Storage, Azure Container Registry, Azure DevOps, or Azure Key Vault.
- **CON-002**: Do not use Docker `build:` sections in the self-hosted Compose file.
- **CON-003**: Do not expose MinIO console or internal service ports publicly.
- **CON-004**: Do not deploy from this phase.
- **PAT-001**: Mount persistent staging/production data under `/srv/akasha`.
- **PAT-002**: Keep all self-hosted deployment artifacts under `infra/selfhosted/`.
- **PAT-003**: Keep implementation plans under `docs/impl-plan/`.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Create and validate the self-hosted Compose and environment contract.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Create directory `infra/selfhosted/`. | Yes — directory created by adding self-hosted artifacts. | 2026-06-11 |
| TASK-002 | Create `infra/selfhosted/coolify-compose.yml` with prebuilt Akasha image references, pinned upstream images, no `build:` blocks, no private-service `ports:`, and `/srv/akasha` bind mounts. | Yes — file created and YAML/guardrail validation passed. | 2026-06-11 |
| TASK-003 | Configure only `web` with Coolify FQDN magic variable `SERVICE_FQDN_WEB`; do not configure FQDN variables for private services. | Yes — validation confirmed only `web` contains `SERVICE_FQDN_WEB=/`. | 2026-06-11 |
| TASK-004 | Create `infra/selfhosted/env.example` with placeholders for image settings, public origin, database credentials, MinIO credentials, auth settings, raster settings, and SAR runtime knobs. | Yes — template created with placeholders only. | 2026-06-11 |
| TASK-005 | Create ignored local root `.env` placeholder only if absent, with non-secret values pointing operators to `infra/selfhosted/env.example`. | Skipped — root `.env` already exists and was left untouched to avoid overwriting local secret material. | 2026-06-11 |
| TASK-006 | Validate the Compose artifact has no `build:` blocks and no host `ports:` mappings. | Yes — Python YAML guardrail validation passed. | 2026-06-11 |

### Implementation Phase 2

- GOAL-002: Create operator documentation for Coolify and first deployment operations.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-007 | Create `infra/selfhosted/README.md` documenting Coolify resource setup and replacement of the placeholder `akasha-staging-compose`. | Yes — runbook created. | 2026-06-11 |
| TASK-008 | Document required Coolify variables and which values are secrets. | Yes — documented in `infra/selfhosted/README.md` and `infra/selfhosted/env.example`. | 2026-06-11 |
| TASK-009 | Document app migration command `python -m app.cli migrate` inside the `api` container. | Yes — documented in the first deployment checklist and one-shot jobs. | 2026-06-11 |
| TASK-010 | Document ingestion one-shot commands for seed/verify and SAR preprocessing. | Yes — documented in the runbook. | 2026-06-11 |
| TASK-011 | Document smoke-test commands including `--login`, private-port checks, and rollback procedure. | Yes — documented in the runbook. | 2026-06-11 |

### Implementation Phase 3

- GOAL-003: Create CI/CD workflows for image build, staging deploy, and production promotion.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | Extend `.github/workflows/ci.yml` with gitleaks secret scanning. | Yes — `gitleaks/gitleaks-action@v2` job added. | 2026-06-11 |
| TASK-013 | Extend `.github/workflows/ci.yml` with Trivy filesystem scanning. | Yes — `aquasecurity/trivy-action@0.28.0` filesystem scan job added. | 2026-06-11 |
| TASK-014 | Create `.github/workflows/deploy-staging.yml` guarded to `Akasha-TechCatalyst/akasha-project`, running on `self-hosted`, `linux`, `x64`, `akasha-control`, building four Akasha images, pushing Git SHA tags, rendering Compose with that SHA, patching the Coolify staging service stack, and triggering deployment. | Yes — workflow created and YAML parse validation passed; workflow has not been executed in this local implementation pass. | 2026-06-11 |
| TASK-015 | Create `.github/workflows/deploy-production.yml` guarded to `Akasha-TechCatalyst/akasha-project`, requiring manual `image_tag`, not building images, rendering Compose with that SHA, patching the Coolify production service stack, and triggering deployment. | Yes — workflow created and YAML parse validation passed; production execution remains blocked on environment approval and production server/resource creation. | 2026-06-11 |
| TASK-016 | Document required repository secrets and variables for both deployment workflows. | Yes — documented in `infra/selfhosted/README.md`. | 2026-06-11 |

### Implementation Phase 4

- GOAL-004: Extend smoke tests and update parent Phase 7 status.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-017 | Extend `scripts/smoke-test.py` with `--login`, `AKASHA_SMOKE_USERNAME`, `AKASHA_SMOKE_PASSWORD`, optional `AKASHA_SMOKE_REMEMBER_ME`, and cookie-jar reuse. | Yes — implemented with `http.cookiejar` and shared opener cookie reuse. | 2026-06-11 |
| TASK-018 | Validate Python syntax for `scripts/smoke-test.py`. | Yes — `python -m py_compile scripts/smoke-test.py` passed. | 2026-06-11 |
| TASK-019 | Validate workflow YAML and Compose YAML parse successfully. | Yes — local PyYAML parse validation passed for Compose and all edited workflows. | 2026-06-11 |
| TASK-020 | Update `docs/impl-plan/infrastructure-selfhosted-coolify-azure-start-1.md` Phase 7 task statuses. | Yes — parent implementation plan updated with Phase 7 artifact status and validation evidence. | 2026-06-11 |

## 3. Alternatives

- **ALT-001**: Deploy from `infra/docker/docker-compose.yml` directly. Rejected because it contains `build:` blocks and local bind mounts that are not appropriate for Coolify staging/production.
- **ALT-002**: Build images directly on staging or production. Rejected because staging and production must pull immutable prebuilt images.
- **ALT-003**: Expose `api`, `titiler`, `stac-api`, `postgis`, or `minio` with direct host ports. Rejected because it violates the one-public-service rule.
- **ALT-004**: Use mutable `latest` image tags for production. Rejected because production must use a Git SHA image tag previously validated in staging.
- **ALT-005**: Store Coolify/GHCR/database/MinIO credentials in repository files. Rejected because secrets must be supplied through Coolify and GitHub secrets only.

## 4. Dependencies

- **DEP-001**: Existing local Compose source at `infra/docker/docker-compose.yml`.
- **DEP-002**: Existing gateway Dockerfile and Caddyfile under `infra/gateway/`.
- **DEP-003**: Existing Akasha image build definitions under `infra/gateway/Dockerfile`, `apps/api/Dockerfile`, `services/ingestion/Dockerfile`, and `services/ingestion-sar/Dockerfile`.
- **DEP-004**: GHCR package access for `ghcr.io/akasha-techcatalyst/*`.
- **DEP-005**: Coolify API token stored as GitHub secret `COOLIFY_TOKEN`.
- **DEP-006**: Coolify API base URL stored as GitHub secret `COOLIFY_API_URL`, including `/api/v1`.
- **DEP-007**: Coolify staging service UUID stored as GitHub variable `COOLIFY_STAGING_SERVICE_UUID`.
- **DEP-008**: Coolify production service UUID stored as GitHub variable `COOLIFY_PRODUCTION_SERVICE_UUID` before production deployment.
- **DEP-009**: GitHub Environment `production` configured with required reviewers before production workflow use.

## 5. Files

- **FILE-001**: `docs/impl-plan/infrastructure-selfhosted-coolify-phase7-deployment-artifacts-1.md` — detailed Phase 7 plan.
- **FILE-002**: `infra/selfhosted/coolify-compose.yml` — self-hosted Coolify Compose file.
- **FILE-003**: `infra/selfhosted/env.example` — environment-variable template without real secrets.
- **FILE-004**: `infra/selfhosted/README.md` — operator runbook.
- **FILE-005**: `.github/workflows/ci.yml` — add gitleaks and Trivy checks.
- **FILE-006**: `.github/workflows/deploy-staging.yml` — build/push/staging deploy workflow.
- **FILE-007**: `.github/workflows/deploy-production.yml` — manual production promotion workflow.
- **FILE-008**: `scripts/smoke-test.py` — authenticated smoke-test mode.
- **FILE-009**: `.env` — ignored local placeholder if absent.
- **FILE-010**: `docs/impl-plan/infrastructure-selfhosted-coolify-azure-start-1.md` — parent Phase 7 status updates.

## 6. Testing

- **TEST-001**: Parse `infra/selfhosted/coolify-compose.yml` and verify it contains no `build:` sections. **Status**: Passed on 2026-06-11.
- **TEST-002**: Parse `infra/selfhosted/coolify-compose.yml` and verify it contains no `ports:` host mappings. **Status**: Passed on 2026-06-11.
- **TEST-003**: Verify only `web` contains `SERVICE_FQDN_WEB` and no private service contains `SERVICE_FQDN` or `SERVICE_URL` public-route magic variables. **Status**: Passed on 2026-06-11.
- **TEST-004**: Run `python -m py_compile scripts/smoke-test.py`. **Status**: Passed on 2026-06-11.
- **TEST-005**: Parse GitHub workflow YAML files for syntax validity. **Status**: Passed on 2026-06-11.
- **TEST-006**: Run `git --no-pager diff --check`. **Status**: Passed on 2026-06-11.
- **TEST-007**: Run repository diagnostics for edited files. **Status**: Passed on 2026-06-11; no editor diagnostics found for edited files.

## 7. Risks & Assumptions

- **RISK-001**: Coolify API URL may be configured without `/api/v1`. Mitigation: document exact expected value and validate in workflow before curl calls.
- **RISK-002**: Production GitHub Environment approval may not be configured yet. Mitigation: workflow declares `environment: production`; operator must configure reviewers in GitHub settings before use.
- **RISK-003**: `SERVICE_FQDN_WEB=/` may generate a temporary Coolify domain if no custom domain is assigned. Mitigation: runbook instructs assigning only the web domain before deployment.
- **RISK-004**: Existing staging placeholder Compose resource UUID is environment-specific. Mitigation: workflow reads UUID from GitHub variables instead of hard-coding it.
- **RISK-005**: Staging may use HTTP by temporary IP, while secure cookies require HTTPS. Mitigation: env template documents `AUTH_COOKIE_SECURE=false` only for temporary HTTP rehearsal and `true` for DNS/TLS.
- **ASSUMPTION-001**: The client repository remains `Akasha-TechCatalyst/akasha-project`.
- **ASSUMPTION-002**: GitHub Container Registry namespace remains lowercase `akasha-techcatalyst`.
- **ASSUMPTION-003**: Coolify service stack API accepts `docker_compose_raw` base64 content for updating the Compose resource.
- **ASSUMPTION-004**: Staging and production persistent paths are available under `/srv/akasha`.

## 8. Related Specifications / Further Reading

- `docs/impl-plan/infrastructure-selfhosted-coolify-azure-start-1.md`
- `infra/docker/docker-compose.yml`
- `docs/platform-plan.md`
- `docs/architecture-tech-stack.md`
- `docs/engineering-dos-donts.md`
- Coolify Docker Compose docs: <https://coolify.io/docs/knowledge-base/docker/compose>
- Coolify GitHub Actions deploy docs: <https://coolify.io/docs/applications/ci-cd/github/actions>
