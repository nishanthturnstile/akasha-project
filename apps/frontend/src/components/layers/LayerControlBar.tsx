import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
    ChevronDown,
    ChevronUp,
    ChevronsRight,
    Cloud,
    Layers as LayersIcon,
} from 'lucide-react';
import { SourceSelector } from '@/components/layers/SourceSelector';
import { DisplayModeToggle } from '@/components/layers/DisplayModeToggle';
import { CompareControl } from '@/components/map/CompareControl';
import { DownloadMenu } from '@/components/monitoring/DownloadMenu';
import { Switch } from '@/components/ui/switch';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type {
    CloudMaskOptions,
    Plot,
    SceneDate,
    Source,
} from '@/types/api';

type CloudMaskOptionKey = keyof CloudMaskOptions;

interface LayerControlBarProps {
    sources: Source[] | undefined;
    activeSourceId: string | undefined;
    onSelectSource: (sourceId: string) => void;
    displayModes: string[];
    displayMode: string;
    onDisplayModeChange: (mode: string) => void;
    cloudMask: CloudMaskOptions;
    onCloudMaskChange: (value: CloudMaskOptions) => void;
    cloudMaskDisabled?: boolean;
    compareEnabled: boolean;
    onCompareEnabledChange: (next: boolean) => void;
    comparableDates: SceneDate[];
    activeDate: string | null;
    compareDate: string | null;
    onCompareDateChange: (date: string | null) => void;
    blend: number;
    onBlendChange: (value: number) => void;
    selectedPlot: Plot | null;
    selectedDate: string | null;
    exportSourceId: string | undefined;
    exportIndexType: string;
    exportCloudMask?: CloudMaskOptions;
    collapsed: boolean;
    onCollapsedChange: (next: boolean) => void;
}

interface PopoverButtonProps {
    label: string;
    value: string | undefined;
    ariaLabel?: string;
    testId?: string;
    children: ReactNode;
    align?: 'start' | 'end' | 'center';
    disabled?: boolean;
    icon?: ReactNode;
}

/** Lightweight click-outside-closing popover. Avoids pulling in a new Radix dep. */
function PopoverButton({
    label,
    value,
    ariaLabel,
    testId,
    children,
    align = 'start',
    disabled = false,
    icon,
}: PopoverButtonProps) {
    const [open, setOpen] = useState(false);
    const wrapRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        if (!open) return;
        const onPointerDown = (event: PointerEvent) => {
            if (!wrapRef.current) return;
            if (!wrapRef.current.contains(event.target as Node)) {
                setOpen(false);
            }
        };
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setOpen(false);
        };
        window.addEventListener('pointerdown', onPointerDown);
        window.addEventListener('keydown', onKey);
        return () => {
            window.removeEventListener('pointerdown', onPointerDown);
            window.removeEventListener('keydown', onKey);
        };
    }, [open]);

    return (
        <div ref={ wrapRef } className="relative">
            <button
                type="button"
                disabled={ disabled }
                aria-haspopup="dialog"
                aria-expanded={ open }
                aria-label={ ariaLabel ?? label }
                data-testid={ testId }
                onClick={ () => setOpen((o) => !o) }
                className={ cn(
                    'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[12px] font-medium leading-none transition-colors duration-fast',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    open
                        ? 'bg-primary/15 text-foreground'
                        : 'text-foreground/85 hover:bg-accent hover:text-accent-foreground',
                    disabled && 'cursor-not-allowed opacity-60',
                ) }
            >
                { icon }
                <span className="max-w-40 truncate">
                    <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                        { label }
                    </span>
                    <span className="ml-1 text-[12px] text-foreground">{ value ?? '—' }</span>
                </span>
                { open ? (
                    <ChevronUp className="size-3.5 text-muted-foreground" strokeWidth={ 1.75 } />
                ) : (
                    <ChevronDown className="size-3.5 text-muted-foreground" strokeWidth={ 1.75 } />
                ) }
            </button>
            { open && (
                <div
                    role="dialog"
                    aria-label={ ariaLabel ?? label }
                    className={ cn(
                        'glass absolute bottom-full z-popover mb-2 min-w-56 rounded-md p-3 shadow-e2',
                        align === 'end' && 'right-0',
                        align === 'start' && 'left-0',
                        align === 'center' && 'left-1/2 -translate-x-1/2',
                    ) }
                >
                    { children }
                </div>
            ) }
        </div>
    );
}

const CLOUD_MASK_OPTIONS: Array<{ key: keyof CloudMaskOptions; label: string }> = [
    { key: 'clouds', label: 'Clouds' },
    { key: 'cloudShadows', label: 'Shadows' },
    { key: 'cirrus', label: 'Cirrus' },
];

interface CloudMaskPopoverProps {
    value: CloudMaskOptions;
    onChange: (next: CloudMaskOptions) => void;
    disabled?: boolean;
    availableOptions?: CloudMaskOptionKey[];
    label?: string;
}

/** Compact icon-trigger version of CloudMaskControl for the layer bar. */
function CloudMaskPopover({
    value,
    onChange,
    disabled = false,
    availableOptions,
    label = 'Mask',
}: CloudMaskPopoverProps) {
    const [open, setOpen] = useState(false);
    const wrapRef = useRef<HTMLDivElement | null>(null);
    const options = CLOUD_MASK_OPTIONS.filter((option) =>
        !availableOptions || availableOptions.includes(option.key),
    );

    useEffect(() => {
        if (!open) return;
        const onPointerDown = (event: PointerEvent) => {
            if (!wrapRef.current) return;
            if (!wrapRef.current.contains(event.target as Node)) {
                setOpen(false);
            }
        };
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setOpen(false);
        };
        window.addEventListener('pointerdown', onPointerDown);
        window.addEventListener('keydown', onKey);
        return () => {
            window.removeEventListener('pointerdown', onPointerDown);
            window.removeEventListener('keydown', onKey);
        };
    }, [open]);

    return (
        <div ref={ wrapRef } className="relative">
            <Tooltip>
                <TooltipTrigger asChild>
                    <button
                        type="button"
                        disabled={ disabled }
                        aria-haspopup="dialog"
                        aria-expanded={ open }
                        aria-label={ label }
                        data-testid="layer-cloud-mask-trigger"
                        onClick={ () => setOpen((o) => !o) }
                        className={ cn(
                            'flex size-8 items-center justify-center rounded-md transition-colors duration-fast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                            open
                                ? 'bg-primary/15 text-foreground'
                                : 'text-foreground/85 hover:bg-accent hover:text-accent-foreground',
                            disabled && 'cursor-not-allowed opacity-60',
                        ) }
                    >
                        <Cloud className="size-4" strokeWidth={ 1.75 } aria-hidden="true" />
                    </button>
                </TooltipTrigger>
                <TooltipContent side="top">{ label }</TooltipContent>
            </Tooltip>
            { open && (
                <div
                    role="dialog"
                    aria-label={`${label} options`}
                    data-testid="cloud-mask-control"
                    className="glass absolute bottom-full right-0 z-popover mb-2 flex w-48 flex-col gap-2 rounded-md p-3 shadow-e2"
                >
                    <div className="flex items-center gap-2 text-[12px] font-semibold text-foreground">
                        <Cloud className="size-4 text-primary" strokeWidth={ 1.75 } aria-hidden="true" />
                        { label }
                    </div>
                    { options.map((option) => (
                        <label key={ option.key } className="flex items-center justify-between gap-2">
                            <span className="text-[12px] text-muted-foreground">{ option.label }</span>
                            <Switch
                                checked={ value[option.key] }
                                disabled={ disabled }
                                onCheckedChange={ (checked) =>
                                    onChange({ ...value, [option.key]: checked })
                                }
                                data-testid={ `cloud-mask-${option.key}` }
                                aria-label={ `Toggle ${option.label.toLowerCase()} mask` }
                            />
                        </label>
                    )) }
                    { options.length === 0 && (
                        <p className="text-[12px] leading-4 text-muted-foreground">
                            No configurable mask options for this source.
                        </p>
                    ) }
                </div>
            ) }
        </div>
    );
}

/**
 * Horizontal layer control bar — bottom-right (above timeline).
 * Consolidates source picker, display-mode picker, cloud-mask, compare, and download
 * into one collapsible glass strip (replaces the previous vertical right-stack).
 */
export function LayerControlBar({
    sources,
    activeSourceId,
    onSelectSource,
    displayModes,
    displayMode,
    onDisplayModeChange,
    cloudMask,
    onCloudMaskChange,
    cloudMaskDisabled = false,
    compareEnabled,
    onCompareEnabledChange,
    comparableDates,
    activeDate,
    compareDate,
    onCompareDateChange,
    blend,
    onBlendChange,
    selectedPlot,
    selectedDate,
    exportSourceId,
    exportIndexType,
    exportCloudMask,
    collapsed,
    onCollapsedChange,
}: LayerControlBarProps) {
    const activeSource = sources?.find((s) => s.id === activeSourceId);
    const activeSourceLabel = activeSource?.label;
    const availableMaskOptions = activeSource?.availableMaskOptions;
    const maskLabel = activeSource?.metricsProvisional ? 'Provisional mask' : 'Cloud mask';

    if (collapsed) {
        return (
            <div
                className="glass pointer-events-auto flex items-center gap-1 rounded-md p-1 shadow-e1"
                data-testid="layer-control-bar"
                data-collapsed="true"
            >
                <Tooltip>
                    <TooltipTrigger asChild>
                        <button
                            type="button"
                            onClick={ () => onCollapsedChange(false) }
                            aria-label="Expand layer controls"
                            data-testid="layer-bar-expand"
                            className="flex size-8 items-center justify-center rounded-md text-foreground/85 transition-colors duration-fast hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                            <LayersIcon className="size-4" strokeWidth={ 1.75 } aria-hidden="true" />
                        </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">Show layer controls</TooltipContent>
                </Tooltip>
            </div>
        );
    }

    return (
        <div
            className="glass pointer-events-auto flex max-w-[calc(100vw-5rem)] flex-wrap items-center justify-end gap-1 rounded-md px-1 py-1 shadow-e1"
            data-testid="layer-control-bar"
            data-collapsed="false"
        >
            <PopoverButton
                label="Source"
                value={ activeSourceLabel }
                ariaLabel="Imagery source"
                testId="layer-source-trigger"
                align="start"
                disabled={ !sources || sources.length === 0 }
            >
                <div className="min-w-56">
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                        Source
                    </p>
                    { sources && sources.length > 0 ? (
                        <SourceSelector
                            sources={ sources }
                            value={ activeSourceId }
                            onChange={ onSelectSource }
                        />
                    ) : (
                        <p className="text-[12px] text-muted-foreground">No sources available.</p>
                    ) }
                </div>
            </PopoverButton>

            <span aria-hidden="true" className="h-5 w-px bg-border" />

            <PopoverButton
                label="Layer"
                value={ displayMode }
                ariaLabel="Display mode"
                testId="layer-display-trigger"
                align="start"
                disabled={ displayModes.length <= 1 }
            >
                <div className="min-w-48">
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                        Layer
                    </p>
                    <DisplayModeToggle
                        modes={ displayModes }
                        value={ displayMode }
                        onChange={ onDisplayModeChange }
                    />
                </div>
            </PopoverButton>

            <span aria-hidden="true" className="h-5 w-px bg-border" />

            <div className="flex items-center gap-1" data-testid="layer-bar-cluster">
                <CompareControl
                    enabled={ compareEnabled }
                    onEnabledChange={ onCompareEnabledChange }
                    dates={ comparableDates }
                    activeDate={ activeDate }
                    compareDate={ compareDate }
                    onCompareDateChange={ onCompareDateChange }
                    blend={ blend }
                    onBlendChange={ onBlendChange }
                />
                <CloudMaskPopover
                    value={ cloudMask }
                    onChange={ onCloudMaskChange }
                    disabled={ cloudMaskDisabled }
                    availableOptions={ availableMaskOptions }
                    label={ maskLabel }
                />
                <DownloadMenu
                    selectedPlot={ selectedPlot }
                    selectedDate={ selectedDate }
                    displayMode={ displayMode }
                    sourceId={ exportSourceId }
                    indexType={ exportIndexType }
                    cloudMask={ exportCloudMask ?? cloudMask }
                />
            </div>

            <span aria-hidden="true" className="h-5 w-px bg-border" />

            <Tooltip>
                <TooltipTrigger asChild>
                    <button
                        type="button"
                        onClick={ () => onCollapsedChange(true) }
                        aria-label="Collapse layer controls"
                        data-testid="layer-bar-collapse"
                        className="flex size-8 items-center justify-center rounded-md text-foreground/85 transition-colors duration-fast hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                        <ChevronsRight className="size-4" strokeWidth={ 1.75 } aria-hidden="true" />
                    </button>
                </TooltipTrigger>
                <TooltipContent side="top">Collapse</TooltipContent>
            </Tooltip>
        </div>
    );
}
