import { useState } from 'react';
import { ChevronLeft, Info, Layers } from 'lucide-react';
import type { SceneDate, Source } from '@/types/api';
import { Separator } from '@/components/ui/separator';
import { SourceSelector } from './SourceSelector';
import { DateList } from './DateList';
import { OpacitySlider } from './OpacitySlider';
import { VisibilityToggle } from './VisibilityToggle';

interface LayerPanelProps {
  sources: Source[] | undefined;
  selectedSourceId: string | undefined;
  onSourceChange: (sourceId: string) => void;
  dates: SceneDate[] | undefined;
  datesLoading: boolean;
  datesError: string | null;
  onDatesRetry: () => void;
  selectedDate: string | null;
  onDateSelect: (acquisitionDate: string) => void;
  visible: boolean;
  onVisibleChange: (visible: boolean) => void;
  opacity: number;
  onOpacityChange: (opacity: number) => void;
  /** Set when no date meets the usability threshold. */
  marginalNote: string | null;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
      {children}
    </h3>
  );
}

export function LayerPanel(props: LayerPanelProps) {
  const {
    sources,
    selectedSourceId,
    onSourceChange,
    dates,
    datesLoading,
    datesError,
    onDatesRetry,
    selectedDate,
    onDateSelect,
    visible,
    onVisibleChange,
    opacity,
    onOpacityChange,
    marginalNote,
  } = props;
  const [collapsed, setCollapsed] = useState(false);

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        data-testid="layer-panel-expand"
        className="glass flex h-10 items-center gap-2 rounded-pill px-3.5 text-[13px] font-medium text-foreground transition-transform duration-fast ease-standard hover:scale-[1.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Layers className="size-4" strokeWidth={1.75} />
        Layers
      </button>
    );
  }

  return (
    <section
      data-testid="layer-panel"
      className="glass w-[320px] max-w-[88vw] animate-panel-in overflow-hidden"
      aria-label="Layer controls"
    >
      <header className="contour flex items-center justify-between gap-2 px-4 py-3">
        <div className="flex items-center gap-2">
          <Layers className="size-4 text-primary" strokeWidth={1.75} />
          <h2 className="font-display text-base font-semibold tracking-[-0.01em]">Layers</h2>
        </div>
        <button
          type="button"
          aria-label="Collapse layer panel"
          data-testid="layer-panel-collapse"
          onClick={() => setCollapsed(true)}
          className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors duration-fast hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ChevronLeft className="size-4" strokeWidth={1.75} />
        </button>
      </header>
      <Separator />

      <div className="flex flex-col gap-4 p-4">
        <div>
          <SectionLabel>Source</SectionLabel>
          {sources && sources.length > 0 ? (
            <SourceSelector
              sources={sources}
              value={selectedSourceId}
              onChange={onSourceChange}
            />
          ) : (
            <p className="text-[13px] text-muted-foreground">No sources available.</p>
          )}
        </div>

        <Separator />

        <div>
          <SectionLabel>Acquisition date</SectionLabel>
          {marginalNote && (
            <div
              className="mb-2 flex items-start gap-2 rounded-md border border-warning/30 bg-warning/10 px-2.5 py-2 text-[12px] text-warning"
              data-testid="marginal-note"
            >
              <Info className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.75} />
              <span>{marginalNote}</span>
            </div>
          )}
          <DateList
            dates={dates}
            selectedDate={selectedDate}
            onSelect={onDateSelect}
            loading={datesLoading}
            error={datesError}
            onRetry={onDatesRetry}
          />
        </div>

        <Separator />

        <div className="flex flex-col gap-3">
          <VisibilityToggle checked={visible} onCheckedChange={onVisibleChange} />
          <OpacitySlider value={opacity} onChange={onOpacityChange} disabled={!visible} />
        </div>
      </div>
    </section>
  );
}
