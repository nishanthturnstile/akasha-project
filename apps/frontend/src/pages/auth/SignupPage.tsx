import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LockKeyhole, Satellite, Sprout } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { useSignup } from '@/lib/queries';

export default function SignupPage() {
    const navigate = useNavigate();
    const signup = useSignup();
    const [displayName, setDisplayName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');

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
            <section className="relative hidden min-h-0 overflow-hidden border-r border-border bg-[hsl(222_38%_7%)] lg:block">
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_28%_22%,hsl(95_68%_45%/.2),transparent_30%),radial-gradient(circle_at_72%_70%,hsl(33_96%_56%/.16),transparent_34%),linear-gradient(145deg,hsl(222_40%_8%),hsl(190_28%_10%)_58%,hsl(110_24%_12%))]" />
                <div className="absolute inset-0 bg-[repeating-linear-gradient(0deg,transparent_0_23px,hsl(210_28%_92%/.34)_24px),repeating-linear-gradient(90deg,transparent_0_23px,hsl(210_28%_92%/.18)_24px)] opacity-[0.14]" />
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