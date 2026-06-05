import { Slider } from '@/components/ui/slider';

interface OpacitySliderProps {
  /** 0..100 */
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
}

export function OpacitySlider({ value, onChange, disabled }: OpacitySliderProps) {
  return (
    <div className="flex flex-col gap-2" data-testid="opacity-control">
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-medium text-muted-foreground">Opacity</span>
        <span
          className="font-mono tnum text-[13px] text-foreground"
          data-testid="opacity-value"
        >
          {Math.round(value)}%
        </span>
      </div>
      <Slider
        value={[value]}
        min={0}
        max={100}
        step={1}
        disabled={disabled}
        onValueChange={(v) => onChange(v[0])}
        data-testid="opacity-slider"
      />
    </div>
  );
}
