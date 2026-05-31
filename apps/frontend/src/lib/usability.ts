// Cloud-usability mapping (design-system §2.3):
//   >=70% -> success, 40-70% -> warning, <40% -> destructive, missing -> nodata.

export type UsabilityStatus = 'success' | 'warning' | 'destructive' | 'nodata';

export function usabilityStatus(percent: number | null | undefined): UsabilityStatus {
  if (percent == null || Number.isNaN(percent)) return 'nodata';
  if (percent >= 70) return 'success';
  if (percent >= 40) return 'warning';
  return 'destructive';
}

export const USABILITY_LABEL: Record<UsabilityStatus, string> = {
  success: 'Usable',
  warning: 'Marginal',
  destructive: 'Poor',
  nodata: 'No data',
};

/** Tailwind text/background token name fragment for the status colour. */
export const USABILITY_TOKEN: Record<UsabilityStatus, string> = {
  success: 'success',
  warning: 'warning',
  destructive: 'destructive',
  nodata: 'nodata',
};
