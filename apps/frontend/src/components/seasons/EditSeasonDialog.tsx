import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { Field, Season } from '@/types/api';

interface Props {
  season: Season;
  allFields: Field[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave?: (seasonId: string, payload: {
    name: string;
    startDate: string | null;
    endDate: string | null;
    fieldIds: string[];
  }) => void;
}

export default function EditSeasonDialog({
  season,
  allFields,
  open,
  onOpenChange,
  onSave,
}: Props) {
  const [name, setName] = useState(season.name);
  const [startDate, setStartDate] = useState(season.startDate ?? '');
  const [endDate, setEndDate] = useState(season.endDate ?? '');
  const [error, setError] = useState<string | null>(null);

  const seasonFieldIds = useMemo(
    () => allFields.filter((f) => f.seasonIds?.includes(season.id)).map((f) => f.id),
    [allFields, season.id],
  );
  const [selectedFieldIds, setSelectedFieldIds] = useState<string[]>(seasonFieldIds);

  const isAllSelected = selectedFieldIds.length === allFields.length && allFields.length > 0;
  const isIndeterminate = selectedFieldIds.length > 0 && selectedFieldIds.length < allFields.length;

  const toggleField = (fieldId: string) => {
    setSelectedFieldIds((prev) =>
      prev.includes(fieldId) ? prev.filter((x) => x !== fieldId) : [...prev, fieldId],
    );
  };

  const toggleAll = () => {
    if (isAllSelected) {
      setSelectedFieldIds([]);
    } else {
      setSelectedFieldIds(allFields.map((f) => f.id));
    }
  };

  const handleSave = () => {
    if (!name.trim()) {
      setError('Season name is required');
      return;
    }
    setError(null);
    onSave?.(season.id, {
      name: name.trim(),
      startDate: startDate || null,
      endDate: endDate || null,
      fieldIds: selectedFieldIds,
    });
    onOpenChange(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-popover bg-background/60 backdrop-blur-sm" />
        <Dialog.Content
          aria-label="Edit season"
          className="glass fixed left-1/2 top-[12vh] z-popover w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-lg p-0"
        >
          <VisuallyHidden>
            <Dialog.Title>Edit season</Dialog.Title>
            <Dialog.Description>Edit season details and select fields for the season.</Dialog.Description>
          </VisuallyHidden>

          <div className="flex items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
            <div className="min-w-0 text-center w-full">
              <div className="mx-auto w-max">
                <h3 className="text-base font-display font-semibold">Edit season</h3>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Update season details or select the fields that belong to it.
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

            {allFields.length > 0 && (
              <div className="grid grid-cols-1 gap-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <input
                      id="editSelectAll"
                      type="checkbox"
                      checked={isAllSelected}
                      ref={(el) => { if (el) el.indeterminate = isIndeterminate; }}
                      onChange={toggleAll}
                    />
                    <label htmlFor="editSelectAll" className="text-sm">
                      Select all fields ({allFields.length})
                    </label>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {selectedFieldIds.length} selected
                  </span>
                </div>

                <ScrollArea className="max-h-48 pr-2">
                  <div className="space-y-2">
                    {allFields.map((f) => (
                      <div
                        key={f.id}
                        className="flex items-center justify-between rounded-lg border border-border/70 bg-card/35 px-3 py-2"
                      >
                        <div className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={selectedFieldIds.includes(f.id)}
                            onChange={() => toggleField(f.id)}
                          />
                          <div className="text-sm">{f.name}</div>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {f.areaHa != null ? `${f.areaHa.toFixed(2)} ha` : '—'}
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            )}

            {allFields.length === 0 && (
              <p className="text-sm text-muted-foreground py-2">No fields available.</p>
            )}

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
  );
}
