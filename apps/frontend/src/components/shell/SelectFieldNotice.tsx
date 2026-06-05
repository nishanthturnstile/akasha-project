import { Link } from 'react-router-dom';

interface SelectFieldNoticeProps {
    title: string;
    message: string;
}

/**
 * Shared empty state for field-dependent modules. Provides an actionable link to
 * the Field analytics map where a field can be drawn, imported, or selected, so
 * these pages are not dead-ends when opened directly without a selected field.
 */
export function SelectFieldNotice({ title, message }: SelectFieldNoticeProps) {
    return (
        <section className="rounded-xl border border-dashed border-border/80 bg-card/80 p-6 text-sm text-muted-foreground">
            <h1 className="text-lg font-semibold text-foreground">{ title }</h1>
            <p className="mt-2">{ message }</p>
            <Link
                to="/monitoring/field-analytics"
                className="mt-4 inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            >
                Go to Field analytics
            </Link>
        </section>
    );
}
