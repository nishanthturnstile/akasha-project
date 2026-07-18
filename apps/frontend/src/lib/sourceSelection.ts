import type { Source } from '@/types/api';

export function selectEffectiveSourceId({
  activeSourceId,
  defaultSourceId,
  sources,
}: {
  activeSourceId?: string;
  defaultSourceId?: string | null;
  sources?: Source[];
}): string | undefined {
  if (!sources || sources.length === 0) {
    return activeSourceId ?? defaultSourceId ?? undefined;
  }

  const primarySources = sources.filter((source) => source.productRole !== 'support');
  const hasSource = (sourceId: string | null | undefined) =>
    Boolean(sourceId && primarySources.some((source) => source.id === sourceId));

  if (hasSource(activeSourceId)) return activeSourceId;
  if (hasSource(defaultSourceId)) return defaultSourceId ?? undefined;
  return primarySources[0]?.id;
}
