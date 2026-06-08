---
title: Auth, Team, Admin, and Notifications Plan
status: draft
last_updated: 2026-06-04
---

# Auth, Team, Admin, and Notifications Plan

## Decision

Better Auth username/password remains the target customer-facing login provider. The FastAPI BFF is the authorization and resource ownership boundary.

Phase 12 implements the BFF-side foundations: users, teams, memberships, API key metadata, sessions, ownership columns, notification schema, and safe dev-mode dependencies. It does **not** implement password login, password verification, OAuth, SSO, MFA, or password reset.

## Local development mode

`AUTH_MODE=disabled` injects a deterministic dev user and team only when local/dev/test environments explicitly set `AUTH_ALLOW_DISABLED=true`. Runtime ownership checks must still use `team_id = current_team.id`; no protected route should rely on `team_id IS NULL`.

## Railway / deployment mode

Customer or Railway deployments must set `AUTH_MODE=enabled`, `AUTH_ALLOW_DISABLED=false`, and a strong `AUTH_PASSWORD_PEPPER`. Disabled auth is forbidden when Railway deployment environment variables are present. Protected routes fail closed with `AUTH_NOT_CONFIGURED` if auth is disabled in deployment.

## Session and identity boundary

Future Better Auth integration runs in the web/gateway layer and issues a signed session or gateway-attested identity. The BFF maps that identity to `akasha.users` and `akasha.teams`, then enforces ownership. Native BFF `akasha.sessions` exists as a fallback/dev-compatible session store only.

## Tables

- `akasha.users`: user identity, nullable/reserved `password_hash`, display name, status.
- `akasha.teams`: team records.
- `akasha.memberships`: user/team roles.
- `akasha.sessions`: hashed opaque session tokens.
- `akasha.api_keys`: hash-only API key metadata. Raw keys are returned only once on creation.
- `akasha.notifications`: team/user notification metadata.

## Ownership matrix

Direct `team_id`: plots, field activities, scout tasks, uploaded datasets, field groups, report templates, attachments, notifications, API keys, sessions.

Indirect: field group members are scoped through field groups and plots; index requests are scoped through `plot_id`.

Global/system: app settings, STAC/pgSTAC catalog, and seed data. Product configuration, sources, layers, tiles, and statistics are portal-authenticated BFF APIs.

## API key policy

Phase 12 API keys are an admin foundation only. They are stored hash-only and are not broad UI/admin authentication credentials. Machine endpoint permissions are deferred until scoped API access is designed.

## Notification scope

Phase 12 provides notification infrastructure and minimal emitters. Full field-change, risk-alert, task-assignment, and report-availability wiring is a Phase 13 hardening follow-up.
