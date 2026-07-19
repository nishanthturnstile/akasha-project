const NISAR_SOURCE_ID = 'nisar-ssar-beta-gcov';

export function radarSensorLabel(sourceId: string | undefined): string {
  return sourceId === NISAR_SOURCE_ID ? 'NISAR S-band' : 'EOS-04';
}

export function radarEvidenceDescription(
  sourceId: string | undefined,
  acquisitionDate: string | undefined,
  displayedPolarization?: string,
): string {
  const polarization = displayedPolarization ? ` using ${displayedPolarization}` : '';
  return `${radarSensorLabel(sourceId)} radar evidence observed this field on ${acquisitionDate ?? 'an available pass'}${polarization}. It provides structural and moisture-sensitive evidence, not NDVI or a direct soil-moisture measurement.`;
}
