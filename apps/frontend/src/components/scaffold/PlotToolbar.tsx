import { Download, Pencil, Spline, Trash2, Upload, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

export type FieldToolbarAction = 'draw' | 'edit' | 'import' | 'export' | 'delete';

type ActionHandler = () => void;

export interface PlotToolbarProps {
  activeAction?: FieldToolbarAction | null;
  className?: string;
  disabledActions?: Partial<Record<FieldToolbarAction, string>>;
  hasSelectedField?: boolean;
  isMapAvailable?: boolean;
  onDeleteSelectedField?: ActionHandler;
  onDrawField?: ActionHandler;
  onEditSelectedField?: ActionHandler;
  onExportGeoJSON?: ActionHandler;
  onImportGeoJSON?: ActionHandler;
  selectedFieldName?: string | null;
  selectionRequiredActions?: readonly FieldToolbarAction[];
}

interface ToolDefinition {
  activeMode?: boolean;
  ariaLabel: string;
  disabledWithoutSelection: string;
  icon: LucideIcon;
  id: FieldToolbarAction;
  label: string;
  tooltip: string;
  tone?: 'default' | 'destructive';
}

const FIELD_TOOLS: readonly ToolDefinition[] = [
  {
    id: 'draw',
    icon: Spline,
    label: 'Draw',
    ariaLabel: 'Draw field',
    tooltip: 'Draw a new field boundary',
    disabledWithoutSelection: '',
    activeMode: true,
  },
  {
    id: 'edit',
    icon: Pencil,
    label: 'Edit',
    ariaLabel: 'Edit selected field',
    tooltip: 'Edit the selected field boundary',
    disabledWithoutSelection: 'Select a field to edit its boundary.',
    activeMode: true,
  },
  {
    id: 'import',
    icon: Upload,
    label: 'Import',
    ariaLabel: 'Import field GeoJSON',
    tooltip: 'Import a field from GeoJSON',
    disabledWithoutSelection: '',
  },
  {
    id: 'export',
    icon: Download,
    label: 'Export',
    ariaLabel: 'Export selected field as GeoJSON',
    tooltip: 'Export the selected field as GeoJSON',
    disabledWithoutSelection: 'Select a field to export it as GeoJSON.',
  },
  {
    id: 'delete',
    icon: Trash2,
    label: 'Delete',
    ariaLabel: 'Delete selected field',
    tooltip: 'Delete the selected field',
    disabledWithoutSelection: 'Select a field to delete it.',
    tone: 'destructive',
  },
] as const;

const DEFAULT_SELECTION_REQUIRED_ACTIONS: readonly FieldToolbarAction[] = [
  'edit',
  'export',
  'delete',
];

function getSelectedFieldCopy(selectedFieldName?: string | null) {
  return selectedFieldName ? `: ${selectedFieldName}` : '';
}

export function PlotToolbar({
  activeAction = null,
  className,
  disabledActions,
  hasSelectedField = false,
  isMapAvailable = true,
  onDeleteSelectedField,
  onDrawField,
  onEditSelectedField,
  onExportGeoJSON,
  onImportGeoJSON,
  selectedFieldName,
  selectionRequiredActions = DEFAULT_SELECTION_REQUIRED_ACTIONS,
}: PlotToolbarProps) {
  const selectionRequired = new Set(selectionRequiredActions);
  const handlers: Record<FieldToolbarAction, ActionHandler | undefined> = {
    draw: onDrawField,
    edit: onEditSelectedField,
    import: onImportGeoJSON,
    export: onExportGeoJSON,
    delete: onDeleteSelectedField,
  };

  const disabledReasonFor = (tool: ToolDefinition) => {
    const explicitReason = disabledActions?.[tool.id];
    if (explicitReason) {
      return explicitReason;
    }

    if (tool.id === 'draw' && !isMapAvailable) {
      return 'The map must finish loading before drawing a field.';
    }

    if (selectionRequired.has(tool.id) && !hasSelectedField) {
      return tool.disabledWithoutSelection || 'Select a field to use this action.';
    }

    return null;
  };

  return (
    <div
      className={ cn('glass flex items-center gap-0.5 rounded-md p-1', className) }
      data-testid="plot-toolbar"
      role="toolbar"
      aria-label="Field tools"
      aria-orientation="horizontal"
    >
      { FIELD_TOOLS.map((tool) => {
        const Icon = tool.icon;
        const disabledReason = disabledReasonFor(tool);
        const disabled = Boolean(disabledReason);
        const active = activeAction === tool.id;
        const selectedFieldCopy =
          hasSelectedField && selectionRequired.has(tool.id)
            ? getSelectedFieldCopy(selectedFieldName)
            : '';
        const tooltip = disabledReason ?? `${tool.tooltip}${selectedFieldCopy}`;
        const button = (
          <Button
            key={ tool.id }
            type="button"
            variant="ghost"
            size="icon"
            aria-label={ `${tool.ariaLabel}${selectedFieldCopy}` }
            aria-pressed={ tool.activeMode || active ? active : undefined }
            disabled={ disabled }
            onClick={ handlers[tool.id] }
            className={ cn(
              'size-9 text-muted-foreground transition-[background-color,color,box-shadow,transform]',
              active && 'bg-primary/15 text-foreground shadow-e1',
              tool.tone === 'destructive' &&
              !disabled &&
              'hover:bg-destructive/10 hover:text-destructive',
            ) }
            data-testid={ `field-toolbar-${tool.id}` }
          >
            <Icon className="size-4.5" strokeWidth={ 1.75 } aria-hidden="true" />
            <span className="sr-only">{ tool.label }</span>
          </Button>
        );

        return (
          <Tooltip key={ tool.id }>
            <TooltipTrigger asChild>
              { disabled ? (
                <span
                  className="inline-flex cursor-not-allowed rounded-md"
                  tabIndex={ 0 }
                  aria-label={ `${tool.ariaLabel}. ${tooltip}` }
                >
                  { button }
                </span>
              ) : (
                button
              ) }
            </TooltipTrigger>
            <TooltipContent side="bottom" align="center">
              { tooltip }
            </TooltipContent>
          </Tooltip>
        );
      }) }
    </div>
  );
}
