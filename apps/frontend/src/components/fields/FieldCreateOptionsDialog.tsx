import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { Map, Upload, FileUp, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';

interface OptionItem {
  icon: typeof Map;
  title: string;
  description: string;
  action: () => void;
  disabled?: boolean;
  disabledHint?: string;
}

export function FieldCreateOptionsDialog({
  open,
  onOpenChange,
  defaultSeasonId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultSeasonId?: string | null;
}) {
  const navigate = useNavigate();
  const seasonParam = defaultSeasonId ? `&seasonId=${defaultSeasonId}` : '';

  const options: OptionItem[] = [
    {
      icon: Map,
      title: 'Draw on map',
      description: 'Draw a polygon field boundary on the map',
      action: () => {
        onOpenChange(false);
        navigate(`/monitoring/field-create?mode=draw${seasonParam}`);
      },
    },
    {
      icon: Upload,
      title: 'Upload fields',
      description: '.shp, .kml, .kmz, .geojson',
      disabled: true,
      disabledHint: 'Upload coming soon',
      action: () => {},
    },
    {
      icon: FileUp,
      title: 'Custom upload',
      description: 'Import from external tools',
      disabled: true,
      disabledHint: 'Custom upload coming soon',
      action: () => {},
    },
  ];

  return (
    <Dialog.Root open={ open } onOpenChange={ onOpenChange }>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-modal bg-background/60 backdrop-blur-sm" />
        <Dialog.Content className="glass fixed left-1/2 top-1/2 z-modal w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-xl p-6">
          <VisuallyHidden>
            <Dialog.Title>Add field</Dialog.Title>
            <Dialog.Description>Choose how to add a field.</Dialog.Description>
          </VisuallyHidden>

          <div className="flex items-center justify-between gap-2">
            <h2 className="font-display text-lg font-semibold">Add field</h2>
            <button
              type="button"
              onClick={ () => onOpenChange(false) }
              className="rounded-md p-1.5 text-muted-foreground hover:bg-accent/40"
            >
              <X className="size-5" />
            </button>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3">
            { options.map((opt) => {
              const Icon = opt.icon;
              return (
                <button
                  key={ opt.title }
                  type="button"
                  disabled={ opt.disabled }
                  onClick={ opt.action }
                  className={ cn(
                    'flex flex-col items-center gap-2 rounded-lg border-2 p-4 text-center transition-colors duration-fast',
                    opt.disabled
                      ? 'border-border/40 opacity-50 cursor-not-allowed'
                      : 'border-border/60 hover:border-primary/40 hover:bg-primary/[0.04] cursor-pointer',
                  ) }
                  title={ opt.disabled ? opt.disabledHint : undefined }
                >
                  <Icon className="size-8 text-primary/70" strokeWidth={ 1.5 } />
                  <span className="font-display text-sm font-semibold text-foreground">{ opt.title }</span>
                  <span className="text-xs text-muted-foreground leading-tight">{ opt.description }</span>
                </button>
              );
            }) }
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
