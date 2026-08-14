import type { SceneDate, SourceKind } from '@/types/api';

interface SelectDefaultDateOptions {
  sourceKind?: SourceKind;
}

/**
 * Choose the default-selected acquisition date.
 * Precedence:
 *   1) the date flagged `isLatestUsable`
 *   2) else the newest date with usablePixelPercent >= threshold
 *   3) no qualifying date => null (caller surfaces the no-qualifying state)
 * SAR/context/archive sources use their newest selectable acquisition because
 * usable-pixel thresholds do not apply to those products.
 */
export function selectDefaultDate(
  dates: SceneDate[],
  thresholdPercent: number,
  options: SelectDefaultDateOptions = {},
): SceneDate | null {
  if (!dates || dates.length === 0) return null;

  const candidates = dates.filter((d) => d.selectable ?? d.tileAvailable !== false);
  if (candidates.length === 0) return null;
  const newestFirst = [...candidates].sort((a, b) =>
    b.acquisitionDate.localeCompare(a.acquisitionDate),
  );

  const latestUsable = newestFirst.find((d) => d.isLatestUsable);
  if (latestUsable) return latestUsable;

  // New availability responses already apply the account's combined quality
  // threshold. Once `selectable` is present, the newest selectable date is the
  // newest qualifying acquisition; do not re-interpret it with the legacy
  // usable-pixel threshold.
  if (dates.some((d) => d.selectable !== undefined)) return newestFirst[0];

  if (
    options.sourceKind === 'sar' ||
    options.sourceKind === 'context' ||
    options.sourceKind === 'archive'
  ) {
    return newestFirst[0];
  }

  const overThreshold = newestFirst.find(
    (d) => d.usablePixelPercent != null && d.usablePixelPercent >= thresholdPercent,
  );
  if (overThreshold) return overThreshold;

  return null;
}
