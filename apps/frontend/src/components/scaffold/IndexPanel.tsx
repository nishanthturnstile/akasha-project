import { BarChart3 } from 'lucide-react';

/**
 * Phase 5 placeholder. Reserves the right anchor for the NDVI/NDRE/NDMI/NDWI index
 * statistics panel. No behaviour is implemented.
 */
export function IndexPanel() {
  return (
    <section
      className="glass w-[280px] max-w-[80vw] overflow-hidden opacity-90"
      data-testid="index-panel"
      aria-label="Index analysis (available in Phase 5)"
    >
      <header className="contour flex items-center gap-2 px-4 py-3">
        <BarChart3 className="size-4 text-muted-foreground" strokeWidth={1.75} />
        <h2 className="font-display text-base font-semibold tracking-[-0.01em] text-muted-foreground">
          Index analysis
        </h2>
      </header>
      <div className="px-4 pb-4 pt-1">
        <p className="text-[13px] leading-5 text-muted-foreground">
          Draw or select a plot to compute NDVI, NDRE, NDMI and NDWI statistics.
        </p>
        <p className="mt-2 text-[12px] text-muted-foreground/70">Coming in Phase 5.</p>
      </div>
    </section>
  );
}
