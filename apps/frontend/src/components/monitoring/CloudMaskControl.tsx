import { Cloud } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import type { CloudMaskOptions } from '@/types/api';

interface CloudMaskControlProps {
  value: CloudMaskOptions;
  onChange: (value: CloudMaskOptions) => void;
  disabled?: boolean;
}

const OPTIONS: Array<{ key: keyof CloudMaskOptions; label: string }> = [
  { key: 'clouds', label: 'Clouds' },
  { key: 'cloudShadows', label: 'Shadows' },
  { key: 'cirrus', label: 'Cirrus' },
];

export function CloudMaskControl({ value, onChange, disabled = false }: CloudMaskControlProps) {
  return (
    <div className="glass flex w-44 flex-col gap-2 rounded-md p-3" data-testid="cloud-mask-control">
      <div className="flex items-center gap-2 text-[12px] font-semibold text-foreground">
        <Cloud className="size-4 text-primary" strokeWidth={ 1.75 } />
        Cloud mask
      </div>
      { OPTIONS.map((option) => (
        <label key={ option.key } className="flex items-center justify-between gap-2">
          <span className="text-[12px] text-muted-foreground">{ option.label }</span>
          <Switch
            checked={ value[option.key] }
            disabled={ disabled }
            onCheckedChange={ (checked) => onChange({ ...value, [option.key]: checked }) }
            data-testid={ `cloud-mask-${option.key}` }
            aria-label={ `Toggle ${option.label.toLowerCase()} mask` }
          />
        </label>
      )) }
    </div>
  );
}
