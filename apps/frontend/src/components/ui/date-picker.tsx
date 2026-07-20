import * as React from 'react';
import { createPortal } from 'react-dom';
import { CalendarIcon, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface DatePickerHandle {
  open: () => void;
  setViewDate: (year: number, month: number) => void;
}

export interface DateRange {
  start: string;
  end: string;
}

interface DatePickerProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  minDate?: string;
  maxDate?: string;
  onOpenChange?: (open: boolean) => void;
  overlapRanges?: DateRange[];
  blockedRanges?: DateRange[];
  showLegend?: boolean;
}

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const DAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month, 1).getDay();
}

function formatDate(isoDate: string): string {
  if (!isoDate) return '';
  const [y, m, d] = isoDate.split('-');
  const date = new Date(Number(y), Number(m) - 1, Number(d));
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export const DatePicker = React.forwardRef<DatePickerHandle, DatePickerProps>(function DatePicker({
  value,
  onChange,
  placeholder = 'Pick a date',
  disabled = false,
  className,
  minDate,
  maxDate,
  onOpenChange,
  overlapRanges,
  blockedRanges,
  showLegend = false,
}, ref) {
  const hasLegend = showLegend && (!!minDate || !!maxDate || (overlapRanges && overlapRanges.length > 0));
  const [open, setOpen] = React.useState(false);

  const handleOpenChange = React.useCallback((next: boolean) => {
    setOpen(next);
    onOpenChange?.(next);
  }, [onOpenChange]);

  const [viewDate, setViewDate] = React.useState(() => {
    if (value) {
      const [y, m] = value.split('-');
      return { year: Number(y), month: Number(m) - 1 };
    }
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });

  React.useImperativeHandle(ref, () => ({
    open: () => handleOpenChange(true),
    setViewDate: (year: number, month: number) => setViewDate({ year, month }),
  }), [handleOpenChange]);

  const wrapperRef = React.useRef<HTMLDivElement>(null);
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const calendarRef = React.useRef<HTMLDivElement>(null);

  // Close on outside click / Escape
  React.useEffect(() => {
    if (!open) return undefined;
    const onPointer = (event: PointerEvent) => {
      const node = wrapperRef.current;
      const cal = calendarRef.current;
      if (
        node &&
        event.target instanceof Node &&
        !node.contains(event.target) &&
        (!cal || !cal.contains(event.target))
      ) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('pointerdown', onPointer);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('pointerdown', onPointer);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  // Recalculate fixed position when opened, close on scroll
  const [fixedStyle, setFixedStyle] = React.useState<React.CSSProperties>({});
  React.useEffect(() => {
    if (!open) return;
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) {
      setFixedStyle({
        top: rect.bottom + 4,
        left: rect.left,
        minWidth: Math.max(rect.width, 280),
      });
    }
    const onScroll = () => setOpen(false);
    window.addEventListener('scroll', onScroll, true);
    return () => {
      window.removeEventListener('scroll', onScroll, true);
    };
  }, [open]);

  // Sync view date when value changes from outside
  React.useEffect(() => {
    if (value) {
      const [y, m] = value.split('-');
      setViewDate({ year: Number(y), month: Number(m) - 1 });
    }
  }, [value]);

  const daysInMonth = getDaysInMonth(viewDate.year, viewDate.month);
  const firstDay = getFirstDayOfMonth(viewDate.year, viewDate.month);
  const prevMonthDays = getDaysInMonth(viewDate.year, viewDate.month - 1);

  const handlePrevMonth = () => {
    setViewDate((prev) => {
      if (prev.month === 0) return { year: prev.year - 1, month: 11 };
      return { year: prev.year, month: prev.month - 1 };
    });
  };

  const handleNextMonth = () => {
    setViewDate((prev) => {
      if (prev.month === 11) return { year: prev.year + 1, month: 0 };
      return { year: prev.year, month: prev.month + 1 };
    });
  };

  const dayButtonClass = 'h-8 w-8 rounded-md text-sm flex items-center justify-center transition-colors';

  const prevDisabled = React.useMemo(() => {
    if (!minDate) return false;
    const prevMonthLastDay = new Date(viewDate.year, viewDate.month, 0);
    const min = new Date(minDate + 'T00:00:00');
    return prevMonthLastDay < min;
  }, [minDate, viewDate]);

  const nextDisabled = React.useMemo(() => {
    if (!maxDate) return false;
    const nextMonthFirstDay = new Date(viewDate.year, viewDate.month + 1, 1);
    const max = new Date(maxDate + 'T00:00:00');
    return nextMonthFirstDay > max;
  }, [maxDate, viewDate]);

  const isDisabled = (day: number) => {
    const date = new Date(viewDate.year, viewDate.month, day);
    if (minDate) {
      const min = new Date(minDate + 'T00:00:00');
      if (date < min) return true;
    }
    if (maxDate) {
      const max = new Date(maxDate + 'T00:00:00');
      if (date > max) return true;
    }
    return false;
  };

  const isOverlapDay = (day: number): boolean => {
    if (!overlapRanges?.length) return false;
    const month = String(viewDate.month + 1).padStart(2, '0');
    const dayStr = String(day).padStart(2, '0');
    const dateStr = `${viewDate.year}-${month}-${dayStr}`;
    return overlapRanges.some((r) => dateStr >= r.start && dateStr <= r.end);
  };

  const isBlockedDay = (day: number): boolean => {
    if (!blockedRanges?.length) return false;
    const month = String(viewDate.month + 1).padStart(2, '0');
    const dayStr = String(day).padStart(2, '0');
    const dateStr = `${viewDate.year}-${month}-${dayStr}`;
    return blockedRanges.some((r) => dateStr >= r.start && dateStr <= r.end);
  };

  const handleSelect = (day: number) => {
    if (isDisabled(day)) return;
    const month = String(viewDate.month + 1).padStart(2, '0');
    const dayStr = String(day).padStart(2, '0');
    const iso = `${viewDate.year}-${month}-${dayStr}`;
    onChange(iso);
    handleOpenChange(false);
  };

  const isSelected = (day: number) => {
    if (!value) return false;
    const month = String(viewDate.month + 1).padStart(2, '0');
    const dayStr = String(day).padStart(2, '0');
    return value === `${viewDate.year}-${month}-${dayStr}`;
  };

  const isToday = (day: number) => {
    const now = new Date();
    return (
      now.getDate() === day &&
      now.getMonth() === viewDate.month &&
      now.getFullYear() === viewDate.year
    );
  };

  const calendarContent = (
    <div
      ref={calendarRef}
      role="dialog"
      aria-label="Pick a date"
      className="fixed z-[999] rounded-md border border-border bg-popover p-3 shadow-e2 pointer-events-auto"
      style={fixedStyle}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <button
          type="button"
          disabled={prevDisabled}
          onClick={handlePrevMonth}
          className={cn(
            'inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors',
            prevDisabled
              ? 'cursor-not-allowed text-muted-foreground/30'
              : 'hover:bg-accent text-muted-foreground hover:text-foreground',
          )}
        >
          <ChevronLeft className="size-4" />
        </button>
        <span className="text-sm font-medium text-foreground">
          {MONTHS[viewDate.month]} {viewDate.year}
        </span>
        <button
          type="button"
          disabled={nextDisabled}
          onClick={handleNextMonth}
          className={cn(
            'inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors',
            nextDisabled
              ? 'cursor-not-allowed text-muted-foreground/30'
              : 'hover:bg-accent text-muted-foreground hover:text-foreground',
          )}
        >
          <ChevronRight className="size-4" />
        </button>
      </div>

      {/* Day headers */}
      <div className="grid grid-cols-7 mb-1">
        {DAYS.map((d) => (
          <div
            key={d}
            className="text-center text-[11px] font-medium text-muted-foreground py-1"
          >
            {d}
          </div>
        ))}
      </div>

      {/* Days grid */}
      <div className="grid grid-cols-7 gap-0.5">
        {/* Previous month padding */}
        {Array.from({ length: firstDay }, (_, i) => {
          const day = prevMonthDays - firstDay + i + 1;
          return (
            <button
              key={`prev-${i}`}
              type="button"
              disabled
              className="h-8 w-8 rounded-md text-sm text-muted-foreground/40 flex items-center justify-center"
            >
              {day}
            </button>
          );
        })}

        {/* Current month days */}
        {Array.from({ length: daysInMonth }, (_, i) => {
          const day = i + 1;
          const selected = isSelected(day);
          const today = isToday(day);
          const outsideSeason = isDisabled(day);
          const overlap = !outsideSeason && isOverlapDay(day);
          const blocked = !outsideSeason && !overlap && isBlockedDay(day);
          return (
            <button
              key={day}
              type="button"
              disabled={outsideSeason || overlap || blocked}
              onClick={() => handleSelect(day)}
              className={cn(
                dayButtonClass,
                outsideSeason && 'cursor-not-allowed text-muted-foreground/40',
                overlap && 'cursor-not-allowed text-amber-600/50',
                blocked && 'cursor-not-allowed text-muted-foreground/40',
                !outsideSeason && !overlap && !blocked && selected && 'bg-primary text-primary-foreground font-medium',
                !outsideSeason && !overlap && !blocked && !selected && today && 'border border-primary/50 text-foreground font-medium',
                !outsideSeason && !overlap && !blocked && !selected && !today && 'text-foreground hover:bg-accent',
              )}
            >
              {day}
            </button>
          );
        })}
      </div>

      {/* Legend */}
      {hasLegend && (
        <div className="border-t border-border/60 pt-2 pb-1 space-y-1">
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <span className="inline-block size-3 rounded-full bg-muted-foreground/40" />
            Dates are outside your season
          </div>
          {overlapRanges && overlapRanges.length > 0 && (
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span className="inline-block size-3 rounded-full bg-amber-600/50" />
              Dates overlap with another crop
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="flex justify-end gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => handleOpenChange(false)}
          className="h-7 px-2 text-[12px]"
        >
          Cancel
        </Button>
        {value && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              onChange('');
              handleOpenChange(false);
            }}
            className="h-7 px-2 text-[12px] text-destructive hover:text-destructive"
          >
            Clear
          </Button>
        )}
      </div>
    </div>
  );

  return (
    <div ref={wrapperRef} className={cn('relative', className)}>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        onClick={() => handleOpenChange(!open)}
        className={cn(
          'flex h-9 w-full cursor-pointer items-center justify-between rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground shadow-sm transition-colors',
          'hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          disabled && 'cursor-not-allowed opacity-50',
          !value && 'text-muted-foreground',
        )}
      >
        <span>{value ? formatDate(value) : placeholder}</span>
        <CalendarIcon className="size-4 text-muted-foreground" />
      </button>

      {open ? (createPortal(calendarContent, document.body) as React.ReactNode) : null}
    </div>
  );
});
