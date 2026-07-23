/**
 * Runtime colors passed to MapLibre/Terra Draw cannot consume Tailwind classes.
 * Keep them centralized here and separate from canonical scientific index ramps.
 */
export const MAP_UI_COLORS = {
  brand: '#16a34a',
  selection: '#3b82f6',
  selectionOutline: '#2563eb',
  boundaryOutline: '#1d4ed8',
  neutralFill: '#1f2937',
  neutralOutline: '#9ca3af',
  destructive: '#dc2626',
  white: '#ffffff',
  handle: '#f59e0b',
} as const;
