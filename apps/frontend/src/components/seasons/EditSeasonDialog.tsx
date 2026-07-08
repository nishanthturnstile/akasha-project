import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { ChevronDown, Search, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { DatePicker } from '@/components/ui/date-picker';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/ui/select';
import { usePredefinedSeasons } from '@/lib/queries';
import {
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogRoot,
  AlertDialogTitle,
  AlertDialogFooter,
} from '@/components/ui/alert-dialog';
import type { Field, Season } from '@/types/api';

const CUSTOM = '__custom__';

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
  const [confirmClose, setConfirmClose] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string>(CUSTOM);
  const [customNameDraft, setCustomNameDraft] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const predefinedQ = usePredefinedSeasons();

  const predefinedMap = useMemo(() => {
    const map = new Map<string, NonNullable<typeof predefinedQ.data>[number]>();
    for (const s of predefinedQ.data ?? []) {
      map.set(s.seasonName, s);
    }
    return map;
  }, [predefinedQ.data]);

  const isCustom = selectedKey === CUSTOM;

  const seasonFieldIds = useMemo(
    () => season.fieldIds.filter((fi) => fi.isMapped).map((fi) => fi.id),
    [season.fieldIds],
  );
  const [selectedFieldIds, setSelectedFieldIds] = useState<string[]>([]);

  // Reset form to season props when dialog opens
  useEffect(() => {
    if (!open) return;
    const fieldIds = season.fieldIds.filter((fi) => fi.isMapped).map((fi) => fi.id);
    setName(season.name);
    setStartDate(season.startDate ?? '');
    setEndDate(season.endDate ?? '');
    setSelectedFieldIds(fieldIds);
    setError(null);
    setConfirmClose(false);
    const has = predefinedMap.has(season.name);
    setSelectedKey(has ? season.name : CUSTOM);
    setCustomNameDraft(has ? '' : season.name);
    setDropdownOpen(false);
    setFieldTab('list');
    setListSearch('');
    setAddedSearch('');
    setRemovedSearch('');
  }, [open, season, seasonFieldIds, predefinedMap]);

  useEffect(() => {
    if (!isCustom) return;
    const id = setTimeout(() => inputRef.current?.focus(), 100);
    return () => clearTimeout(id);
  }, [isCustom]);

  const handleSeasonSelect = (key: string) => {
    if (isCustom && key !== CUSTOM) {
      setCustomNameDraft(name);
    }
    setSelectedKey(key);
    setError(null);
    if (key === CUSTOM) {
      setName(customNameDraft);
      const y = new Date().getFullYear();
      setStartDate(`${y}-01-01`);
      setEndDate(`${y}-12-31`);
    } else if (key !== CUSTOM) {
      const p = predefinedMap.get(key);
      setName(key);
      if (p?.periodStartDate) setStartDate(p.periodStartDate);
      if (p?.periodEndDate) setEndDate(p.periodEndDate);
    }
    setDropdownOpen(false);

    if (key === CUSTOM) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          inputRef.current?.focus();
        });
      });
    }
  };

  const initialSnapshot = useMemo(() => ({
    name: season.name,
    startDate: season.startDate ?? '',
    endDate: season.endDate ?? '',
    fieldIds: seasonFieldIds,
  }), [season.name, season.startDate, season.endDate, seasonFieldIds]);

  const dirty = name !== initialSnapshot.name
    || startDate !== initialSnapshot.startDate
    || endDate !== initialSnapshot.endDate
    || JSON.stringify([...selectedFieldIds].sort()) !== JSON.stringify([...initialSnapshot.fieldIds].sort());

  const endDateMin = useMemo(() => {
    if (!startDate) return undefined;
    const d = new Date(startDate + 'T00:00:00');
    d.setDate(d.getDate() + 1);
    return d.toISOString().split('T')[0];
  }, [startDate]);

  const handleCancel = useCallback(() => {
    if (dirty) {
      setConfirmClose(true);
    } else {
      onOpenChange(false);
    }
  }, [dirty, onOpenChange]);

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
            <button aria-label="Close" onClick={handleCancel} className="rounded-md p-1 text-muted-foreground hover:bg-accent/40 cursor-pointer">
              <X className="size-4" />
            </button>
          </div>

          <div className="p-4 space-y-4">
            <div className="grid grid-cols-1 gap-3">
              <label className="text-sm">Season name <span className="text-destructive">*</span></label>
              <div className="relative">
                <Select value={ selectedKey } onValueChange={ handleSeasonSelect } open={ dropdownOpen } onOpenChange={ setDropdownOpen }>
                  <SelectTrigger className="sr-only" />
                  <SelectContent>
                    { (predefinedQ.data ?? []).map((s) => (
                      <SelectItem key={ s.id } value={ s.seasonName }>{ s.seasonName }</SelectItem>
                    )) }
                    <SelectItem value={ CUSTOM }>Custom</SelectItem>
                  </SelectContent>
                </Select>

                { isCustom ? (
                  <div className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-within:outline-none focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2">
                    <input
                      ref={ inputRef }
                      value={ name }
                      autoFocus
                      onChange={ (e) => { setName(e.target.value); setError(null); } }
                      placeholder="Enter season name"
                      className="flex-1 bg-transparent outline-none text-sm"
                    />
                    <button
                      type="button"
                      onClick={ () => setDropdownOpen(true) }
                      className="flex cursor-pointer items-center"
                    >
                      <ChevronDown className="size-4 text-muted-foreground" />
                    </button>
                  </div>
                ) : (
                  <div
                    className="flex h-10 w-full cursor-pointer items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background hover:bg-accent/40 focus-within:outline-none focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2"
                    onClick={ () => setDropdownOpen(true) }
                  >
                    <span>{ name }</span>
                    <ChevronDown className="size-4 text-muted-foreground" />
                  </div>
                ) }
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm">Start date <span className="text-destructive">*</span></label>
                <DatePicker
                  value={startDate}
                  disabled={!isCustom}
                  onChange={(v) => {
                    setStartDate(v);
                    if (endDate && v >= endDate) setEndDate('');
                  }}
                  placeholder="Start Date"
                  onOpenChange={(open) => { if (open && !name.trim()) setError('Season name is required'); }}
                />
              </div>
              <div>
                <label className="text-sm">End date <span className="text-destructive">*</span></label>
                <DatePicker
                  value={endDate}
                  disabled={!isCustom || !startDate}
                  onChange={setEndDate}
                  placeholder="End Date"
                  minDate={endDateMin}
                  onOpenChange={(open) => { if (open && !name.trim()) setError('Season name is required'); }}
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
              <Button variant="outline" size="lg" className="min-w-[120px]" onClick={handleCancel}>
                Cancel
              </Button>
              <Button variant="primary" size="lg" className="min-w-[120px]" onClick={handleSave}>
                Save
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>

      <AlertDialogRoot open={confirmClose} onOpenChange={setConfirmClose}>
        <AlertDialogContent>
          <AlertDialogTitle>Save the changes?</AlertDialogTitle>
          <AlertDialogDescription>
            All unsaved changes will be lost.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel className="cursor-pointer" onClick={() => setConfirmClose(false)}>No</AlertDialogCancel>
            <AlertDialogAction className="cursor-pointer" onClick={() => { setConfirmClose(false); onOpenChange(false); }}>
              Yes
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogRoot>
    </Dialog.Root>
  );
}
