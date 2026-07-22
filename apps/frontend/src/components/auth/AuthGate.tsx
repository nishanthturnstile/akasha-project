import { Navigate, useLocation } from 'react-router-dom';
import { BrandLockup } from '@/components/BrandLockup';
import { ApiError } from '@/lib/api';
import { useAccountMe } from '@/lib/queries';
import { MAIN_MONITORING_ROUTE } from '@/routes/productNavigation';

interface AuthGateProps {
  children: JSX.Element;
  onboardingOnly?: boolean;
  requireOnboardingComplete?: boolean;
  requiredRoles?: string[];
}

export function AuthGate({
  children,
  onboardingOnly = false,
  requireOnboardingComplete = false,
  requiredRoles,
}: AuthGateProps) {
  const location = useLocation();
  const account = useAccountMe();

  if (account.isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="glass-card scan-sweep flex h-20 w-70 max-w-[80vw] items-center px-5">
          <BrandLockup variant="compact" />
        </div>
      </div>
    );
  }

  if (account.error instanceof ApiError && account.error.status === 401) {
    const returnTo = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={ `/login?returnTo=${encodeURIComponent(returnTo)}` } replace />;
  }

  if (account.isError) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background px-4">
        <div className="glass-card hero-pattern w-full max-w-md p-5 text-card-foreground">
          <BrandLockup className="mb-4" variant="compact" />
          <h1 className="font-display text-lg font-bold">Akasha by CIDSA is unavailable</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Account verification could not complete. Check the API service and try again.
          </p>
        </div>
      </div>
    );
  }

  if (account.isSuccess) {
    const onboardingCompleted = account.data?.user?.onboardingCompleted ?? true;
    if (onboardingOnly && onboardingCompleted) {
      return <Navigate to={ MAIN_MONITORING_ROUTE } replace />;
    }
    if (requireOnboardingComplete && !onboardingCompleted) {
      return <Navigate to="/onboarding/step1" replace />;
    }
    if (requiredRoles?.length) {
      const role = account.data.currentTeam.role;
      if (!requiredRoles.includes(role)) {
        return <Navigate to={ MAIN_MONITORING_ROUTE } replace />;
      }
    }
  }

  return children;
}
