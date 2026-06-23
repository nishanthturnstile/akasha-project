import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { Search, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { useCreateSeason, useFields } from '@/lib/queries';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (seasonId: string) => void;
}

function CreateSeasonDialogInner({ open, onOpenChange, onCreated }: Props) {
  const [name, setName] = useState('');
  const [startDate, setStartDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [endDate, setEndDate] = useState('');
  const [selectedFieldIds, setSelectedFieldIds] = useState<string[]>([]);
  const [deselectedFieldIds, setDeselectedFieldIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const createSeason = useCreateSeason();
  const fieldsQ = useFields();

  const allFields = useMemo(() => (Array.isArray(fieldsQ.data) ? fieldsQ.data : []), [fieldsQ.data]);

  const toggleField = (fieldId: string) => {
    setSelectedFieldIds((prev) => {
      if (prev.includes(fieldId)) {
        const newSelected = prev.filter((x) => x !== fieldId);
        setDeselectedFieldIds((d) => d.includes(fieldId) ? d : [...d, fieldId]);
        return newSelected;
      }
      return [...prev, fieldId];
    });
  };

  const [fieldTab, setFieldTab] = useState<'list' | 'added' | 'removed'>('list');
  const [listSearch, setListSearch] = useState('');
  const [addedSearch, setAddedSearch] = useState('');
  const [removedSearch, setRemovedSearch] = useState('');

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
    const removed = allFields.filter((f) => deselectedFieldIds.includes(f.id));
    if (!removedSearch.trim()) return removed;
    const q = removedSearch.trim().toLocaleLowerCase();
    return removed.filter((f) => f.name.toLocaleLowerCase().includes(q));
  }, [allFields, deselectedFieldIds, removedSearch]);

  const canCreate = name.trim() !== '' && startDate !== '' && endDate !== '';

  const handleCreate = async () => {
    if (!canCreate) return;
    setError(null);
    try {
      const created = await createSeason.mutateAsync({
        name: name.trim(),
        startDate: startDate || null,
        endDate: endDate || null,
        fieldIds: selectedFieldIds,
      });
      onCreated?.(created.id);
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
            <Dialog.Close asChild>
              <button aria-label="Close" className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground hover:bg-accent/40">
                <X className="size-4" />
              </button>
            </Dialog.Close>
            <h3 className="text-center text-base font-display font-bold">Create season</h3>
            <p className="mt-1 text-center text-xs text-muted-foreground">
              Seasons filter all platform data and field assignments.
            </p>
          </div>

          <div className="p-4 space-y-4">
            <div className="grid grid-cols-1 gap-3">
              <label className="text-sm">Season name</label>
              <input
                className="rounded-md border border-border bg-background px-3 py-2"
                value={ name }
                onChange={ (e) => setName(e.target.value) }
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm">Start date</label>
                <DatePicker
                  value={ startDate }
                  onChange={ setStartDate }
                  placeholder="Start Date"
                />
              </div>
              <div>
                <label className="text-sm">End date</label>
                <DatePicker
                  value={ endDate }
                  onChange={ setEndDate }
                  placeholder="End Date"
                />
              </div>
            </div>

            { allFields.length > 0 && (
              <div className="grid grid-cols-1 gap-2">
                <div className="flex items-center border-b border-border/60">
                  <button
                    type="button"
                    onClick={ () => setFieldTab('list') }
                    className={ cn(
                      'flex-1 pb-2 text-sm font-medium border-b-2 transition-colors',
                      fieldTab === 'list'
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground',
                    ) }
                  >
                    Field List
                  </button>
                  <button
                    type="button"
                    onClick={ () => setFieldTab('added') }
                    className={ cn(
                      'flex-1 pb-2 text-sm font-medium border-b-2 transition-colors',
                      fieldTab === 'added'
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground',
                    ) }
                  >
                    Added Fields ({ selectedFieldIds.length })
                  </button>
                  <button
                    type="button"
                    onClick={ () => setFieldTab('removed') }
                    className={ cn(
                      'flex-1 pb-2 text-sm font-medium border-b-2 transition-colors',
                      fieldTab === 'removed'
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground',
                    ) }
                  >
                    Removed Fields ({ deselectedFieldIds.length })
                  </button>
                </div>

                <label className="relative block">
                  <span className="sr-only">Search fields</span>
                  <Search
                    className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
                    strokeWidth={ 1.75 }
                  />
                  <input
                    type="search"
                    value={ fieldTab === 'list' ? listSearch : fieldTab === 'added' ? addedSearch : removedSearch }
                    onChange={ (e) => {
                      if (fieldTab === 'list') setListSearch(e.target.value);
                      else if (fieldTab === 'added') setAddedSearch(e.target.value);
                      else setRemovedSearch(e.target.value);
                    } }
                    placeholder={ `Search ${fieldTab === 'list' ? 'all' : fieldTab === 'added' ? 'added' : 'removed'} fields\u2026` }
                    className="h-8 w-full rounded-md border border-input bg-background/55 pl-8 pr-3 text-[13px] text-foreground shadow-e1 transition-colors duration-fast placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </label>

                <ScrollArea className="max-h-48 pr-2">
                  <div className="space-y-2">
                    { fieldTab === 'list' && filteredAllFields.map((f) => (
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
                    { fieldTab === 'added' && filteredAddedFields.map((f) => (
                      <div
                        key={ f.id }
                        className="flex items-center justify-between rounded-lg border border-border/70 bg-card/35 px-3 py-2"
                      >
                        <div className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={ true }
                            onChange={ () => toggleField(f.id) }
                          />
                          <div className="text-sm">{ f.name }</div>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          { f.areaHa != null ? `${f.areaHa.toFixed(2)} ha` : '—' }
                        </div>
                      </div>
                    )) }
                    { fieldTab === 'removed' && filteredRemovedFields.map((f) => (
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
                    { fieldTab === 'list' && filteredAllFields.length === 0 && (
                      <p className="text-sm text-muted-foreground py-2 text-center">No fields match your search.</p>
                    ) }
                    { fieldTab === 'added' && filteredAddedFields.length === 0 && (
                      <p className="text-sm text-muted-foreground py-2 text-center">No fields added yet.</p>
                    ) }
                    { fieldTab === 'removed' && filteredRemovedFields.length === 0 && (
                      <p className="text-sm text-muted-foreground py-2 text-center">No fields removed.</p>
                    ) }
                  </div>
                </ScrollArea>
              </div>
            ) }

            { error && <p className="text-sm text-destructive">{ error }</p> }

            <div className="flex items-center justify-end gap-2 border-t border-border/60 pt-3">
              <Dialog.Close asChild>
                <button type="button" className="rounded-md border border-border px-3 py-1.5 text-sm">
                  Cancel
                </button>
              </Dialog.Close>
              <Button
                variant="primary"
                size="sm"
                onClick={ handleCreate }
                disabled={ !canCreate || createSeason.isPending }
                className={ cn('gap-2', !canCreate && 'opacity-60') }
              >
                { createSeason.isPending ? 'Creating…' : 'Create season' }
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
export default function CreateSeasonDialog({ open, onOpenChange, onCreated }: Props) {
  // Use a key to force remount and reset all internal state when dialog opens
  return <CreateSeasonDialogInner key={ open ? 'open' : 'closed' } open={ open } onOpenChange={ onOpenChange } onCreated={ onCreated } />;
}
