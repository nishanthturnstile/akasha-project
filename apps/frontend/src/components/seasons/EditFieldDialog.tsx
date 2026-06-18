import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { X } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { MapLayerManager } from '@/components/map/MapLayerManager';
import { FieldBoundaryLayer } from '@/components/fields/FieldBoundaryLayer';
import { useConfig } from '@/lib/queries';
import { resolveBasemapConfig } from '@/map/basemap';
import type maplibregl from 'maplibre-gl';
import type { Field } from '@/types/api';

interface Props {
  field: Field;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave?: (fieldId: string, name?: string) => void;
  onDelete?: (fieldId: string) => void;
}

function polygonBounds(geometry: Field['geometry']): [[number, number], [number, number]] | null {
  if (!geometry) return null;
  const ring = geometry.type === 'Polygon'
    ? geometry.coordinates[0]
    : geometry.coordinates[0][0];
  if (!ring || ring.length === 0) return null;
  let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
  for (const [lng, lat] of ring) {
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }
  return [[minLng, minLat], [maxLng, maxLat]];
}

function polygonCenter(geometry: Field['geometry']): [number, number] {
  const bounds = polygonBounds(geometry);
  if (!bounds) return [78, 12];
  return [
    (bounds[0][0] + bounds[1][0]) / 2,
    (bounds[0][1] + bounds[1][1]) / 2,
  ];
}

export default function EditFieldDialog({
  field,
  open,
  onOpenChange,
  onSave,
  onDelete,
}: Props) {
  const [name, setName] = useState(field.name);
  const [error, setError] = useState<string | null>(null);
  const [miniMap, setMiniMap] = useState<maplibregl.Map | null>(null);

  const configQ = useConfig();

  const basemapResolution = useMemo(() => {
    if (!configQ.data) return null;
    try { return resolveBasemapConfig(configQ.data); }
    catch { return null; }
  }, [configQ.data]);

  const center = useMemo(() => polygonCenter(field.geometry), [field.geometry]);

  const handleMapReady = useCallback((map: maplibregl.Map) => {
    setMiniMap(map);
    const bounds = polygonBounds(field.geometry);
    if (bounds) {
      map.fitBounds(bounds, { padding: 24, maxZoom: 18 });
    }
  }, [field.geometry]);

  const handleSave = () => {
    if (!name.trim()) {
      setError('Field name is required');
      return;
    }
    setError(null);
    onSave?.(field.id, name.trim());
    onOpenChange(false);
  };

  const handleDelete = () => {
    onDelete?.(field.id);
    onOpenChange(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-popover bg-background/60 backdrop-blur-sm" />
        <Dialog.Content
          aria-label="Edit field"
          className="glass fixed left-1/2 top-[18vh] z-popover w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-lg p-0"
        >
          <VisuallyHidden>
            <Dialog.Title>Edit field</Dialog.Title>
            <Dialog.Description>Edit field name and view its boundary on the map.</Dialog.Description>
          </VisuallyHidden>

          <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
            <h3 className="text-base font-display font-semibold">Edit field</h3>
            <Dialog.Close asChild>
              <button aria-label="Close" className="rounded-md p-1 text-muted-foreground hover:bg-accent/40">
                <X className="size-4" />
              </button>
            </Dialog.Close>
          </div>

          <div className="p-4 space-y-4">
            {basemapResolution ? (
              <div className="relative h-[260px] w-full rounded-lg overflow-hidden border border-border">
                <MapLayerManager
                  basemap={basemapResolution}
                  center={center}
                  zoom={15}
                  scene={null}
                  opacity={1}
                  visible={true}
                  onBasemapError={() => {}}
                  onMapReady={handleMapReady}
                />
                {miniMap && (
                  <FieldBoundaryLayer
                    map={miniMap}
                    plot={null}
                    geometry={field.geometry}
                    featureId="edit-field-preview"
                    name={field.name}
                  />
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-[260px] rounded-lg border border-border bg-muted/30 text-sm text-muted-foreground">
                Loading map…
              </div>
            )}

            <div className="grid grid-cols-1 gap-3">
              <label className="text-sm">Field name</label>
              <input
                className="rounded-md border border-border bg-background px-3 py-2"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="text-sm text-muted-foreground">
              Area: {field.areaHa != null ? `${field.areaHa.toFixed(2)} ha` : '—'}
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex items-center justify-between gap-2 border-t border-border/60 pt-3">
              <div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDelete}
                  className="text-destructive border-destructive/40 hover:bg-destructive/10"
                >
                  Delete field
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Dialog.Close asChild>
                  <button type="button" className="rounded-md border border-border px-3 py-1.5 text-sm">
                    Cancel
                  </button>
                </Dialog.Close>
                <Button variant="primary" size="sm" onClick={handleSave}>
                  Save
                </Button>
              </div>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
