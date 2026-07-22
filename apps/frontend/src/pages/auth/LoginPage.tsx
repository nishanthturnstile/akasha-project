import { FormEvent, useState } from 'react';
import { LockKeyhole } from 'lucide-react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { BrandLockup } from '@/components/BrandLockup';
import { AuthHero } from '@/components/auth/AuthHero';
import { authInputClassName } from '@/components/auth/authStyles';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { useAccountMe, useLogin } from '@/lib/queries';
import { MAIN_MONITORING_ROUTE } from '@/routes/productNavigation';

function landingRoute(onboardingCompleted: boolean) {
  return onboardingCompleted ? MAIN_MONITORING_ROUTE : '/onboarding/step1';
}

export default function LoginPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const account = useAccountMe();
  const login = useLogin();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const returnTo = params.get('returnTo');
  const justLoggedOut = params.has('loggedOut');

  if (account.isSuccess && !justLoggedOut) {
    return <Navigate to={ returnTo || landingRoute(account.data.user.onboardingCompleted) } replace />;
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    login.mutate(
      { username, password, rememberMe },
      {
        onSuccess: (result) => {
          if (result.user.id) {
            navigate(returnTo || landingRoute(result.user.onboardingCompleted), { replace: true });
          }
        },
      },
    );
  };

  const message =
    login.error instanceof ApiError
      ? login.error.message
      : login.isError
        ? 'Unable to sign in.'
        : null;

  return (
    <main className="grid min-h-screen bg-background text-foreground lg:grid-cols-[minmax(0,1fr)_440px]">
      <AuthHero
        description="Fields, seasons, analytics, scouting tasks, and reports are scoped to the signed-in user and team."
        imagePosition="48% center"
        imageSrc="/images/onboarding1.png"
        title="Secure field intelligence for each workspace."
      />

      <section className="flex min-h-screen items-center justify-center px-5 py-8">
        <div className="w-full max-w-90">
          <BrandLockup className="mb-8 lg:hidden" variant="full" />

          <div className="gradient-border rounded-xl border border-primary/10 bg-card p-5 text-card-foreground shadow-e2">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <h1 className="font-display text-xl font-semibold">Sign in</h1>
                <p className="mt-1 text-sm text-muted-foreground">Use your Akasha account.</p>
              </div>
              <LockKeyhole className="size-5 text-primary" strokeWidth={ 1.75 } />
            </div>

            <form className="grid gap-4" onSubmit={ submit }>
              <label className="grid gap-1.5 text-sm">
                <span className="text-muted-foreground">Username</span>
                <input
                  value={ username }
                  onChange={ (event) => setUsername(event.target.value) }
                  autoComplete="username"
                  className={ authInputClassName }
                  required
                />
              </label>
              <label className="grid gap-1.5 text-sm">
                <span className="text-muted-foreground">Password</span>
                <input
                  value={ password }
                  onChange={ (event) => setPassword(event.target.value) }
                  autoComplete="current-password"
                  type="password"
                  className={ authInputClassName }
                  required
                />
              </label>
              <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm text-muted-foreground">
                <input
                  checked={ rememberMe }
                  onChange={ (event) => setRememberMe(event.target.checked) }
                  type="checkbox"
                  className="size-5 rounded border-input accent-primary"
                />
                Keep me signed in
              </label>
              { message && (
                <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  { message }
                </p>
              ) }
              <Button type="submit" size="lg" disabled={ login.isPending } className="w-full">
                { login.isPending ? 'Signing in...' : 'Sign in' }
              </Button>
            </form>
            <p className="mt-4 text-center text-sm text-muted-foreground">
              New to Akasha?{ ' ' }
              <Link to="/signup" className="inline-flex min-h-11 items-center font-semibold text-interactive underline-offset-4 hover:underline">
                Create an account
              </Link>
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
