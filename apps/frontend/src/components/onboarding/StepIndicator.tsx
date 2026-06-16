import { CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface StepIndicatorProps {
  currentStep: number;
  totalSteps?: number;
  labels?: string[];
}

const DEFAULT_LABELS = ['Create season', 'Add field', 'Add crop'];

export function StepIndicator({ currentStep, totalSteps = 3, labels = DEFAULT_LABELS }: StepIndicatorProps) {
  return (
    <div className="flex items-center gap-4 mb-6">
      {Array.from({ length: totalSteps }, (_, i) => i + 1).map((num) => {
        const isCompleted = num < currentStep;
        const isActive = num === currentStep;
        return (
          <div key={num} className="flex flex-col items-center">
            <div
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded-full border-2 text-sm font-medium',
                isCompleted
                  ? 'border-primary bg-primary text-primary-foreground'
                  : isActive
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-muted-foreground text-muted-foreground',
              )}
            >
              {isCompleted ? <CheckCircle2 className="size-4" /> : num}
            </div>
            <span
              className={cn(
                'mt-1 text-xs',
                isActive ? 'text-primary font-medium' : isCompleted ? 'text-primary' : 'text-muted-foreground',
              )}
            >
              {labels[num - 1] ?? `Step ${num}`}
            </span>
            {num < totalSteps && <div className="h-px w-8 bg-muted-foreground mt-1" />}
          </div>
        );
      })}
    </div>
  );
}
