import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { Pencil, Plus, Trash2, X } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import { ScrollArea } from '@/components/ui/scroll-area';
import { GeometryPreview } from '@/lib/geometry-preview';
import { cn } from '@/lib/utils';
import type { Field, Season } from '@/types/api';
import EditFieldDialog from './EditFieldDialog';

interface Props {
  season: Season;
  fields: Field[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave?: (seasonId: string, payload: { name: string; startDate: string | null; endDate: string | null }) => void;
  onDeleteField?: (fieldId: string) => void;
  onAddField?: () => void;
}

export default function EditSeasonDialog({
  season,
  fields,
  open,
  onOpenChange,
  onSave,
  onDeleteField,
  onAddField,
}: Props) {
  const [name, setName] = useState(season.name);
  const [startDate, setStartDate] = useState(season.startDate ?? '');
  const [endDate, setEndDate] = useState(season.endDate ?? '');
  const [error, setError] = useState<string | null>(null);
  const [editingField, setEditingField] = useState<Field | null>(null);

  const handleSave = () => {
    if (!name.trim()) {
      setError('Season name is required');
      return;
    }
    setError(null);
    onSave?.(season.id, { name: name.trim(), startDate: startDate || null, endDate: endDate || null });
    onOpenChange(false);
  };

  const handleFieldDelete = (fieldId: string) => {
    onDeleteField?.(fieldId);
  };

  return (
    <>
      <Dialog.Root open={open} onOpenChange={onOpenChange}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-popover bg-background/60 backdrop-blur-sm" />
          <Dialog.Content
            aria-label="Edit season"
            className="glass fixed left-1/2 top-[12vh] z-popover w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-lg p-0"
          >
            <VisuallyHidden>
              <Dialog.Title>Edit season</Dialog.Title>
              <Dialog.Description>Edit season details and manage its fields.</Dialog.Description>
            </VisuallyHidden>

            <div className="flex items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
              <div className="min-w-0 text-center w-full">
                <div className="mx-auto w-max">
                  <h3 className="text-base font-display font-semibold">Edit season</h3>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Update season details or manage fields.
                </p>
              </div>
              <Dialog.Close asChild>
                <button aria-label="Close" className="rounded-md p-1 text-muted-foreground hover:bg-accent/40">
                  <X className="size-4" />
                </button>
              </Dialog.Close>
            </div>

            <div className="p-4 space-y-4">
              <div className="grid grid-cols-1 gap-3">
                <label className="text-sm">Season name</label>
                <input
                  className="rounded-md border border-border bg-background px-3 py-2"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm">Start date</label>
                  <DatePicker
                    value={startDate}
                    onChange={setStartDate}
                    placeholder="Start Date"
                  />
                </div>
                <div>
                  <label className="text-sm">End date</label>
                  <DatePicker
                    value={endDate}
                    onChange={setEndDate}
                    placeholder="End Date"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">
                    Fields ({fields.length})
                  </label>
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1"
                    onClick={onAddField}
                  >
                    <Plus className="size-3" />
                    Add field
                  </Button>
                </div>

                {fields.length > 0 ? (
                  <ScrollArea className="max-h-56 pr-2">
                    <div className="space-y-2">
                      {fields.map((f) => (
                        <div
                          key={f.id}
                          className="flex items-center gap-3 rounded-lg border border-border/70 bg-card/35 px-3 py-2"
                        >
                          <GeometryPreview
                            geometry={f.geometry}
                            width={48}
                            height={48}
                            className="shrink-0 rounded border border-border/50"
                          />
                          <div className="min-w-0 flex-1">
                            <div className="text-sm truncate font-medium">{f.name}</div>
                            <div className="text-xs text-muted-foreground">
                              {f.areaHa != null ? `${f.areaHa.toFixed(2)} ha` : '—'}
                            </div>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              onClick={() => setEditingField(f)}
                              className={cn(
                                'rounded p-1 text-muted-foreground hover:bg-accent/40 hover:text-foreground',
                              )}
                              aria-label={`Edit field ${f.name}`}
                            >
                              <Pencil className="size-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleFieldDelete(f.id)}
                              className="rounded p-1 text-muted-foreground hover:bg-accent/40 hover:text-destructive"
                              aria-label={`Delete field ${f.name}`}
                            >
                              <Trash2 className="size-3.5" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                ) : (
                  <p className="text-sm text-muted-foreground py-2">
                    No fields assigned to this season.
                  </p>
                )}
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <div className="flex items-center justify-end gap-2 border-t border-border/60 pt-3">
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
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {editingField && (
        <EditFieldDialog
          field={editingField}
          open={!!editingField}
          onOpenChange={(open) => { if (!open) setEditingField(null); }}
          onSave={(fieldId) => {
            handleFieldDelete(fieldId);
            setEditingField(null);
          }}
          onDelete={handleFieldDelete}
        />
      )}
    </>
  );
}
