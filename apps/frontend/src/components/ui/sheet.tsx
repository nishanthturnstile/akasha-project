import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { type ComponentPropsWithoutRef, type ElementRef, forwardRef } from 'react';
import { cn } from '@/lib/utils';

/* ── Sheet Root ──────────────────────────────────────────── */
const SheetRoot = Dialog.Root;
const SheetTrigger = Dialog.Trigger;
const SheetClose = Dialog.Close;
const SheetPortal = Dialog.Portal;

/* ── Sheet Overlay ───────────────────────────────────────── */
const SheetOverlay = forwardRef<
  ElementRef<typeof Dialog.Overlay>,
  ComponentPropsWithoutRef<typeof Dialog.Overlay>
>(({ className, ...props }, ref) => (
  <Dialog.Overlay
    ref={ref}
    className={cn(
      'fixed inset-0 z-popover bg-background/60 backdrop-blur-sm data-[state=open]:animate-fade-in data-[state=closed]:animate-fade-in',
      className,
    )}
    {...props}
  />
));
SheetOverlay.displayName = 'SheetOverlay';

/* ── Sheet Content ───────────────────────────────────────── */
interface SheetContentProps extends ComponentPropsWithoutRef<typeof Dialog.Content> {
  side?: 'left' | 'right';
}

const sideStyles: Record<string, string> = {
  right: 'inset-y-0 right-0 h-full w-full max-w-md border-l border-border translate-x-0 data-[state=closed]:translate-x-full',
  left: 'inset-y-0 left-0 h-full w-full max-w-md border-r border-border translate-x-0 data-[state=closed]:-translate-x-full',
};

const SheetContent = forwardRef<
  ElementRef<typeof Dialog.Content>,
  SheetContentProps
>(({ side = 'right', className, children, ...props }, ref) => (
  <SheetPortal>
    <SheetOverlay />
    <Dialog.Content
      ref={ref}
      className={cn(
        'fixed z-popover gap-4 bg-background p-0 shadow-e2 transition-transform duration-slow ease-decelerate',
        'data-[state=open]:animate-in',
        sideStyles[side],
        className,
      )}
      {...props}
    >
      {children}
      <Dialog.Close asChild>
        <button
          aria-label="Close"
          className="absolute right-4 top-4 rounded-md p-1 text-muted-foreground hover:bg-accent/40"
        >
          <X className="size-4" />
        </button>
      </Dialog.Close>
    </Dialog.Content>
  </SheetPortal>
));
SheetContent.displayName = 'SheetContent';

/* ── Sheet Header ────────────────────────────────────────── */
const SheetHeader = ({ className, ...props }: ComponentPropsWithoutRef<'div'>) => (
  <div className={cn('flex flex-col gap-1.5 border-b border-border/60 px-4 py-4', className)} {...props} />
);

/* ── Sheet Footer ────────────────────────────────────────── */
const SheetFooter = ({ className, ...props }: ComponentPropsWithoutRef<'div'>) => (
  <div className={cn('flex items-center justify-end gap-2 border-t border-border/60 px-4 py-3', className)} {...props} />
);

/* ── Sheet Title ─────────────────────────────────────────── */
const SheetTitle = forwardRef<
  ElementRef<typeof Dialog.Title>,
  ComponentPropsWithoutRef<typeof Dialog.Title>
>(({ className, ...props }, ref) => (
  <Dialog.Title ref={ref} className={cn('text-base font-display font-semibold text-foreground', className)} {...props} />
));
SheetTitle.displayName = 'SheetTitle';

/* ── Sheet Description ───────────────────────────────────── */
const SheetDescription = forwardRef<
  ElementRef<typeof Dialog.Description>,
  ComponentPropsWithoutRef<typeof Dialog.Description>
>(({ className, ...props }, ref) => (
  <Dialog.Description ref={ref} className={cn('text-sm text-muted-foreground', className)} {...props} />
));
SheetDescription.displayName = 'SheetDescription';

export {
  SheetRoot,
  SheetTrigger,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
  SheetPortal,
  SheetOverlay,
};
