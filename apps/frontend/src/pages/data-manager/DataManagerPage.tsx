import { useState } from 'react';
import { useDatasets, useUploadDataset } from '@/lib/queries';
import { reportErrorMessage } from '@/pages/reports/reportUtils';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { UploadedDataset } from '@/types/api';

export default function DataManagerPage() {
  const [datasetType, setDatasetType] = useState<UploadedDataset['datasetType']>('geojson');
  const datasetsQ = useDatasets();
  const uploadMutation = useUploadDataset();
  const error = datasetsQ.error ?? uploadMutation.error;

  async function onFile(file: File | undefined) {
    if (!file) return;
    await uploadMutation.mutateAsync({ file, datasetType });
  }

  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="data-manager-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Data manager</p>
        <h1 className="mt-1 text-2xl font-semibold">Dataset uploads</h1>
        <p className="mt-1 text-sm text-muted-foreground">Upload GeoJSON, SHP ZIP, or ISO-XML ZIP metadata. Max upload: 1 MiB in this demo build.</p>
      </section>
      <section className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-border/80 bg-card/90 p-4">
        <Select
          value={ datasetType }
          onValueChange={ (value) => setDatasetType(value as UploadedDataset['datasetType']) }
        >
          <SelectTrigger className="w-full sm:w-auto">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="geojson">GeoJSON</SelectItem>
            <SelectItem value="shp_zip">SHP ZIP</SelectItem>
            <SelectItem value="iso_xml">ISO-XML ZIP</SelectItem>
          </SelectContent>
        </Select>
        <input className="min-w-0 flex-1 text-sm sm:flex-none" type="file" onChange={ (event) => void onFile(event.target.files?.[0]) } />
      </section>
      { error && <p className="mt-4 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning">{ reportErrorMessage(error) }</p> }
      <section className="mt-4 grid gap-2 rounded-xl border border-border/80 bg-card/90 p-4">
        { datasetsQ.data?.map((dataset) => (
          <article key={ dataset.id } className="rounded-md border border-border p-3">
            <p className="font-medium">{ dataset.name }</p>
            <p className="text-sm text-muted-foreground">{ dataset.datasetType } · { dataset.uploadStatus } · { dataset.featureCount ?? 'metadata only' }</p>
          </article>
        )) }
        { !datasetsQ.data?.length && <p className="text-sm text-muted-foreground">No datasets uploaded yet.</p> }
      </section>
    </main>
  );
}
