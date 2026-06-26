import { Lock, Plus, Sprout } from 'lucide-react';
import { useCallback, useState } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import EditFieldDialog from '@/components/seasons/EditFieldDialog';
import { useUpdateField } from '@/lib/queries';
import type { Field, PlotGeometry, VegetationCycleCreate } from '@/types/api';

interface CropTabProps {
  field: Field;
}

export default function CropTab({ field }: CropTabProps) {
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const updateField = useUpdateField();
  const [saving, setSaving] = useState(false);

  const vegData = field.vegetationData ?? [];
  const latestCycle = vegData.length > 0 ? vegData[vegData.length - 1] : null;

  const handleSave = useCallback((
    fieldId: string,
    name: string,
    geometry?: PlotGeometry,
    vegetationData?: VegetationCycleCreate[],
    groupId?: string | null,
  ) => {
    setSaving(true);
    updateField.mutate(
      {
        fieldId,
        payload: {
          name,
          ...(geometry ? { geometry } : {}),
          ...(vegetationData ? { vegetationData } : {}),
          ...(groupId !== undefined ? { groupId } : {}),
        },
      },
      {
        onSuccess: () => {
          setSaving(false);
          setEditDialogOpen(false);
        },
        onError: () => {
          setSaving(false);
        },
      },
    );
  }, [updateField]);

  return (
    <>
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-3">
          <CropInfoCard
            testId="crop-info-card-crop-rotation"
            title="Crop rotation"
            icon={<Sprout className="size-3.5 text-primary" strokeWidth={1.75} />}
            action={
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-6 px-2 text-[11px]"
                onClick={() => setEditDialogOpen(true)}
                data-testid="crop-rotation-add"
              >
                <Plus className="size-3" strokeWidth={1.75} /> Add
              </Button>
            }
          >
            {latestCycle ? (
              <div className="space-y-1 text-[13px] leading-5 text-foreground">
                <p><span className="text-muted-foreground">Crop:</span> {latestCycle.cropName || '—'}</p>
                <p><span className="text-muted-foreground">Variety:</span> {latestCycle.varietyName || '—'}</p>
                <p><span className="text-muted-foreground">Planted:</span> {latestCycle.sowingDate || '—'}</p>
              </div>
            ) : (
              <p className="text-[13px] text-muted-foreground">No crop data added yet.</p>
            )}
          </CropInfoCard>

          {vegData.length > 0 && (
            <div className="rounded-md border border-border/70 bg-background/40 p-2.5">
              <p className="text-[11px] font-medium text-muted-foreground mb-1.5">All cycles</p>
              <div className="space-y-1.5">
                {vegData.map((vc) => (
                  <div key={vc.id} className="flex items-center gap-2 text-[12px] text-foreground">
                    <Sprout className="size-3 text-emerald-500 shrink-0" />
                    <span className="truncate">{vc.cropName || '—'}</span>
                    {vc.seasonName && (
                      <span className="text-muted-foreground text-[10px]">({vc.seasonName})</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <CropInfoCard
            testId="crop-info-card-sown-area"
            title="Sown area detected"
            locked
          >
            <p className="text-[13px] leading-4 text-muted-foreground">
              Sown-area detection is available on the Essential or Professional plan.
            </p>
          </CropInfoCard>
        </div>

        <div className="space-y-3">
          <CropInfoCard
            testId="crop-info-card-growth-stages"
            title="Growth stages"
          >
            <p className="text-[13px] leading-4 text-muted-foreground">
              Select a crop to view its growth stages.
            </p>
          </CropInfoCard>

          <CropInfoCard
            testId="crop-info-card-yield"
            title="Yield"
            icon={<Sprout className="size-3.5 text-primary" strokeWidth={1.75} />}
            action={
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-6 px-2 text-[11px]"
                onClick={() => setEditDialogOpen(true)}
                data-testid="crop-yield-add"
              >
                <Plus className="size-3" strokeWidth={1.75} /> Add
              </Button>
            }
          >
            {latestCycle ? (
              <div className="space-y-1 text-[13px] leading-5 text-foreground">
                <p><span className="text-muted-foreground">Target:</span> {latestCycle.targetYield != null ? `${latestCycle.targetYield} t/ha` : '—'}</p>
                <p><span className="text-muted-foreground">Actual:</span> {latestCycle.actualYield != null ? `${latestCycle.actualYield} t/ha` : '—'}</p>
              </div>
            ) : (
              <p className="text-[13px] text-muted-foreground">No yield data recorded.</p>
            )}
          </CropInfoCard>
        </div>

        <div className="space-y-3">
          <CropInfoCard
            testId="crop-info-card-current-risks"
            title="Risk information"
            locked
          >
            <p className="text-[13px] leading-4 text-muted-foreground">
              Risk diagnostics are available on the Essential or Professional plan.
            </p>
          </CropInfoCard>

          <CropInfoCard
            testId="crop-info-card-ndvi-split"
            title="NDVI value split"
            locked
          >
            <p className="text-[13px] leading-4 text-muted-foreground">
              Vegetation-class split is available on the Essential or Professional plan.
            </p>
          </CropInfoCard>
        </div>
      </div>

      <EditFieldDialog
        field={field}
        open={editDialogOpen}
        onOpenChange={setEditDialogOpen}
        onSave={handleSave}
        saving={saving}
      />
    </>
  );
}

function CropInfoCard({
  title,
  children,
  testId,
  icon,
  locked = false,
  action,
}: {
  title: string;
  children: React.ReactNode;
  testId: string;
  icon?: React.ReactNode;
  locked?: boolean;
  action?: React.ReactNode;
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
          <p className="text-[13px] font-medium text-foreground">{title}</p>
        </div>
        <div className="flex items-center gap-2">
          {action}
          {locked && (
            <Lock
              className="size-3 text-muted-foreground"
              strokeWidth={1.75}
              aria-label="Plan-gated feature"
            />
          )}
        </div>
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}
