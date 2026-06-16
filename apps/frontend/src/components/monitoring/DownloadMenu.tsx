import { useState } from 'react';
import type { ReactNode } from 'react';
import { Download, FileArchive, FileDown, FileText, ImageDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useExportFieldIndex, useExportFieldReportCsv } from '@/lib/queries';
import type { CloudMaskOptions, FileDownload, Plot } from '@/types/api';

interface DownloadMenuProps {
  selectedPlot: Plot | null;
  selectedDate: string | null;
  displayMode: string;
  sourceId: string | undefined;
  indexType: string;
  cloudMask: CloudMaskOptions;
  analyticsEnabled?: boolean;
}

function isIndexMode(mode: string): boolean {
  return ![
    'RGB',
    'FCC',
    'CONTEXT',
    'NDVI_CONTEXT',
    'FALSE_COLOR',
    'FALSE_COLOR_URBAN',
    'VV_GRAYSCALE',
    'VH_GRAYSCALE',
  ].includes(mode.toUpperCase());
}

function downloadFile(file: FileDownload): void {
  const url = URL.createObjectURL(file.blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = file.filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function DownloadMenu({
  selectedPlot,
  selectedDate,
  displayMode,
  sourceId,
  indexType,
  cloudMask,
  analyticsEnabled = true,
}: DownloadMenuProps) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const indexExport = useExportFieldIndex();
  const reportExport = useExportFieldReportCsv();

  const disabledReason = !selectedPlot
    ? 'Select a field to download map outputs.'
    : !selectedDate
      ? 'Select a scene date to download map outputs.'
      : null;
  const fieldId = selectedPlot?.id;
  const canExportField = Boolean(analyticsEnabled && fieldId && selectedDate && sourceId);
  const nativeGeoTiffAvailable = false;
  const canExportTiff = Boolean(canExportField && isIndexMode(displayMode) && nativeGeoTiffAvailable);
  const busy = indexExport.isPending || reportExport.isPending;

  const exportIndex = async (format: 'geotiff' | 'geojson') => {
    if (!fieldId || !selectedDate || !sourceId) return;
    setError(null);
    try {
      const file = await indexExport.mutateAsync({
        plotId: fieldId,
        options: {
          format,
          sourceId,
          acquisitionDate: selectedDate,
          indexType,
          cloudMask,
        },
      });
      downloadFile(file);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed.');
    }
  };

  const exportAnalyticsCsv = async () => {
    if (!fieldId || !selectedDate || !sourceId) return;
    setError(null);
    try {
      const file = await reportExport.mutateAsync({
        plotId: fieldId,
        options: {
          sourceId,
          indexType,
          startDate: selectedDate,
          endDate: selectedDate,
          cloudMask,
        },
      });
      downloadFile(file);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed.');
    }
  };

  return (
    <div className="flex flex-col items-end gap-2" data-testid="download-menu">
      { open && (
        <div className="glass w-60 rounded-md p-3" data-testid="download-menu-panel">
          <p className="mb-2 text-[12px] font-semibold text-foreground">
            { indexType } · { selectedDate ?? 'No date' }
          </p>
          <div className="flex flex-col gap-1">
            <DownloadButton
              id="index-tiff"
              label="Index GeoTIFF"
              icon={<ImageDown className="size-3.5" />}
              disabled={ !canExportTiff || busy }
              reason={
                canExportTiff
                  ? undefined
                  : 'Native GeoTIFF export is not available yet.'
              }
              onClick={ () => void exportIndex('geotiff') }
            />
            <DownloadButton
              id="analytics-csv"
              label="Analytics CSV"
              icon={<FileText className="size-3.5" />}
              disabled={ !canExportField || busy }
              reason={ analyticsEnabled ? disabledReason ?? undefined : 'Analytics are not enabled for this source.' }
              onClick={ () => void exportAnalyticsCsv() }
            />
            <DownloadButton
              id="field-geojson"
              label="Field GeoJSON"
              icon={<FileDown className="size-3.5" />}
              disabled={ !canExportField || busy }
              reason={ analyticsEnabled ? disabledReason ?? undefined : 'Analytics are not enabled for this source.' }
              onClick={ () => void exportIndex('geojson') }
            />
            <DownloadButton
              id="index-shp"
              label="Index SHP"
              icon={<FileArchive className="size-3.5" />}
              disabled
              reason="Available after native vector exports."
            />
            <DownloadButton
              id="contours-shp"
              label="Contours SHP"
              icon={<FileArchive className="size-3.5" />}
              disabled
              reason="Available after native vector exports."
            />
          </div>
          { disabledReason && (
            <p className="mt-2 text-[11px] leading-4 text-muted-foreground">{ disabledReason }</p>
          ) }
          { error && (
            <p className="mt-2 text-[11px] leading-4 text-destructive" data-testid="download-error">
              { error }
            </p>
          ) }
        </div>
      ) }
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label={ open ? 'Close downloads' : 'Open downloads' }
        aria-expanded={ open }
        onClick={ () => setOpen((current) => !current) }
        data-testid="download-menu-toggle"
        title="Downloads"
        className="glass size-9"
      >
        <Download className="size-5" strokeWidth={ 1.75 } />
      </Button>
    </div>
  );
}

interface DownloadButtonProps {
  id: string;
  label: string;
  icon: ReactNode;
  disabled: boolean;
  reason?: string;
  onClick?: () => void;
}

function DownloadButton({ id, label, icon, disabled, reason, onClick }: DownloadButtonProps) {
  return (
    <button
      type="button"
      disabled={ disabled }
      className="flex items-center justify-between rounded px-2 py-1.5 text-left text-[12px] text-foreground/85 transition-colors hover:bg-accent hover:text-accent-foreground disabled:text-muted-foreground disabled:opacity-65"
      data-testid={ `download-${id}` }
      title={ disabled ? reason : label }
      onClick={ onClick }
    >
      <span className="flex items-center gap-2">
        { icon }
        { label }
      </span>
      { disabled && reason && (
        <span className="max-w-[78px] truncate text-[10px] uppercase tracking-wide">Unavailable</span>
      ) }
    </button>
  );
}
