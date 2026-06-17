import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { X } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { GeometryPreview } from '@/lib/geometry-preview';
import type { Field } from '@/types/api';

interface Props {
  field: Field;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave?: (fieldId: string, name?: string) => void;
  onDelete?: (fieldId: string) => void;
}

export default function EditFieldDialog({
  field,
  open,
  onOpenChange,
  onSave,
  onDelete,
}: Props) {
  const [name, setName] = useState(field.name);
  const [error, setError] = useState<string | null>(null);

  const handleSave = () => {
    if (!name.trim()) {
      setError('Field name is required');
      return;
    }
    setError(null);
    onSave?.(field.id, name.trim());
    onOpenChange(false);
  };

  const handleDelete = () => {
    onDelete?.(field.id);
    onOpenChange(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-popover bg-background/60 backdrop-blur-sm" />
        <Dialog.Content
          aria-label="Edit field"
          className="glass fixed left-1/2 top-[22vh] z-popover w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-lg p-0"
        >
          <VisuallyHidden>
            <Dialog.Title>Edit field</Dialog.Title>
            <Dialog.Description>Edit field name and view its boundary.</Dialog.Description>
          </VisuallyHidden>

          <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
            <h3 className="text-base font-display font-semibold">Edit field</h3>
            <Dialog.Close asChild>
              <button aria-label="Close" className="rounded-md p-1 text-muted-foreground hover:bg-accent/40">
                <X className="size-4" />
              </button>
            </Dialog.Close>
          </div>

          <div className="p-4 space-y-4">
            <div className="flex items-center justify-center p-4 bg-muted/30 rounded-lg border border-border/60">
              <GeometryPreview
                geometry={field.geometry}
                width={200}
                height={140}
              />
            </div>

            <div className="grid grid-cols-1 gap-3">
              <label className="text-sm">Field name</label>
              <input
                className="rounded-md border border-border bg-background px-3 py-2"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="text-sm text-muted-foreground">
              Area: {field.areaHa != null ? `${field.areaHa.toFixed(2)} ha` : '—'}
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex items-center justify-between gap-2 border-t border-border/60 pt-3">
              <div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDelete}
                  className="text-destructive border-destructive/40 hover:bg-destructive/10"
                >
                  Delete field
                </Button>
              </div>
              <div className="flex items-center gap-2">
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
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
