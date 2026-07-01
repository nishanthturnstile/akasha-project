# Fix: Logout from field detail route hangs / shows black screen

## Problem
Logout from `/monitoring/field-analytics/field/:plotId` fails silently — no navigation to `/login`, page appears frozen.

## Root cause
`queueMicrotask(() => { queryClient.clear(); })` runs after `navigate()` is scheduled. The microtask fires `clear()` while React is committing the route transition, wiping all active query data. Components in the old tree (FieldAnalyticsPage, MapPage) crash mid-render from undefined query data, and the navigation to `/login` never commits.

## Fix

### File: `apps/frontend/src/components/shell/AppShell.tsx`
**Lines 873-879 — Replace:**

```tsx
                        // Navigate first to unmount the old component tree, THEN
                        // clear the query cache. If we clear before navigating,
                        // active queries lose their data mid-render while the old
                        // tree is still mounted, crashing components that access
                        // query data (e.g. FieldAnalyticsPage → black screen).
                        navigate('/login?loggedOut=1', { replace: true });
                        queueMicrotask(() => { queryClient.clear(); });
```

**With:**

```tsx
                        // Navigate away from the protected tree so all query-
                        // dependent components unmount safely. After this, stale
                        // account data remains in the cache but LoginPage won't
                        // redirect because of the ?loggedOut=1 param.
                        navigate('/login?loggedOut=1', { replace: true });
```

### If `queryClient` is no longer referenced elsewhere in the file
Remove the import:
```tsx
import { queryClient } from '@/lib/queryClient';
```

Check if `queryClient` is used elsewhere in `AppShell.tsx` first. If it's only used in the logout handler, remove the import.

## Already done (previous round)
These changes are already in place and correct:
- `LoginPage.tsx:22,24` — `const justLoggedOut = params.has('loggedOut');` and `if (account.isSuccess && !justLoggedOut)` — prevents auto-redirect when returning from logout
