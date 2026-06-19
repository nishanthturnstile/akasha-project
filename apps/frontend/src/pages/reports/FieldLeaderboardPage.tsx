import { useMemo, useState } from 'react';
import { useExportFieldLeaderboardCsv, useFieldLeaderboard } from '@/lib/queries';
import { fieldLabel } from '@/lib/fieldLabels';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { FieldLeaderboardFilters } from '@/types/api';
import { DEFAULT_REPORT_COLUMNS, REPORT_COLUMNS } from '@/pages/reports/reportColumns';
import { downloadFile, fmt, reportErrorMessage, valueForColumn } from '@/pages/reports/reportUtils';

export default function FieldLeaderboardPage() {
  const [filters, setFilters] = useState<FieldLeaderboardFilters>({
    indexType: 'NDVI',
    sortBy: 'score',
    sortOrder: 'desc',
    limit: 50,
    evaluationLimit: 100,
  });
  const leaderboardQ = useFieldLeaderboard(filters);
  const exportMutation = useExportFieldLeaderboardCsv();
  const rows = leaderboardQ.data?.rows ?? [];
  const truncated = Boolean(leaderboardQ.data?.metadata.truncated);

  const columns = useMemo(() => DEFAULT_REPORT_COLUMNS, []);

  async function handleExport() {
    try {
      const file = await exportMutation.mutateAsync({ filters, columns });
      downloadFile(file);
    } catch {
      // TanStack Query keeps the sanitized error for rendering.
    }
  }

  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="field-leaderboard-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Reports</p>
        <h1 className="mt-1 text-2xl font-semibold">Field leaderboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Ranked from normalized Akasha field metadata and cloud-free index statistics.
        </p>
      </section>

      <section className="mt-4 grid gap-3 rounded-xl border border-border/80 bg-card/90 p-4 md:grid-cols-5">
        <label className="text-sm text-muted-foreground">
          Index
          <Select
            value={ filters.indexType ?? 'NDVI' }
            onValueChange={ (value) => setFilters((current) => ({ ...current, indexType: value })) }
          >
            <SelectTrigger className="mt-1 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              { ['NDVI', 'NDRE', 'NDMI'].map((index) => (
                <SelectItem key={ index } value={ index }>{ index }</SelectItem>
              )) }
            </SelectContent>
          </Select>
        </label>
        { ['groupName', 'cropType', 'variety', 'seasonLabel'].map((key) => (
          <label key={ key } className="text-sm text-muted-foreground">
            { fieldLabel(key) }
            <input
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
              value={ String((filters as Record<string, unknown>)[key] ?? '') }
              onChange={ (event) => setFilters((current) => ({ ...current, [key]: event.target.value || undefined })) }
            />
          </label>
        )) }
        <label className="text-sm text-muted-foreground md:col-span-2">
          Search field/location
          <input
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
            value={ filters.search ?? '' }
            onChange={ (event) => setFilters((current) => ({ ...current, search: event.target.value || undefined })) }
          />
        </label>
        <button
          className="self-end rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-40"
          disabled={ exportMutation.isPending || rows.length === 0 }
          onClick={ () => void handleExport() }
          type="button"
        >
          { exportMutation.isPending ? 'Exporting...' : 'Export CSV' }
        </button>
      </section>

      { truncated && (
        <div className="mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100">
          Ranking computed for first { fmt(leaderboardQ.data?.metadata.evaluationLimit, 0) } filtered fields.
        </div>
      ) }
      { (leaderboardQ.error || exportMutation.error) && (
        <div className="mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100" role="status">
          { reportErrorMessage(leaderboardQ.error ?? exportMutation.error) }
        </div>
      ) }

      <section className="mt-4 overflow-x-auto rounded-xl border border-border/80 bg-card/90 p-4">
        <table className="min-w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
            <tr>
              { columns.map((column) => (
                <th key={ column } className="py-2 pr-4">
                  { REPORT_COLUMNS.find((item) => item.id === column)?.label ?? column }
                </th>
              )) }
            </tr>
          </thead>
          <tbody>
            { rows.map((row) => (
              <tr key={ row.plotId } className="border-t border-border/60">
                { columns.map((column) => (
                  <td key={ column } className="py-2 pr-4">
                    { column === 'preview' && row.preview ? (
                      <a className="text-primary underline-offset-4 hover:underline" href={ row.preview }>
                        Preview
                      </a>
                    ) : (
                      fmt(valueForColumn(row, column), column === 'score' ? 4 : 2)
                    ) }
                  </td>
                )) }
              </tr>
            )) }
            { rows.length === 0 && (
              <tr>
                <td className="py-4 text-muted-foreground" colSpan={ columns.length }>
                  { leaderboardQ.isLoading ? 'Loading leaderboard...' : 'No fields match the current report filters.' }
                </td>
              </tr>
            ) }
          </tbody>
        </table>
      </section>
    </main>
  );
}
