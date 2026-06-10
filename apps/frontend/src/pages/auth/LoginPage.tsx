import { FormEvent, useState } from 'react';
import { LockKeyhole, Satellite } from 'lucide-react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { useAccountMe, useLogin } from '@/lib/queries';

export default function LoginPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const account = useAccountMe();
  const login = useLogin();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const returnTo = params.get('returnTo') || '/monitoring/field-analytics';

  if (account.isSuccess) {
    return <Navigate to={ returnTo } replace />;
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    login.mutate(
      { username, password, rememberMe },
      {
        onSuccess: (result) => {
          if (result.user.id) {
            navigate(returnTo, { replace: true });
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
      <section className="relative hidden min-h-0 overflow-hidden border-r border-border bg-[hsl(222_38%_7%)] lg:block">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_22%_25%,hsl(33_96%_56%/.18),transparent_32%),linear-gradient(145deg,hsl(222_40%_8%),hsl(190_28%_10%)_58%,hsl(110_24%_12%))]" />
        <div className="absolute inset-0 opacity-[0.16] [background-image:repeating-linear-gradient(0deg,transparent_0_23px,hsl(210_28%_92%/.34)_24px),repeating-linear-gradient(90deg,transparent_0_23px,hsl(210_28%_92%/.18)_24px)]" />
        <div className="relative flex h-full flex-col justify-between p-10">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Satellite className="size-5" strokeWidth={ 1.75 } />
            </div>
            <div>
              <p className="font-display text-lg font-semibold">Akasha</p>
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Crop intelligence
              </p>
            </div>
          </div>
          <div className="max-w-xl">
            <p className="font-display text-4xl font-semibold leading-tight">
              Secure field intelligence for each workspace.
            </p>
            <p className="mt-4 max-w-lg text-sm leading-6 text-muted-foreground">
              Fields, seasons, analytics, scouting tasks, and reports are scoped to the signed-in
              user and team.
            </p>
          </div>
        </div>
      </section>

      <section className="flex min-h-screen items-center justify-center px-5 py-8">
        <div className="w-full max-w-[360px]">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex size-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Satellite className="size-5" strokeWidth={ 1.75 } />
            </div>
            <div>
              <p className="font-display text-lg font-semibold">Akasha</p>
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Crop intelligence
              </p>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card p-5 text-card-foreground shadow-e2">
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
                  className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none transition-colors focus:border-primary"
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
                  className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none transition-colors focus:border-primary"
                  required
                />
              </label>
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input
                  checked={ rememberMe }
                  onChange={ (event) => setRememberMe(event.target.checked) }
                  type="checkbox"
                  className="size-4 rounded border-input accent-[hsl(var(--primary))]"
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
          </div>
        </div>
      </section>
    </main>
  );
}
