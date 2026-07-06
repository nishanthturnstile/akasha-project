import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { Search, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useCreateSeason, useFields, useSeasons } from '@/lib/queries';
import type { Season } from '@/types/api';
import {
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogRoot,
  AlertDialogTitle,
  AlertDialogFooter,
} from '@/components/ui/alert-dialog';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (season: Season) => void;
}

export default function CreateSeasonDialog({ open, onOpenChange, onCreated }: Props) {
  const [name, setName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [selectedFieldIds, setSelectedFieldIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [startDateError, setStartDateError] = useState<string | null>(null);
  const [endDateError, setEndDateError] = useState<string | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);

  const initialSnapshot = useMemo(() => ({
    name: '',
    startDate: '',
    endDate: '',
    fieldIds: [] as string[],
  }), []);

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

  const createSeason = useCreateSeason();
  const fieldsQ = useFields();
  const seasonsQuery = useSeasons();

  const existingSeasonNames = useMemo(() => {
    if (!Array.isArray(seasonsQuery.data)) return new Set<string>();
    return new Set(seasonsQuery.data.map((s) => s.name.toLowerCase().trim()));
  }, [seasonsQuery.data]);

  useEffect(() => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const timer = setTimeout(() => {
      if (existingSeasonNames.has(trimmed.toLowerCase())) {
        setNameError('Season name already exists.');
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [name, existingSeasonNames]);

  const allFields = useMemo(() => (Array.isArray(fieldsQ.data) ? fieldsQ.data : []), [fieldsQ.data]);

  const toggleField = (fieldId: string) => {
    setSelectedFieldIds((prev) =>
      prev.includes(fieldId) ? prev.filter((x) => x !== fieldId) : [...prev, fieldId],
    );
  };

  const [copyFromSeasonEnabled, setCopyFromSeasonEnabled] = useState(false);
  const [copySourceSeasonId, setCopySourceSeasonId] = useState<string | null>(null);

  const existingSeasons = useMemo(() => {
    if (!Array.isArray(seasonsQuery.data)) return [];
    return seasonsQuery.data;
  }, [seasonsQuery.data]);

  const copySourceFieldsEmpty = useMemo(() => {
    if (!copySourceSeasonId) return false;
    const season = existingSeasons.find((s) => s.id === copySourceSeasonId);
    if (!season) return true;
    return season.fieldIds.filter((fi) => fi.isMapped).length === 0;
  }, [existingSeasons, copySourceSeasonId]);

  const handleCopySeasonChange = (seasonId: string) => {
    setCopySourceSeasonId(seasonId);
    const season = existingSeasons.find((s) => s.id === seasonId);
    if (season) {
      const mappedFieldIds = season.fieldIds.filter((fi) => fi.isMapped).map((fi) => fi.id);
      setSelectedFieldIds(mappedFieldIds);
    }
  };

  const [search, setSearch] = useState('');

  const filteredAllFields = useMemo(() => {
    if (!search.trim()) return allFields;
    const q = search.trim().toLocaleLowerCase();
    return allFields.filter((f) => f.name.toLocaleLowerCase().includes(q));
  }, [allFields, search]);

  const canCreate = name.trim() !== '' && startDate !== '' && endDate !== '' && !nameError;

  const handleCancel = useCallback(() => {
    if (dirty) {
      setConfirmClose(true);
    } else {
      onOpenChange(false);
    }
  }, [dirty, onOpenChange]);

  const handleCreate = async () => {
    let hasError = false;
    if (!name.trim()) { setNameError('Season name is required'); hasError = true; }
    if (!startDate) { setStartDateError('Start date is required'); hasError = true; }
    if (!endDate) { setEndDateError('End date is required'); hasError = true; }
    if (hasError || !canCreate) return;
    setError(null);
    try {
      const created = await createSeason.mutateAsync({
        name: name.trim(),
        startDate: startDate || null,
        endDate: endDate || null,
        fieldIds: selectedFieldIds,
      });
      onCreated?.(created);
      onOpenChange(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create season';
      setError(message);
    }
  };

  return (
    <Dialog.Root open={ open } onOpenChange={ onOpenChange }>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-popover bg-background/60 backdrop-blur-sm" />
        <Dialog.Content
          aria-label="Create season"
          onInteractOutside={ (e) => e.preventDefault() }
          onEscapeKeyDown={ (e) => e.preventDefault() }
          className="glass fixed left-1/2 top-[12vh] z-popover w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 rounded-lg p-0"
        >
          <VisuallyHidden>
            <Dialog.Title>Create season</Dialog.Title>
            <Dialog.Description>
              Create a new season and assign fields to it.
            </Dialog.Description>
          </VisuallyHidden>

          <div className="relative border-b border-border/60 px-4 py-4">
            <button aria-label="Close" onClick={handleCancel} className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground hover:bg-accent/40">
              <X className="size-4" />
            </button>
            <h3 className="text-center text-base font-display font-bold">Create season</h3>
            <p className="mt-1 text-center text-xs text-muted-foreground">
              Seasons filter all platform data and field assignments.
            </p>
          </div>

          <div className="p-4 space-y-4">
            <div className="grid grid-cols-1 gap-3">
              <label className="text-sm">Season name <span className="text-destructive">*</span></label>
              <input
                className="rounded-md border border-border bg-background px-3 py-2"
                value={ name }
                onChange={ (e) => { setName(e.target.value); setNameError(null); } }
              />
              { nameError && <p className="text-sm text-destructive">{ nameError }</p> }
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm">Start date <span className="text-destructive">*</span></label>
                <DatePicker
                  value={ startDate }
                  onChange={ (v) => {
                    setStartDate(v);
                    setStartDateError(null);
                    if (endDate && v >= endDate) { setEndDate(''); setEndDateError(null); }
                  } }
                  placeholder="Start Date"
                  onOpenChange={ (open) => { if (open && !name.trim()) setNameError('Season name is required'); } }
                />
                { startDateError && <p className="text-sm text-destructive mt-1">{ startDateError }</p> }
              </div>
              <div>
                <label className="text-sm">End date <span className="text-destructive">*</span></label>
                <DatePicker
                  value={ endDate }
                  onChange={ (v) => { setEndDate(v); setEndDateError(null); } }
                  placeholder="End Date"
                  disabled={ !startDate }
                  minDate={ endDateMin }
                  onOpenChange={ (open) => { if (open && !name.trim()) setNameError('Season name is required'); } }
                />
                { endDateError && <p className="text-sm text-destructive mt-1">{ endDateError }</p> }
              </div>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="copy-fields"
                checked={ copyFromSeasonEnabled }
                onChange={ (e) => {
                  setCopyFromSeasonEnabled(e.target.checked);
                  if (!e.target.checked) {
                    setCopySourceSeasonId(null);
                  }
                } }
              />
              <label htmlFor="copy-fields" className="text-sm cursor-pointer">Copy fields from season</label>
            </div>

            { copyFromSeasonEnabled && (
              <div className="grid grid-cols-1 gap-2">
                <label className="text-sm">Source season</label>
                { existingSeasons.length > 0 ? (
                  <>
                    <select
                      value={ copySourceSeasonId ?? '' }
                      onChange={ (e) => handleCopySeasonChange(e.target.value) }
                      className="rounded-md border border-border bg-background px-3 py-2 text-sm"
                    >
                      <option value="" disabled>Select a season</option>
                      { existingSeasons.map((s) => (
                        <option key={ s.id } value={ s.id }>{ s.name }</option>
                      )) }
                    </select>
                    { copySourceSeasonId && copySourceFieldsEmpty && (
                      <p className="text-sm text-muted-foreground">No fields available in the selected season.</p>
                    ) }
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">No existing seasons to copy from.</p>
                ) }
              </div>
            ) }

            { allFields.length > 0 && (
              <div className="grid grid-cols-1 gap-2">
                <label className="relative block">
                  <span className="sr-only">Search fields</span>
                  <Search
                    className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
                    strokeWidth={ 1.75 }
                  />
                  <input
                    type="search"
                    value={ search }
                    onChange={ (e) => setSearch(e.target.value) }
                    placeholder="Search"
                    className="h-8 w-full rounded-md border border-input bg-background/55 pl-8 pr-3 text-[13px] text-foreground shadow-e1 transition-colors duration-fast placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </label>

                <ScrollArea className="max-h-48 pr-2">
                  <div className="space-y-2">
                    { filteredAllFields.map((f) => (
                      <div
                        key={ f.id }
                        className="flex items-center justify-between rounded-lg border border-border/70 bg-card/35 px-3 py-2"
                      >
                        <div className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={ selectedFieldIds.includes(f.id) }
                            onChange={ () => toggleField(f.id) }
                          />
                          <div className="text-sm">{ f.name }</div>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          { f.areaHa != null ? `${f.areaHa.toFixed(2)} ha` : '—' }
                        </div>
                      </div>
                    )) }
                    { filteredAllFields.length === 0 && (
                      <p className="text-sm text-muted-foreground py-2 text-center">No fields match your search.</p>
                    ) }
                  </div>
                </ScrollArea>
              </div>
            ) }

            { error && <p className="text-sm text-destructive">{ error }</p> }

            <div className="flex items-center justify-end gap-2 border-t border-border/60 pt-3">
              <Button variant="outline" size="lg" className="min-w-[120px]" onClick={handleCancel}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="lg"
                className="min-w-[120px]"
                onClick={ handleCreate }
                disabled={ !canCreate || createSeason.isPending }
              >
                { createSeason.isPending ? 'Creating…' : 'Create season' }
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
            <AlertDialogCancel onClick={() => setConfirmClose(false)}>No</AlertDialogCancel>
            <AlertDialogAction onClick={() => onOpenChange(false)}>
              Yes
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialogRoot>
    </Dialog.Root>
  );
}


