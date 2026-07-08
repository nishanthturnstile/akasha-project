import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useDeleteSeason, useFields, useSeasons } from '@/lib/queries';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  deletingSeasonId: string | null;
}

export default function DeleteSeasonDialog({ open, onOpenChange, deletingSeasonId }: Props) {
  const [deletingSeasonMoveTarget, setDeletingSeasonMoveTarget] = useState<string | null>(null);
  const deleteSeason = useDeleteSeason();
  const seasonsQ = useSeasons();
  const fieldsQ = useFields();

  const sortedSeasons = useMemo(() => {
    const data = seasonsQ.data;
    if (!Array.isArray(data)) return [];
    return [...data].sort(
      (a, b) => new Date(b.createdAt ?? 0).getTime() - new Date(a.createdAt ?? 0).getTime(),
    );
  }, [seasonsQ.data]);

  const deletingSeason = useMemo(
    () => (deletingSeasonId ? sortedSeasons.find((s) => s.id === deletingSeasonId) ?? null : null),
    [deletingSeasonId, sortedSeasons],
  );

  const orphanFieldCount = useMemo(() => {
    if (!deletingSeason) return 0;
    const allFields = fieldsQ.data;
    if (!Array.isArray(allFields)) return 0;
    const otherSeasonIds = new Set(
      sortedSeasons.filter((s) => s.id !== deletingSeasonId).map((s) => s.id),
    );
    return deletingSeason.fieldIds.filter((fe) => {
      if (!fe.isMapped) return false;
      const field = allFields.find((f) => f.id === fe.id);
      if (!field) return false;
      return !field.seasonIds.some((sid) => otherSeasonIds.has(sid));
    }).length;
  }, [deletingSeason, deletingSeasonId, fieldsQ.data, sortedSeasons]);

  const otherSeasons = useMemo(
    () => sortedSeasons.filter((s) => s.id !== deletingSeasonId),
    [sortedSeasons, deletingSeasonId],
  );

  const handleClose = () => {
    setDeletingSeasonMoveTarget(null);
    onOpenChange(false);
  };

  return (
    <Dialog.Root open={ open } onOpenChange={ (open) => { if (!open) handleClose(); } }>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-overlay bg-background/60 backdrop-blur-sm" />
        <Dialog.Content
          onCloseAutoFocus={ (e) => e.preventDefault() }
          className="fixed left-1/2 top-1/2 z-popover w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-popover p-6 shadow-e2"
        >
          <VisuallyHidden>
            <Dialog.Title>Delete season</Dialog.Title>
            <Dialog.Description>Delete season confirmation</Dialog.Description>
          </VisuallyHidden>

          { orphanFieldCount > 0 ? (
            <div className="relative">
              <button
                aria-label="Close"
                onClick={ handleClose }
                className="absolute right-0 top-0 cursor-pointer rounded-md border-0 bg-transparent p-1 text-muted-foreground shadow-none hover:bg-accent/40"
              >
                <X className="size-4" />
              </button>
              <h2 className="text-center text-base font-display font-semibold text-foreground">Delete Season</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                By deleting this season, you will permanently remove all data assigned to it.
                This season contains one or more fields that are not assigned to any other
                season. Please move these fields to another season before deleting it.
              </p>
              <div className="py-3">
                <label className="mb-1.5 block text-sm font-medium">Select Season</label>
                <Select value={ deletingSeasonMoveTarget ?? '' } onValueChange={ setDeletingSeasonMoveTarget }>
                  <SelectTrigger className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm">
                    <SelectValue placeholder="Select a season" />
                  </SelectTrigger>
                  <SelectContent>
                    { otherSeasons.map((s) => (
                      <SelectItem key={ s.id } value={ s.id }>{ s.name }</SelectItem>
                    )) }
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3 pt-3">
                <Dialog.Close className="inline-flex w-full cursor-pointer items-center justify-center rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground shadow-sm hover:bg-accent/40 transition-colors duration-fast">
                  Cancel
                </Dialog.Close>
                <Button
                  variant="primary"
                  size="lg"
                  className="w-full cursor-pointer"
                  disabled={ !deletingSeasonMoveTarget }
                  onClick={ async () => {
                    if (!deletingSeasonId || !deletingSeasonMoveTarget) return;
                    await deleteSeason.mutateAsync({ seasonId: deletingSeasonId, moveFieldsToSeasonId: deletingSeasonMoveTarget });
                    handleClose();
                  } }
                >
                  Delete
                </Button>
              </div>
            </div>
          ) : (
            <>
              <h2 className="text-base font-display font-semibold text-foreground">Delete season?</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Are you sure you want to delete "{ deletingSeason?.name }"? This action cannot be undone.
              </p>
              <div className="mt-6 flex items-center justify-end gap-2">
                <Dialog.Close className="inline-flex cursor-pointer items-center justify-center rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground shadow-sm hover:bg-accent/40 transition-colors duration-fast">
                  Cancel
                </Dialog.Close>
                <Dialog.Close
                  className="inline-flex cursor-pointer items-center justify-center rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground shadow-sm hover:bg-destructive/90 transition-colors duration-fast"
                  onClick={ async (e) => {
                    e.preventDefault();
                    if (!deletingSeasonId) return;
                    await deleteSeason.mutateAsync({ seasonId: deletingSeasonId });
                    handleClose();
                  } }
                >
                  Delete
                </Dialog.Close>
              </div>
            </>
          ) }
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
