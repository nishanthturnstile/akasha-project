import * as React from 'react';
import { CalendarIcon, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface DatePickerProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
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

export function DatePicker({
  value,
  onChange,
  placeholder = 'Pick a date',
  disabled = false,
  className,
}: DatePickerProps) {
  const [open, setOpen] = React.useState(false);
  const [viewDate, setViewDate] = React.useState(() => {
    if (value) {
      const [y, m] = value.split('-');
      return { year: Number(y), month: Number(m) - 1 };
    }
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });
  const wrapperRef = React.useRef<HTMLDivElement>(null);

  // Close on outside click / Escape
  React.useEffect(() => {
    if (!open) return undefined;
    const onPointer = (event: PointerEvent) => {
      const node = wrapperRef.current;
      if (node && event.target instanceof Node && !node.contains(event.target)) {
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

  const handleSelect = (day: number) => {
    const month = String(viewDate.month + 1).padStart(2, '0');
    const dayStr = String(day).padStart(2, '0');
    const iso = `${viewDate.year}-${month}-${dayStr}`;
    onChange(iso);
    setOpen(false);
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

  return (
    <div ref={wrapperRef} className={cn('relative', className)}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          'flex h-9 w-full items-center justify-between rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground shadow-sm transition-colors',
          'hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          disabled && 'cursor-not-allowed opacity-50',
          !value && 'text-muted-foreground',
        )}
      >
        <span>{value ? formatDate(value) : placeholder}</span>
        <CalendarIcon className="size-4 text-muted-foreground" />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Pick a date"
          className="absolute top-full left-0 z-50 mt-1 w-70 rounded-md border border-border bg-popover p-3 shadow-e2"
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-3">
            <button
              type="button"
              onClick={handlePrevMonth}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
            >
              <ChevronLeft className="size-4" />
            </button>
            <span className="text-sm font-medium text-foreground">
              {MONTHS[viewDate.month]} {viewDate.year}
            </span>
            <button
              type="button"
              onClick={handleNextMonth}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
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
              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => handleSelect(day)}
                  className={cn(
                    'h-8 w-8 rounded-md text-sm flex items-center justify-center transition-colors',
                    selected
                      ? 'bg-primary text-primary-foreground font-medium'
                      : today
                        ? 'border border-primary/50 text-foreground font-medium'
                        : 'text-foreground hover:bg-accent',
                  )}
                >
                  {day}
                </button>
              );
            })}
          </div>

          {/* Footer */}
          <div className="mt-3 flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setOpen(false)}
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
                  setOpen(false);
                }}
                className="h-7 px-2 text-[12px] text-destructive hover:text-destructive"
              >
                Clear
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
