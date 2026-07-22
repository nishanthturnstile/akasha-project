import { Command } from 'cmdk';
import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { CalendarDays, Layers, Radar, Satellite } from 'lucide-react';
import type { SceneDate, Source } from '@/types/api';

interface CommandPaletteProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    sources: Source[] | undefined;
    activeSourceId: string | undefined;
    dates: SceneDate[] | undefined;
    onSelectSource: (sourceId: string) => void;
    onSelectDate: (date: string) => void;
    onToggleLayers: () => void;
}

/**
 * ⌘K / Ctrl-K command palette to jump between imagery sources and acquisition
 * dates without reaching for the panels. Built on `cmdk` (Radix Dialog under the
 * hood, so focus-trap/ARIA come for free) and styled with the CIDSA glass-card
 * surface. Geocoded "places" search is intentionally out of scope until a
 * geocoder exists; this covers sources, dates, and panel actions.
 */
export function CommandPalette({
    open,
    onOpenChange,
    sources,
    activeSourceId,
    dates,
    onSelectSource,
    onSelectDate,
    onToggleLayers,
}: CommandPaletteProps) {
    const selectableDates = (dates ?? []).filter((d) => d.tileAvailable);

    return (
        <Dialog.Root open={ open } onOpenChange={ onOpenChange }>
            <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 z-modal bg-background/60 backdrop-blur-sm animate-fade-in" />
                <Dialog.Content
                    aria-label="Command palette"
                    className="glass fixed left-1/2 top-[18vh] z-modal w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-lg p-0 animate-panel-in"
                >
                    <VisuallyHidden>
                        <Dialog.Title>Command palette</Dialog.Title>
                        <Dialog.Description>
                            Search and jump between imagery sources, acquisition dates, and panel actions.
                        </Dialog.Description>
                    </VisuallyHidden>
                    <Command label="Command palette">
                        <div data-testid="command-palette">
                            <div className="flex items-center gap-2 border-b border-border/60 px-3">
                                <Command.Input
                                    placeholder="Search sources, dates, actions…"
                                    data-testid="command-input"
                                    className="h-12 w-full bg-transparent text-[14px] text-foreground placeholder:text-muted-foreground focus:outline-none"
                                />
                            </div>

                            <Command.List className="p-1.5">
                                <Command.Empty>No matches.</Command.Empty>

                                { sources && sources.length > 0 && (
                                    <Command.Group heading="Sources">
                                        { sources.map((source) => (
                                            <Command.Item
                                                key={ source.id }
                                                value={ `source ${source.label} ${source.provider}` }
                                                data-testid={ `command-source-${source.id}` }
                                                onSelect={ () => {
                                                    onSelectSource(source.id);
                                                    onOpenChange(false);
                                                } }
                                            >
                                                { source.kind === 'sar' ? (
                                                    <Radar className="size-4 shrink-0 text-muted-foreground" strokeWidth={ 1.75 } />
                                                ) : (
                                                    <Satellite className="size-4 shrink-0 text-muted-foreground" strokeWidth={ 1.75 } />
                                                ) }
                                                <span className="flex-1 truncate">{ source.label }</span>
                                                { source.id === activeSourceId && (
                                                    <span className="text-[11px] font-medium text-primary">Active</span>
                                                ) }
                                            </Command.Item>
                                        )) }
                                    </Command.Group>
                                ) }

                                { selectableDates.length > 0 && (
                                    <Command.Group heading="Dates">
                                        { selectableDates.map((date) => (
                                            <Command.Item
                                                key={ date.acquisitionDate }
                                                value={ `date ${date.acquisitionDate}` }
                                                data-testid={ `command-date-${date.acquisitionDate}` }
                                                onSelect={ () => {
                                                    onSelectDate(date.acquisitionDate);
                                                    onOpenChange(false);
                                                } }
                                            >
                                                <CalendarDays className="size-4 shrink-0 text-muted-foreground" strokeWidth={ 1.75 } />
                                                <span className="flex-1 font-mono text-[13px] tabular-nums">
                                                    { date.acquisitionDate }
                                                </span>
                                                { date.isLatestUsable && (
                                                    <span className="text-[11px] font-medium text-primary">Latest</span>
                                                ) }
                                            </Command.Item>
                                        )) }
                                    </Command.Group>
                                ) }

                                <Command.Group heading="Actions">
                                    <Command.Item
                                        value="action toggle layers panel"
                                        data-testid="command-toggle-layers"
                                        onSelect={ () => {
                                            onToggleLayers();
                                            onOpenChange(false);
                                        } }
                                    >
                                        <Layers className="size-4 shrink-0 text-muted-foreground" strokeWidth={ 1.75 } />
                                        <span className="flex-1">Toggle layers panel</span>
                                    </Command.Item>
                                </Command.Group>
                            </Command.List>

                            <div className="flex items-center justify-end gap-2 border-t border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground">
                                <kbd className="rounded bg-secondary px-1.5 py-0.5 font-mono">↑↓</kbd>
                                <span>navigate</span>
                                <kbd className="rounded bg-secondary px-1.5 py-0.5 font-mono">↵</kbd>
                                <span>select</span>
                                <kbd className="rounded bg-secondary px-1.5 py-0.5 font-mono">esc</kbd>
                                <span>close</span>
                            </div>
                        </div>
                    </Command>
                </Dialog.Content>
            </Dialog.Portal>
        </Dialog.Root>
    );
}
