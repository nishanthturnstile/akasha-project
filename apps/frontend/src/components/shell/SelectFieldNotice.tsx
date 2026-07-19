import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

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
            <Button asChild variant="primary" size="sm" className="mt-4">
                <Link to="/monitoring/field-analytics">
                    Go to Field analytics
                </Link>
            </Button>
        </section>
    );
}
