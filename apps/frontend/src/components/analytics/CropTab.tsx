import { Lock, Plus, Sprout } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useVegetationCycles } from '@/hooks/useVegetationCycles';

interface CropTabProps {
  fieldId: string;
}

export default function CropTab({ fieldId }: CropTabProps) {
  const { cycles, addCycle, updateCycle } = useVegetationCycles(fieldId);
  const [showYieldForm, setShowYieldForm] = useState(false);

  const seasonIds = Object.keys(cycles);
  const firstSeasonId = seasonIds.length > 0 ? seasonIds[0] : null;
  const currentCycles = firstSeasonId ? cycles[firstSeasonId] : [];
  const latestCycle = currentCycles.length > 0 ? currentCycles[currentCycles.length - 1] : null;

  const handleAddYield = () => {
    if (!firstSeasonId) return;
    addCycle(firstSeasonId);
    setShowYieldForm(true);
    // Scroll to the yield card after a tick so the DOM is updated
    setTimeout(() => {
      document.getElementById('yield-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 50);
  };

  const latestCycleIndex = currentCycles.length > 0 ? currentCycles.length - 1 : -1;

  return (
    <div className="grid grid-cols-3 gap-3">
      {/* Column 1 — under "Crop" header */}
      <div className="space-y-3">
        <CropInfoCard
          testId="crop-info-card-crop-rotation"
          title="Crop rotation"
          icon={<Sprout className="size-3.5 text-primary" strokeWidth={1.75} />}
        >
          {latestCycle ? (
            <div className="space-y-1 text-[11px] leading-5 text-foreground">
              <p><span className="text-muted-foreground">Crop:</span> {latestCycle.cropName || '—'}</p>
              <p><span className="text-muted-foreground">Planted:</span> {latestCycle.plantingDate || '—'}</p>
              <p><span className="text-muted-foreground">Harvest:</span> {latestCycle.harvestingDate || '—'}</p>
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground">No crop data added yet.</p>
          )}
        </CropInfoCard>

        <CropInfoCard
          testId="crop-info-card-sown-area"
          title="Sown area detected"
          locked
        >
          <p className="text-[11px] leading-4 text-muted-foreground">
            Sown-area detection is available on the Essential or Professional plan.
          </p>
        </CropInfoCard>
      </div>

      {/* Column 2 — under "Chart" header */}
      <div className="space-y-3">
        <CropInfoCard
          testId="crop-info-card-growth-stages"
          title="Growth stages"
        >
          <p className="text-[11px] leading-4 text-muted-foreground">
            Select a crop to view its growth stages.
          </p>
        </CropInfoCard>

        <CropInfoCard
          testId="crop-info-card-yield"
          title="Yield"
          icon={<Sprout className="size-3.5 text-primary" strokeWidth={1.75} />}
        >
          {latestCycle ? (
            <div className="space-y-1 text-[11px] leading-5 text-foreground">
              <p><span className="text-muted-foreground">Target:</span> {latestCycle.targetYield != null ? `${latestCycle.targetYield} t/ha` : '—'}</p>
              <p><span className="text-muted-foreground">Actual:</span> {latestCycle.actualYield != null ? `${latestCycle.actualYield} t/ha` : '—'}</p>
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground">No yield data recorded.</p>
          )}

          {showYieldForm && firstSeasonId && latestCycleIndex >= 0 && (
            <div className="mt-2 space-y-2 border-t border-border/60 pt-2">
              <div>
                <label className="text-[10px] font-medium text-muted-foreground">Crop name</label>
                <input
                  value={currentCycles[latestCycleIndex].cropName}
                  onChange={(e) => updateCycle(firstSeasonId, currentCycles[latestCycleIndex].id, 'cropName', e.target.value)}
                  className="w-full rounded border border-border/60 bg-background px-2 py-1 text-[11px] focus:border-primary focus:outline-none"
                  placeholder="Wheat, Rice..."
                />
              </div>
              <div>
                <label className="text-[10px] font-medium text-muted-foreground">Planting date</label>
                <input
                  type="date"
                  value={currentCycles[latestCycleIndex].plantingDate}
                  onChange={(e) => updateCycle(firstSeasonId, currentCycles[latestCycleIndex].id, 'plantingDate', e.target.value)}
                  className="w-full rounded border border-border/60 bg-background px-2 py-1 text-[11px] focus:border-primary focus:outline-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] font-medium text-muted-foreground">Target yield (t/ha)</label>
                  <input
                    type="number"
                    min={0}
                    step={0.01}
                    value={currentCycles[latestCycleIndex].targetYield ?? ''}
                    onChange={(e) => updateCycle(firstSeasonId, currentCycles[latestCycleIndex].id, 'targetYield', e.target.value ? Number(e.target.value) : null)}
                    className="w-full rounded border border-border/60 bg-background px-2 py-1 text-[11px] focus:border-primary focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-medium text-muted-foreground">Actual yield (t/ha)</label>
                  <input
                    type="number"
                    min={0}
                    step={0.01}
                    value={currentCycles[latestCycleIndex].actualYield ?? ''}
                    onChange={(e) => updateCycle(firstSeasonId, currentCycles[latestCycleIndex].id, 'actualYield', e.target.value ? Number(e.target.value) : null)}
                    className="w-full rounded border border-border/60 bg-background px-2 py-1 text-[11px] focus:border-primary focus:outline-none"
                  />
                </div>
              </div>
              <div>
                <label className="text-[10px] font-medium text-muted-foreground">Notes</label>
                <input
                  value={currentCycles[latestCycleIndex].notes}
                  onChange={(e) => updateCycle(firstSeasonId, currentCycles[latestCycleIndex].id, 'notes', e.target.value)}
                  className="w-full rounded border border-border/60 bg-background px-2 py-1 text-[11px] focus:border-primary focus:outline-none"
                  placeholder="Optional notes..."
                />
              </div>
              <div className="flex items-center gap-2">
                <Button type="button" size="sm" variant="primary" className="h-7 px-3 text-[11px]" onClick={() => setShowYieldForm(false)}>
                  Save
                </Button>
                <Button type="button" size="sm" variant="ghost" className="h-7 px-3 text-[11px]" onClick={() => setShowYieldForm(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {!showYieldForm && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-2 h-7 px-2 text-[11px]"
              onClick={handleAddYield}
              data-testid="crop-yield-add"
            >
              <Plus className="size-3" strokeWidth={1.75} /> Add
            </Button>
          )}
        </CropInfoCard>
      </div>

      {/* Column 3 — under "Activities" header */}
      <div className="space-y-3">
        <CropInfoCard
          testId="crop-info-card-current-risks"
          title="Risk information"
          locked
        >
          <p className="text-[11px] leading-4 text-muted-foreground">
            Risk diagnostics are available on the Essential or Professional plan.
          </p>
        </CropInfoCard>

        <CropInfoCard
          testId="crop-info-card-ndvi-split"
          title="NDVI value split"
          locked
        >
          <p className="text-[11px] leading-4 text-muted-foreground">
            Vegetation-class split is available on the Essential or Professional plan.
          </p>
        </CropInfoCard>
      </div>
    </div>
  );
}

function CropInfoCard({
  title,
  children,
  testId,
  icon,
  locked = false,
}: {
  title: string;
  children: React.ReactNode;
  testId: string;
  icon?: React.ReactNode;
  locked?: boolean;
}) {
  return (
    <div
      data-testid={testId}
      className={cn(
        'rounded-md border border-border/70 bg-background/40 p-2.5',
        locked && 'opacity-80',
      )}
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          {icon}
          <p className="text-[12px] font-medium text-foreground">{title}</p>
        </div>
        {locked && (
          <Lock
            className="size-3 text-muted-foreground"
            strokeWidth={1.75}
            aria-label="Plan-gated feature"
          />
        )}
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}
