# Module 14 — Team Management

Guide page: <https://eos.com/user-guide/crop-monitoring/team-management/>

## Purpose
Shared **Team Accounts** so multiple users work off the same fields/data with
role-based access. Every account owner is automatically the **Owner** of a Team
Account. Reached via the account name (bottom-right of the side menu) → **Team
Management**. Especially valuable for delegating/completing/reporting scout tasks
(agro-cooperatives, consultants, traders, insurers).

## Sub-features

### 14.1 Add a user (invite)
- Account name → **Team Management** → **+ Invite New User** (or "INVITE A TEAM
  MEMBER" on first open).
- Invitation window: enter email(s), select the **fields or field groups** the user
  may access (one field / several / one+ groups / all), assign a **role** (role's
  permissions are shown under its name) → **Invite**.
- Invitee gets an email with a link to the Team Account. A user can belong to
  **multiple teams**.

### 14.2 Roles & permissions
Owner assigns one of three roles. Permission matrix:

| Capability | Admin | Scout | Observer |
|---|---|---|---|
| View fields & field groups | ✓ | ✓ | ✓ |
| Add fields to the team account | ✓ | ✓ | — |
| Edit all fields | ✓ | — | — |
| Create field groups | ✓ | — | — |
| Create scout tasks | ✓ | ✓ | ✓ |
| Assign members to scout tasks | ✓ | ✓ | — |
| Edit current scout tasks | ✓ | — | — |
| Close scout tasks | ✓ | — | — |
| Complete scout tasks | (via reports) | ✓ | ✓ (only own assigned) |
| Create scout reports | ✓ | — | — |
| Add new team members | ✓ | — | — |

(Owner = full control above Admin.)

### 14.3 Team Management dashboard
Owners/Admins see: list of members (incl. pending invitees), each member's role, the
fields/groups available to them, **last active** time, and available **actions**.

### 14.4 Actions
- Edit a user's field access; reassign their role; remove a user; **resend
  invitation** (for unaccepted invites).

### 14.5 Edit Team name
- Owner/Admin → pencil icon next to the name. (Keep short for easy recognition when
  switching.)

### 14.6 Switch Team
- My Account icon → **Switch team** → pick a team → **SAVE**. Shows current team,
  default team, and your role per team.

### 14.7 Default Team
- In the switch-team menu, a toggle sets a team as **default** (loaded on login).

## Cross-references
- Roles gate Scouting (module 08) and field/group management (modules 05/13).
- Field/group-scoped access ties to module 02 grouping and module 05 fields.

## Notes for replica
- RBAC with roles {Owner, Admin, Scout, Observer} and per-user resource scoping to
  fields/groups. Membership is many-to-many (user ↔ team) with per-team role.
- Invitation lifecycle (pending/accepted/resend), last-active tracking, team switch +
  default team. (Akasha already has owner/admin/member/viewer RBAC — role names will
  need mapping to EOS's Admin/Scout/Observer semantics.)
