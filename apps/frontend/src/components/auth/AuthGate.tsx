import { Navigate, useLocation } from 'react-router-dom';
import { ApiError } from '@/lib/api';
import { useAccountMe } from '@/lib/queries';

interface AuthGateProps {
  children: JSX.Element;
}

export function AuthGate({ children }: AuthGateProps) {
  const location = useLocation();
  const account = useAccountMe();

  if (account.isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="glass scan-sweep h-20 w-[280px] max-w-[80vw]" />
      </div>
    );
  }

  if (account.error instanceof ApiError && account.error.status === 401) {
    const returnTo = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={`/login?returnTo=${encodeURIComponent(returnTo)}`} replace />;
  }

  if (account.isError) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background px-4">
        <div className="w-full max-w-md rounded-lg border border-border bg-card p-5 text-card-foreground shadow-e2">
          <h1 className="font-display text-lg font-semibold">Akasha is unavailable</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Account verification could not complete. Check the API service and try again.
          </p>
        </div>
      </div>
    );
  }

  return children;
}
