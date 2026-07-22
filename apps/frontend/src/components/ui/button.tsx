import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-pill font-sans text-[13px] font-semibold leading-none tracking-[0.005em] ring-offset-background transition-[background-color,color,border-color,box-shadow,transform] duration-fast ease-standard focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        primary:
          'bg-linear-to-br from-cidsa-primary to-cidsa-primary-dark text-white shadow-e1 hover:-translate-y-0.5 hover:shadow-[0_10px_24px_rgb(22_163_74/0.25)] active:translate-y-0 active:scale-[0.98]',
        secondary:
          'border border-border bg-transparent text-foreground hover:border-primary/45 hover:bg-primary/5 active:scale-[0.98]',
        ghost: 'text-foreground hover:bg-accent hover:text-accent-foreground',
        outline:
          'border border-border bg-background/70 text-foreground hover:border-primary/40 hover:bg-primary/5 hover:text-primary',
        destructive:
          'bg-destructive text-destructive-foreground shadow-e1 hover:-translate-y-0.5 hover:bg-destructive/90 active:translate-y-0 active:scale-[0.98]',
      },
      size: {
        sm: 'h-[30px] px-2.5',
        md: 'h-9 px-4',
        lg: 'h-11 px-6 text-sm',
        icon: 'h-9 w-9',
        'icon-sm': 'h-8 w-8',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
  VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp className={ cn(buttonVariants({ variant, size, className })) } ref={ ref } { ...props } />
    );
  },
);
Button.displayName = 'Button';
