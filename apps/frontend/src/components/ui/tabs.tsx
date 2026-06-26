import * as React from 'react';
import * as TabsPrimitive from '@radix-ui/react-tabs';
import { cn } from '@/lib/utils';

export const Tabs = TabsPrimitive.Root;

export const TabsList = React.forwardRef<
    React.ElementRef<typeof TabsPrimitive.List>,
    React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
    <TabsPrimitive.List
        ref={ ref }
        className={ cn(
            'inline-flex h-9 items-center gap-1 rounded-md border border-border/60 bg-card/40 p-1 text-muted-foreground',
            className,
        ) }
        { ...props }
    />
));
TabsList.displayName = TabsPrimitive.List.displayName;

export const TabsTrigger = React.forwardRef<
    React.ElementRef<typeof TabsPrimitive.Trigger>,
    React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
    <TabsPrimitive.Trigger
        ref={ ref }
        className={ cn(
            'inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1 text-[12px] font-medium ring-offset-background transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
            'disabled:pointer-events-none disabled:opacity-50',
            'data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-e1',
            className,
        ) }
        { ...props }
    />
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

export const TabsContent = React.forwardRef<
    React.ElementRef<typeof TabsPrimitive.Content>,
    React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
    <TabsPrimitive.Content
        ref={ ref }
        className={ cn(
            'mt-3 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
            // Radix sets data-state="inactive" on non-active panels even when forceMount
            // keeps them mounted. Without this, forceMount panels (which are never given
            // the hidden attribute) would all render stacked and visible at once.
            'data-[state=inactive]:hidden',
            className,
        ) }
        { ...props }
    />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;
