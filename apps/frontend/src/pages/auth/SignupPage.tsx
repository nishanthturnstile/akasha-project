import { FormEvent, useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { LockKeyhole, Sprout } from 'lucide-react';
import { BrandLockup } from '@/components/BrandLockup';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { useAccountMe, useSignup } from '@/lib/queries';
import { MAIN_MONITORING_ROUTE } from '@/routes/productNavigation';

function landingRoute(onboardingCompleted: boolean) {
    return onboardingCompleted ? MAIN_MONITORING_ROUTE : '/onboarding/step1';
}

export default function SignupPage() {
    const navigate = useNavigate();
    const account = useAccountMe();
    const signup = useSignup();
    const [displayName, setDisplayName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');

    if (account.isSuccess) {
        return <Navigate to={ landingRoute(account.data.user.onboardingCompleted) } replace />;
    }

    const submit = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        signup.mutate(
            { displayName: displayName.trim(), email: email.trim(), password },
            {
                onSuccess: () => navigate('/onboarding/step1', { replace: true }),
            },
        );
    };

    const message =
        signup.error instanceof ApiError
            ? signup.error.message
            : signup.isError
                ? 'Unable to create account.'
                : null;

    return (
        <main className="grid min-h-screen bg-background text-foreground lg:grid-cols-[minmax(0,1fr)_460px]">
            <section className="hero-pattern relative hidden min-h-0 overflow-hidden border-r border-primary/10 bg-bg-light-secondary dark:bg-background lg:block">
                <div className="grid-pattern absolute inset-0 opacity-70" />
                <div className="relative flex h-full flex-col justify-between p-10">
                    <BrandLockup variant="full" />
                    <div className="max-w-xl">
                        <p className="text-gradient font-display text-4xl font-bold leading-tight">
                            Start with your first season, then map every field.
                        </p>
                        <p className="mt-4 max-w-lg text-sm leading-6 text-muted-foreground">
                            Create an account, complete onboarding, and keep field records scoped to your own workspace.
                        </p>
                    </div>
                </div>
            </section>

            <section className="flex min-h-screen items-center justify-center px-5 py-8">
                <div className="w-full max-w-95">
                    <BrandLockup className="mb-8 lg:hidden" variant="full" />

                    <div className="gradient-border rounded-xl border border-primary/10 bg-card p-5 text-card-foreground shadow-e2">
                        <div className="mb-5 flex items-center justify-between gap-3">
                            <div>
                                <h1 className="font-display text-xl font-semibold">Create account</h1>
                                <p className="mt-1 text-sm text-muted-foreground">
                                    Sign up and continue to onboarding.
                                </p>
                            </div>
                            <div className="flex items-center gap-2 text-primary">
                                <Sprout className="size-5" strokeWidth={ 1.75 } />
                                <LockKeyhole className="size-5" strokeWidth={ 1.75 } />
                            </div>
                        </div>

                        <form className="grid gap-4" onSubmit={ submit }>
                            <label className="grid gap-1.5 text-sm">
                                <span className="text-muted-foreground">Name</span>
                                <input
                                    value={ displayName }
                                    onChange={ (event) => setDisplayName(event.target.value) }
                                    autoComplete="name"
                                    className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none transition-colors focus:border-primary"
                                    required
                                />
                            </label>
                            <label className="grid gap-1.5 text-sm">
                                <span className="text-muted-foreground">Email</span>
                                <input
                                    value={ email }
                                    onChange={ (event) => setEmail(event.target.value) }
                                    autoComplete="email"
                                    type="email"
                                    className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none transition-colors focus:border-primary"
                                    required
                                />
                            </label>
                            <label className="grid gap-1.5 text-sm">
                                <span className="text-muted-foreground">Password</span>
                                <input
                                    value={ password }
                                    onChange={ (event) => setPassword(event.target.value) }
                                    autoComplete="new-password"
                                    type="password"
                                    minLength={ 8 }
                                    className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none transition-colors focus:border-primary"
                                    required
                                />
                            </label>
                            { message && (
                                <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                                    { message }
                                </p>
                            ) }
                            <Button type="submit" size="lg" disabled={ signup.isPending } className="w-full">
                                { signup.isPending ? 'Creating account...' : 'Create account' }
                            </Button>
                        </form>
                        <p className="mt-4 text-center text-sm text-muted-foreground">
                            Already have an account?{ ' ' }
                            <Link to="/login" className="font-medium text-primary hover:underline">
                                Sign in
                            </Link>
                        </p>
                    </div>
                </div>
            </section>
        </main>
    );
}
