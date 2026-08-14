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
  const [userSelectedId, setUserSelectedId] = useState<string>('');

  const resolvedId = userSelectedId && vegData.find((vc) => vc.id === userSelectedId)
    ? userSelectedId
    : vegData.length > 0
      ? vegData[vegData.length - 1].id
      : '';
  const selectedCycle = vegData.find((vc) => vc.id === resolvedId) ?? null;

  const handleSave = useCallback(async (
    fieldId: string,
    name: string,
    geometry?: PlotGeometry,
    vegetationData?: VegetationCycleCreate[],
    groupId?: string | null,
    areaHa?: number | null,
  ) => {
    setSaving(true);
    try {
      await updateField.mutateAsync(
        {
          fieldId,
          payload: {
            name,
            ...(geometry ? { geometry } : {}),
            ...(vegetationData ? { vegetationData } : {}),
            ...(groupId !== undefined ? { groupId } : {}),
            ...(areaHa !== undefined ? { areaHa } : {}),
          },
        },
      );
      setSaving(false);
      setEditDialogOpen(false);
      setUserSelectedId('');
    } catch (err) {
      setSaving(false);
      throw err;
    }
  }, [updateField]);

  return (
    <>
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-3">
          <CropInfoCard
            testId="crop-info-card-veg-cycles"
            title="Veg cycles"
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
            {vegData.length === 0 ? (
              <p className="text-[13px] text-muted-foreground">No crop data added yet.</p>
            ) : (
              <div className="space-y-1.5">
                {vegData.map((vc) => (
                  <label
                    key={vc.id}
                    className={cn(
                      'flex items-start gap-2 rounded-md border p-2 cursor-pointer transition-colors',
                      resolvedId === vc.id
                        ? 'border-primary bg-primary/5'
                        : 'border-border/70 hover:bg-accent/10',
                    )}
                  >
                    <input
                      type="radio"
                      name="veg-cycle"
                      checked={resolvedId === vc.id}
                      onChange={() => setUserSelectedId(vc.id)}
                      className="mt-0.5 size-3.5 accent-primary shrink-0"
                    />
                    <div className="space-y-0.5 text-[12px] leading-4 text-foreground min-w-0">
                      <p className="font-medium truncate">{vc.cropName || '—'}</p>
                      {vc.varietyName && (
                        <p className="text-muted-foreground">Variety: {vc.varietyName}</p>
                      )}
                      {vc.sowingDate && (
                        <p className="text-muted-foreground">Sown: {vc.sowingDate}</p>
                      )}
                      {vc.seasonName && (
                        <p className="text-muted-foreground text-[10px]">{vc.seasonName}</p>
                      )}
                    </div>
                  </label>
                ))}
              </div>
            )}
          </CropInfoCard>

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
            {selectedCycle ? (
              <div className="space-y-1 text-[13px] leading-5 text-foreground">
                <p><span className="text-muted-foreground">Target:</span> {selectedCycle.targetYield != null ? `${selectedCycle.targetYield} t/ha` : '—'}</p>
                <p><span className="text-muted-foreground">Actual:</span> {selectedCycle.actualYield != null ? `${selectedCycle.actualYield} t/ha` : '—'}</p>
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
