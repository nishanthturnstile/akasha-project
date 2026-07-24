import { MapPin, Plus, Search, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DiscoveryBrowser } from '@/components/discovery/DiscoveryBrowser';
import { FieldCreateOptionsDialog } from '@/components/fields/FieldCreateOptionsDialog';
import { GeometryPreview } from '@/lib/geometry-preview';
import { useConfig, useFields } from '@/lib/queries';
import { useMapView } from '@/state/useMapView';
import type { PlotGeometry } from '@/types/api';

interface Props {
  onClose: () => void;
  seasonId: string | null;
}

export function FieldThumbnail({ geometry, size = 48 }: { geometry: PlotGeometry; size?: number }) {
  return (
    <GeometryPreview
      geometry={geometry}
      width={size}
      height={size}
      className="shrink-0 rounded-lg border border-primary/15 bg-primary/5 p-1.5"
    />
  );
}

const LAST_FIELD_KEY = 'akasha.lastFieldPerSeason';

export function getLastFieldPerSeason(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(LAST_FIELD_KEY) ?? '{}') as Record<string, string>;
  } catch {
    return {};
  }
}

export function setLastFieldForSeason(seasonId: string, fieldId: string) {
  try {
    const map = getLastFieldPerSeason();
    map[seasonId] = fieldId;
    localStorage.setItem(LAST_FIELD_KEY, JSON.stringify(map));
  } catch {
    // Storage unavailable.
  }
}

function LegacyFieldList({ seasonId }: { seasonId: string }) {
  const fieldsQ = useFields();
  const view = useMapView();
  const [query, setQuery] = useState('');
  const fields = useMemo(() => (fieldsQ.data ?? []).filter((field) =>
    field.seasonIds.includes(seasonId)
    && field.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())), [
    fieldsQ.data,
    query,
    seasonId,
  ]);
  return (
    <div className="min-h-0 flex-1 overflow-auto p-4">
      <label className="relative mb-3 block">
        <span className="sr-only">Search field names</span>
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="h-9 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm"
          placeholder="Search field names"
        />
      </label>
      <div className="space-y-2">
        {fields.map((field) => (
          <article key={field.id} className="flex items-center gap-3 rounded-lg border border-border p-3">
            <FieldThumbnail geometry={field.geometry} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">{field.name}</p>
              <p className="text-xs text-muted-foreground">
                {field.areaHa == null ? '—' : `${field.areaHa.toFixed(2)} ha`}
              </p>
            </div>
            <button
              type="button"
              aria-label={`Find ${field.name} on map`}
              className="rounded-md border border-border p-2"
              onClick={() => {
                view.setSelectedPlotId(field.id);
                view.setFocusNonce(view.focusNonce + 1);
              }}
            >
              <MapPin className="size-4" />
            </button>
          </article>
        ))}
      </div>
    </div>
  );
}

export default function GlobalViewPanel({ onClose, seasonId }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('discoveryTarget') === 'scouting' ? 'scouting' : 'monitoring';
  const [addFieldOpen, setAddFieldOpen] = useState(false);
  const configQ = useConfig();
  const discoveryEnabled = configQ.data?.features?.fieldDiscoveryEnabled !== false;

  return (
    <>
      <aside className="flex h-full w-96 max-w-[42vw] flex-col border-l border-border bg-muted/30">
        <header className="border-b border-border/60 px-4 py-4">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="font-display text-base font-semibold">Global View</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Discover fields and scouting work without leaving the map.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close global view"
              className="rounded-md p-1 text-muted-foreground hover:bg-accent"
            >
              <X className="size-4" />
            </button>
          </div>
          {discoveryEnabled && <div className="mt-3 grid grid-cols-2 rounded-lg bg-muted p-1" role="tablist" aria-label="Discovery target">
            {(['monitoring', 'scouting'] as const).map((value) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={tab === value}
                className={tab === value
                  ? 'rounded-md bg-background px-3 py-1.5 text-xs font-semibold shadow-sm'
                  : 'rounded-md px-3 py-1.5 text-xs text-muted-foreground'}
                onClick={() => setSearchParams((current) => {
                  const next = new URLSearchParams(current);
                  if (value === 'scouting') next.set('discoveryTarget', 'scouting');
                  else next.delete('discoveryTarget');
                  return next;
                }, { replace: true })}
              >
                {value === 'monitoring' ? 'Monitoring' : 'Scouting'}
              </button>
            ))}
          </div>}
        </header>

        {seasonId && discoveryEnabled ? (
          <DiscoveryBrowser key={`${tab}:${seasonId}`} target={tab} seasonId={seasonId} />
        ) : seasonId ? (
          <LegacyFieldList seasonId={seasonId} />
        ) : (
          <div className="m-4 rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            Select a season to discover fields.
          </div>
        )}

        {tab === 'monitoring' && (
          <div className="shrink-0 border-t border-border/60 px-4 py-3">
            <button
              type="button"
              onClick={() => setAddFieldOpen(true)}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground"
            >
              <Plus className="size-4" />
              Add field
            </button>
          </div>
        )}
      </aside>
      <FieldCreateOptionsDialog
        open={addFieldOpen}
        onOpenChange={setAddFieldOpen}
        defaultSeasonId={seasonId}
      />
    </>
  );
}
