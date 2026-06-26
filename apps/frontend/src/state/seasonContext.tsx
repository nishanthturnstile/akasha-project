import { createContext, useContext, type ReactNode } from 'react';

export interface SeasonContextValue {
  seasonId: string | null;
}

const SeasonContext = createContext<SeasonContextValue | null>(null);

export function useSeasonContext(): SeasonContextValue {
  const ctx = useContext(SeasonContext);
  if (!ctx) return { seasonId: null };
  return ctx;
}

export function SeasonProvider({ seasonId, children }: { seasonId: string | null; children: ReactNode }) {
  return <SeasonContext.Provider value={{ seasonId }}>{children}</SeasonContext.Provider>;
}

export { SeasonContext };
