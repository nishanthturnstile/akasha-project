import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { useCreateSeason, useFields } from '@/lib/queries';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function CreateSeasonDialogInner({ open, onOpenChange }: Props) {
  const [name, setName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [selectedFieldIds, setSelectedFieldIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const createSeason = useCreateSeason();
  const fieldsQ = useFields();

  const allFields = useMemo(() => fieldsQ.data ?? [], [fieldsQ.data]);

  const toggleField = (fieldId: string) => {
    setSelectedFieldIds((prev) =>
      prev.includes(fieldId) ? prev.filter((x) => x !== fieldId) : [...prev, fieldId],
    );
  };

  const selectAll = () => {
    setSelectedFieldIds(allFields.map((f) => f.id));
  };

  const canCreate = name.trim() !== '' && startDate !== '' && endDate !== '';

  const handleCreate = async () => {
    if (!canCreate) return;
    setError(null);
    try {
      await createSeason.mutateAsync({
        name: name.trim(),
        startDate: startDate || null,
        endDate: endDate || null,
      });
      onOpenChange(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create season';
      setError(message);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-popover bg-background/60 backdrop-blur-sm" />
        <Dialog.Content
          aria-label="Create season"
          className="glass fixed left-1/2 top-[18vh] z-popover w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-lg p-0"
        >
          <VisuallyHidden>
            <Dialog.Title>Create season</Dialog.Title>
            <Dialog.Description>
              Create a new season and assign fields to it.
            </Dialog.Description>
          </VisuallyHidden>

          <div className="flex items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
            <div className="min-w-0 text-center w-full">
              <div className="mx-auto w-max">
                <h3 className="text-base font-display font-semibold">Create season</h3>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                All data on the platform is filtered according to the selected season and the fields added to it.
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

            {fieldsQ.data && fieldsQ.data.length > 0 && (
              <div className="grid grid-cols-1 gap-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <input
                      id="selectAll"
                      type="checkbox"
                      checked={selectedFieldIds.length === allFields.length && allFields.length > 0}
                      onChange={selectAll}
                    />
                    <label htmlFor="selectAll" className="text-sm">
                      Select all fields: {allFields.length}
                    </label>
                  </div>
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

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex items-center justify-end gap-2 border-t border-border/60 pt-3">
              <Dialog.Close asChild>
                <button type="button" className="rounded-md border border-border px-3 py-1.5 text-sm">
                  Cancel
                </button>
              </Dialog.Close>
              <Button
                variant="primary"
                size="sm"
                onClick={handleCreate}
                disabled={!canCreate || createSeason.isPending}
                className={cn('gap-2', !canCreate && 'opacity-60')}
              >
                {createSeason.isPending ? 'Creating…' : 'Create season'}
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/**
 * Wrapper that resets form state whenever the dialog is opened.
 */
export default function CreateSeasonDialog({ open, onOpenChange }: Props) {
  // Use a key to force remount and reset all internal state when dialog opens
  return <CreateSeasonDialogInner key={open ? 'open' : 'closed'} open={open} onOpenChange={onOpenChange} />;
}
