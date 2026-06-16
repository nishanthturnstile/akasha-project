import React from 'react';
import { CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface StepIndicatorProps {
  currentStep: number;
  totalSteps?: number;
  labels?: string[];
}

const DEFAULT_LABELS = ['Create season', 'Add field', 'Add crop'];

export function StepIndicator({ currentStep, totalSteps = 3, labels = DEFAULT_LABELS }: StepIndicatorProps) {
  const steps = Array.from({ length: totalSteps }, (_, i) => i + 1);
  return (
    <div className="inline-flex items-start mb-6">
      {steps.map((num, idx) => {
        const isCompleted = num < currentStep;
        const isActive = num === currentStep;
        const isLast = idx === steps.length - 1;
        return (
          <React.Fragment key={num}>
            <div className="flex flex-col items-center">
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
                  'mt-1 text-xs whitespace-nowrap',
                  isActive ? 'text-primary font-medium' : isCompleted ? 'text-primary' : 'text-muted-foreground',
                )}
              >
                {labels[num - 1] ?? `Step ${num}`}
              </span>
            </div>
            {!isLast && (
              <div className="flex items-center mx-3" style={{ height: '32px' }}>
                <div
                  className={cn(
                    'w-10 h-0.5 rounded-full',
                    isCompleted ? 'bg-primary' : 'bg-muted-foreground/60',
                  )}
                />
              </div>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}
