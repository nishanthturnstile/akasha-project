import { Radar, Satellite } from 'lucide-react';
import type { Source } from '@/types/api';

/** One-line provenance for a source card: platform kind + provider. */
export function SourceMetadata({ source }: { source: Source }) {
    const isSar = source.kind === 'sar';
    const Icon = isSar ? Radar : Satellite;
    const level = source.analysisLevel;
    const kindLabel = isSar
        ? 'Radar'
        : source.kind === 'context' || level === 'context'
          ? 'Context'
          : source.kind === 'archive' || level === 'archive'
            ? 'Archive'
            : level === 'regional'
            ? 'Regional'
            : 'Optical';

    return (
        <p
            className="flex items-center gap-1.5 text-[12px] leading-4 text-muted-foreground"
            data-testid={ `source-meta-${source.id}` }
        >
            <Icon className="size-3.5 shrink-0" strokeWidth={ 1.75 } />
            <span className="truncate">
                { source.availabilityStatus === 'gated' ? `${kindLabel} gated` : kindLabel }
                { source.provider ? ` · ${source.provider}` : '' }
            </span>
        </p>
    );
}
