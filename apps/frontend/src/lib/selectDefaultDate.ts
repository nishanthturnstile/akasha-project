import type { SceneDate, SourceKind } from '@/types/api';

interface SelectDefaultDateOptions {
  sourceKind?: SourceKind;
}

/**
 * Choose the default-selected acquisition date.
 * Precedence:
 *   1) the date flagged `isLatestUsable`
 *   2) else the newest date with usablePixelPercent >= threshold
 *   3) else the newest date (caller surfaces the marginal/empty state)
 * Returns null only for an empty list.
 */
export function selectDefaultDate(
  dates: SceneDate[],
  thresholdPercent: number,
  options: SelectDefaultDateOptions = {},
): SceneDate | null {
  if (!dates || dates.length === 0) return null;

  const selectable = dates.filter((d) => d.tileAvailable);
  const candidates = selectable.length > 0 ? selectable : dates;
  const newestFirst = [...candidates].sort((a, b) =>
    b.acquisitionDate.localeCompare(a.acquisitionDate),
  );

  const latestUsable = newestFirst.find((d) => d.isLatestUsable);
  if (latestUsable) return latestUsable;

  if (options.sourceKind === 'sar') return newestFirst[0];

  const overThreshold = newestFirst.find(
    (d) => d.usablePixelPercent != null && d.usablePixelPercent >= thresholdPercent,
  );
  if (overThreshold) return overThreshold;

  return newestFirst[0];
}
