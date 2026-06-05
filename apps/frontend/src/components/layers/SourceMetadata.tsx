import { Radar, Satellite } from 'lucide-react';
import type { Source } from '@/types/api';

/** One-line provenance for a source card: platform kind + provider. */
export function SourceMetadata({ source }: { source: Source }) {
    const isSar = source.kind === 'sar';
    const Icon = isSar ? Radar : Satellite;
    const kindLabel = isSar ? 'Radar' : 'Optical';

    return (
        <p
            className="flex items-center gap-1.5 text-[12px] leading-4 text-muted-foreground"
            data-testid={ `source-meta-${source.id}` }
        >
            <Icon className="size-3.5 shrink-0" strokeWidth={ 1.75 } />
            <span className="truncate">
                { kindLabel }
                { source.provider ? ` · ${source.provider}` : '' }
            </span>
        </p>
    );
}
