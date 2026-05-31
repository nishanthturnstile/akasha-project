import { Switch } from '@/components/ui/switch';
import { Eye, EyeOff } from 'lucide-react';

interface VisibilityToggleProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}

export function VisibilityToggle({ checked, onCheckedChange }: VisibilityToggleProps) {
  return (
    <div className="flex items-center justify-between" data-testid="visibility-control">
      <span className="flex items-center gap-2 text-[13px] font-medium text-muted-foreground">
        {checked ? (
          <Eye className="size-4" strokeWidth={1.75} />
        ) : (
          <EyeOff className="size-4" strokeWidth={1.75} />
        )}
        Satellite layer
      </span>
      <Switch
        checked={checked}
        onCheckedChange={onCheckedChange}
        aria-label="Toggle satellite layer visibility"
        data-testid="visibility-toggle"
      />
    </div>
  );
}
