import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { Search, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
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
    () => season.fieldIds.filter((fi) => fi.isMapped).map((fi) => fi.id),
    [season.fieldIds],
  );
  const [selectedFieldIds, setSelectedFieldIds] = useState<string[]>([]);

  useEffect(() => {
    setSelectedFieldIds(seasonFieldIds);
  }, [seasonFieldIds]);

  const [fieldTab, setFieldTab] = useState<'list' | 'added' | 'removed'>('list');
  const [listSearch, setListSearch] = useState('');
  const [addedSearch, setAddedSearch] = useState('');
  const [removedSearch, setRemovedSearch] = useState('');

  const removedFieldIds = useMemo(
    () => seasonFieldIds.filter((id) => !selectedFieldIds.includes(id)),
    [seasonFieldIds, selectedFieldIds],
  );

  const toggleField = (fieldId: string) => {
    const fieldEntry = season.fieldIds.find((fi) => fi.id === fieldId);
    if (fieldEntry && fieldEntry.isMapped && !fieldEntry.canRemove) return;
    setSelectedFieldIds((prev) =>
      prev.includes(fieldId) ? prev.filter((x) => x !== fieldId) : [...prev, fieldId],
    );
  };

  const filteredAllFields = useMemo(() => {
    if (!listSearch.trim()) return allFields;
    const q = listSearch.trim().toLocaleLowerCase();
    return allFields.filter((f) => f.name.toLocaleLowerCase().includes(q));
  }, [allFields, listSearch]);

  const filteredAddedFields = useMemo(() => {
    const added = allFields.filter((f) => selectedFieldIds.includes(f.id));
    if (!addedSearch.trim()) return added;
    const q = addedSearch.trim().toLocaleLowerCase();
    return added.filter((f) => f.name.toLocaleLowerCase().includes(q));
  }, [allFields, selectedFieldIds, addedSearch]);

  const filteredRemovedFields = useMemo(() => {
    const removed = allFields.filter((f) => removedFieldIds.includes(f.id));
    if (!removedSearch.trim()) return removed;
    const q = removedSearch.trim().toLocaleLowerCase();
    return removed.filter((f) => f.name.toLocaleLowerCase().includes(q));
  }, [allFields, removedFieldIds, removedSearch]);

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
          onInteractOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
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
                <div className="flex items-center border-b border-border/60">
                  <button
                    type="button"
                    onClick={() => setFieldTab('list')}
                    className={cn(
                      'flex-1 pb-2 text-sm font-medium border-b-2 transition-colors',
                      fieldTab === 'list'
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground',
                    )}
                  >
                    Field List
                  </button>
                  <button
                    type="button"
                    onClick={() => setFieldTab('added')}
                    className={cn(
                      'flex-1 pb-2 text-sm font-medium border-b-2 transition-colors',
                      fieldTab === 'added'
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground',
                    )}
                  >
                    Added Fields ({selectedFieldIds.length})
                  </button>
                  <button
                    type="button"
                    onClick={() => setFieldTab('removed')}
                    className={cn(
                      'flex-1 pb-2 text-sm font-medium border-b-2 transition-colors',
                      fieldTab === 'removed'
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground',
                    )}
                  >
                    Removed Fields ({removedFieldIds.length})
                  </button>
                </div>

                <label className="relative block">
                  <span className="sr-only">Search fields</span>
                  <Search
                    className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
                    strokeWidth={1.75}
                  />
                  <input
                    type="search"
                    value={fieldTab === 'list' ? listSearch : fieldTab === 'added' ? addedSearch : removedSearch}
                    onChange={(e) => {
                      if (fieldTab === 'list') setListSearch(e.target.value);
                      else if (fieldTab === 'added') setAddedSearch(e.target.value);
                      else setRemovedSearch(e.target.value);
                    }}
                    placeholder={`Search ${fieldTab === 'list' ? 'all' : fieldTab === 'added' ? 'added' : 'removed'} fields\u2026`}
                    className="h-8 w-full rounded-md border border-input bg-background/55 pl-8 pr-3 text-[13px] text-foreground shadow-e1 transition-colors duration-fast placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </label>

                <ScrollArea className="max-h-48 pr-2">
                  <div className="space-y-2">
                    {fieldTab === 'list' && filteredAllFields.map((f) => {
                      const fieldEntry = season.fieldIds.find((fi) => fi.id === f.id);
                      const isMandatory = fieldEntry ? (!fieldEntry.canRemove && fieldEntry.isMapped) : false;
                      return (
                        <div
                          key={f.id}
                          className="flex items-center justify-between rounded-lg border border-border/70 bg-card/35 px-3 py-2"
                        >
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={selectedFieldIds.includes(f.id)}
                              disabled={isMandatory}
                              onChange={() => toggleField(f.id)}
                            />
                            <div className={cn('text-sm', isMandatory && 'text-muted-foreground')}>
                              {f.name}
                            </div>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {f.areaHa != null ? `${f.areaHa.toFixed(2)} ha` : '—'}
                          </div>
                        </div>
                      );
                    })}
                    {fieldTab === 'added' && filteredAddedFields.map((f) => (
                      <div
                        key={f.id}
                        className="flex items-center justify-between rounded-lg border border-border/70 bg-card/35 px-3 py-2"
                      >
                        <div className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={true}
                            onChange={() => toggleField(f.id)}
                          />
                          <div className="text-sm">{f.name}</div>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {f.areaHa != null ? `${f.areaHa.toFixed(2)} ha` : '—'}
                        </div>
                      </div>
                    ))}
                    {fieldTab === 'removed' && filteredRemovedFields.map((f) => {
                      const isMandatory = false;
                      return (
                        <div
                          key={f.id}
                          className="flex items-center justify-between rounded-lg border border-border/70 bg-card/35 px-3 py-2"
                        >
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={selectedFieldIds.includes(f.id)}
                              disabled={isMandatory}
                              onChange={() => toggleField(f.id)}
                            />
                            <div className="text-sm">{f.name}</div>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {f.areaHa != null ? `${f.areaHa.toFixed(2)} ha` : '—'}
                          </div>
                        </div>
                      );
                    })}
                    {fieldTab === 'list' && filteredAllFields.length === 0 && (
                      <p className="text-sm text-muted-foreground py-2 text-center">No fields match your search.</p>
                    )}
                    {fieldTab === 'added' && filteredAddedFields.length === 0 && (
                      <p className="text-sm text-muted-foreground py-2 text-center">No fields added yet.</p>
                    )}
                    {fieldTab === 'removed' && filteredRemovedFields.length === 0 && (
                      <p className="text-sm text-muted-foreground py-2 text-center">No fields removed.</p>
                    )}
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
