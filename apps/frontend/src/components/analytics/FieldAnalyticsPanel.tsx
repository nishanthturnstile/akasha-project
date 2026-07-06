import { useEffect, useMemo, useState } from 'react';
import type { CloudMaskOptions, Field } from '@/types/api';
import CropTab from './CropTab';
import ChartTab from './ChartTab';
import { cn } from '@/lib/utils';

interface FieldAnalyticsPanelProps {
  field: Field;
  sourceId: string | undefined;
  indices: string[];
  selectedDate: string | null;
  displayMode?: string | null;
  cloudMask: CloudMaskOptions;
  periodFrom?: string | null;
  periodTo?: string | null;
}

type Section = 'crop' | 'chart' | 'activities';

const SECTIONS: { key: Section; label: string }[] = [
  { key: 'crop', label: 'Crop' },
  { key: 'chart', label: 'Chart' },
  { key: 'activities', label: 'Activities' },
];

function preferredIndex(displayMode: string | null | undefined, supported: string[]): string {
  const normalized = displayMode?.toUpperCase() ?? '';
  if (supported.includes(normalized)) return normalized;
  if (normalized === 'NDWI' && supported.includes('NDWI_GREEN_NIR')) return 'NDWI_GREEN_NIR';
  if (supported.includes('NDVI')) return 'NDVI';
  return supported[0] ?? 'NDVI';
}

export default function FieldAnalyticsPanel({
  field,
  sourceId,
  indices,
  selectedDate,
  displayMode,
  cloudMask,
  periodFrom,
  periodTo,
}: FieldAnalyticsPanelProps) {
  const [activeSection, setActiveSection] = useState<Section>('crop');
  const analyticsIndices = useMemo(() => indices.filter(Boolean), [indices]);
  const desiredIndex = preferredIndex(displayMode, analyticsIndices);
  const [activeIndex, setActiveIndex] = useState(desiredIndex);
  const activeIndexType = analyticsIndices.includes(activeIndex) ? activeIndex : desiredIndex;

  useEffect(() => {
    setActiveIndex(desiredIndex);
  }, [desiredIndex]);

  return (
    <div className="flex h-full flex-col min-h-0">
      {/* Horizontal section titles */}
      <div className="flex shrink-0 border-b border-border">
        {SECTIONS.map((s) => (
          <button
            key={s.key}
            type="button"
            onClick={() => setActiveSection(s.key)}
            className={cn(
              'flex-1 px-3 py-2 text-[12px] font-semibold uppercase tracking-wider transition-colors duration-fast',
              activeSection === s.key
                ? 'text-foreground border-b-2 border-primary bg-muted/20'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/10',
            )}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Section content */}
      <div className="flex-1 min-h-0 overflow-y-auto p-3">
        {activeSection === 'crop' && <CropTab field={field} />}
        {activeSection === 'chart' && (
          <ChartTab
            field={ field }
            sourceId={ sourceId }
            selectedDate={ selectedDate }
            indexType={ activeIndexType }
            indices={ analyticsIndices }
            onIndexTypeChange={ setActiveIndex }
            cloudMask={ cloudMask }
            periodFrom={ periodFrom }
            periodTo={ periodTo }
          />
        )}
        {activeSection === 'activities' && (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            Coming soon
          </div>
        )}
      </div>
    </div>
  );
}
