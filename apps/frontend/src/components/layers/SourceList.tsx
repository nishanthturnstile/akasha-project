import type { Source } from '@/types/api';
import { SourceCard } from './SourceCard';

interface SourceListProps {
    sources: Source[] | undefined;
    activeSourceId: string | undefined;
    selectedDate: string | null;
    displayMode: string;
    visible: boolean;
    opacity: number;
    onSelectSource: (sourceId: string) => void;
    onDisplayModeChange: (mode: string) => void;
    onVisibleChange: (visible: boolean) => void;
    onOpacityChange: (opacity: number) => void;
    onPrefetchSource?: (sourceId: string) => void;
}

/** Renders `/api/sources` as a vertical stack of single-select source cards. */
export function SourceList({
    sources,
    activeSourceId,
    selectedDate,
    displayMode,
    visible,
    opacity,
    onSelectSource,
    onDisplayModeChange,
    onVisibleChange,
    onOpacityChange,
    onPrefetchSource,
}: SourceListProps) {
    if (!sources || sources.length === 0) {
        return (
            <p className="px-1 text-[13px] text-muted-foreground" data-testid="source-list-empty">
                No imagery sources available.
            </p>
        );
    }

    return (
        <div
            role="radiogroup"
            aria-label="Imagery source"
            className="flex flex-col gap-2"
            data-testid="source-list"
        >
            { sources.map((source) => {
                const active = source.id === activeSourceId;
                return (
                    <SourceCard
                        key={ source.id }
                        source={ source }
                        active={ active }
                        selectedDate={ active ? selectedDate : null }
                        displayMode={ displayMode }
                        visible={ visible }
                        opacity={ opacity }
                        onSelect={ () => onSelectSource(source.id) }
                        onDisplayModeChange={ onDisplayModeChange }
                        onVisibleChange={ onVisibleChange }
                        onOpacityChange={ onOpacityChange }
                        onPrefetch={ onPrefetchSource ? () => onPrefetchSource(source.id) : undefined }
                    />
                );
            }) }
        </div>
    );
}
