import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { DiscoveryFilters, DiscoverySort } from '@/types/api';

type DiscoveryNamespace = 'monitoring' | 'scouting';
const PREFIX: Record<DiscoveryNamespace, string> = {
  monitoring: 'mon',
  scouting: 'scout',
};
const SORTS = new Set<DiscoverySort>([
  'name_asc',
  'name_desc',
  'newest',
  'oldest',
  'area_asc',
  'area_desc',
]);

function positiveInt(value: string | null, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

export function useDiscoveryUrlState(
  namespace: DiscoveryNamespace,
  seasonId: string | null,
  defaultStatus?: 'new' | 'closed',
) {
  const [params, setParams] = useSearchParams();
  const prefix = PREFIX[namespace];
  const key = useCallback((name: string) => `${prefix}${name}`, [prefix]);

  const filters = useMemo<DiscoveryFilters | null>(() => {
    if (!seasonId) return null;
    const rawSort = params.get(key('Sort')) as DiscoverySort | null;
    const rawStatus = params.get(key('Status'));
    return {
      seasonId,
      q: params.get(key('Q')) ?? '',
      cropIds: params
        .getAll(key('Crop'))
        .map(Number)
        .filter((value) => Number.isInteger(value)),
      groupIds: params.getAll(key('Group')),
      includeUngrouped: params.get(key('Ungrouped')) === '1',
      sort: rawSort && SORTS.has(rawSort) ? rawSort : 'name_asc',
      page: positiveInt(params.get(key('Page')), 1),
      pageSize: 20,
      status:
        namespace === 'scouting'
          ? rawStatus === 'closed'
            ? 'closed'
            : rawStatus === 'new'
              ? 'new'
              : defaultStatus
          : undefined,
    };
  }, [defaultStatus, key, namespace, params, seasonId]);

  const update = useCallback(
    (patch: Partial<DiscoveryFilters>, options?: { keepPage?: boolean }) => {
      setParams((current) => {
        const next = new URLSearchParams(current);
        const setRepeated = (name: string, values: Array<string | number>) => {
          next.delete(key(name));
          for (const value of values) next.append(key(name), String(value));
        };
        if ('q' in patch) {
          if (patch.q) next.set(key('Q'), patch.q);
          else next.delete(key('Q'));
        }
        if ('cropIds' in patch) setRepeated('Crop', patch.cropIds ?? []);
        if ('groupIds' in patch) setRepeated('Group', patch.groupIds ?? []);
        if ('includeUngrouped' in patch) {
          if (patch.includeUngrouped) next.set(key('Ungrouped'), '1');
          else next.delete(key('Ungrouped'));
        }
        if ('sort' in patch) {
          if (patch.sort && patch.sort !== 'name_asc') next.set(key('Sort'), patch.sort);
          else next.delete(key('Sort'));
        }
        if ('status' in patch && namespace === 'scouting') {
          if (patch.status) next.set(key('Status'), patch.status);
          else next.delete(key('Status'));
        }
        if ('page' in patch) {
          if (patch.page && patch.page > 1) next.set(key('Page'), String(patch.page));
          else next.delete(key('Page'));
        } else if (!options?.keepPage) {
          next.delete(key('Page'));
        }
        return next;
      }, { replace: true });
    },
    [key, namespace, setParams],
  );

  return { filters, update };
}
