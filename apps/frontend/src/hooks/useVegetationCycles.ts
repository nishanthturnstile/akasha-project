import { useCallback, useSyncExternalStore } from 'react';

export interface VegetationCycleForm {
  id: string;
  cropName: string;
  plantingDate: string;
  irrigationType: string;
  targetYield: number | null;
  harvestingDate: string;
  tillageType: string;
  actualYield: number | null;
  notes: string;
}

const EMPTY_CYCLES: Record<string, VegetationCycleForm[]> = Object.freeze({});

function createVegCycleStore() {
  const store = new Map<string, Record<string, VegetationCycleForm[]>>();
  const listeners = new Set<() => void>();

  function emit() {
    for (const l of listeners) l();
  }

  return {
    get(fieldId: string): Record<string, VegetationCycleForm[]> {
      return store.get(fieldId) ?? EMPTY_CYCLES;
    },
    set(fieldId: string, cycles: Record<string, VegetationCycleForm[]>) {
      if (Object.keys(cycles).length === 0) {
        store.delete(fieldId);
      } else {
        store.set(fieldId, cycles);
      }
      emit();
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
  };
}

const vegCycleStore = createVegCycleStore();

export function useVegetationCycles(fieldId: string) {
  const cycles = useSyncExternalStore(
    vegCycleStore.subscribe,
    useCallback(() => vegCycleStore.get(fieldId), [fieldId]),
  );

  const addCycle = useCallback((seasonId: string) => {
    const newCycle: VegetationCycleForm = {
      id: crypto.randomUUID(),
      cropName: '',
      plantingDate: '',
      irrigationType: '',
      targetYield: null,
      harvestingDate: '',
      tillageType: '',
      actualYield: null,
      notes: '',
    };
    const current = vegCycleStore.get(fieldId);
    vegCycleStore.set(fieldId, {
      ...current,
      [seasonId]: [...(current[seasonId] ?? []), newCycle],
    });
  }, [fieldId]);

  const removeCycle = useCallback((seasonId: string, cycleId: string) => {
    const current = vegCycleStore.get(fieldId);
    vegCycleStore.set(fieldId, {
      ...current,
      [seasonId]: (current[seasonId] ?? []).filter((c) => c.id !== cycleId),
    });
  }, [fieldId]);

  const updateCycle = useCallback(
    (seasonId: string, cycleId: string, key: keyof VegetationCycleForm, value: string | number | null) => {
      const current = vegCycleStore.get(fieldId);
      vegCycleStore.set(fieldId, {
        ...current,
        [seasonId]: (current[seasonId] ?? []).map((c) =>
          c.id === cycleId ? { ...c, [key]: value } : c,
        ),
      });
    },
    [fieldId],
  );

  const clearSeasonCycles = useCallback((seasonId: string) => {
    const current = vegCycleStore.get(fieldId);
    const rest: Record<string, VegetationCycleForm[]> = {};
    for (const key of Object.keys(current)) {
      if (key !== seasonId) rest[key] = current[key];
    }
    vegCycleStore.set(fieldId, rest);
  }, [fieldId]);

  return { cycles, addCycle, removeCycle, updateCycle, clearSeasonCycles } as const;
}
