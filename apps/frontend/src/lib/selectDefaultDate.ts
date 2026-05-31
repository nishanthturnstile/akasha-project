import type { SceneDate } from '@/types/api';

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
): SceneDate | null {
  if (!dates || dates.length === 0) return null;

  const newestFirst = [...dates].sort((a, b) => b.acquisitionDate.localeCompare(a.acquisitionDate));

  const latestUsable = newestFirst.find((d) => d.isLatestUsable);
  if (latestUsable) return latestUsable;

  const overThreshold = newestFirst.find(
    (d) => d.usablePixelPercent != null && d.usablePixelPercent >= thresholdPercent,
  );
  if (overThreshold) return overThreshold;

  return newestFirst[0];
}
