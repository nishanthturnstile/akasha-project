import { useQuery } from '@tanstack/react-query';
import { getConfig, getDates, getDefaultLayer, getSources } from '@/lib/api';

export const queryKeys = {
  config: ['config'] as const,
  sources: ['sources'] as const,
  dates: (sourceId: string) => ['dates', sourceId] as const,
  defaultLayer: ['layers', 'default'] as const,
};

export function useConfig() {
  return useQuery({ queryKey: queryKeys.config, queryFn: getConfig });
}

export function useSources() {
  return useQuery({ queryKey: queryKeys.sources, queryFn: getSources });
}

export function useDates(sourceId: string | undefined) {
  return useQuery({
    queryKey: sourceId ? queryKeys.dates(sourceId) : (['dates', 'none'] as const),
    queryFn: () => getDates(sourceId as string),
    enabled: Boolean(sourceId),
  });
}

export function useDefaultLayer() {
  return useQuery({ queryKey: queryKeys.defaultLayer, queryFn: getDefaultLayer });
}
