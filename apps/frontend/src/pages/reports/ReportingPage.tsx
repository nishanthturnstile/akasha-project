import { useMemo, useState } from 'react';
import {
  useCreateReportTemplate,
  useReportTemplates,
  useUpdateReportTemplate,
} from '@/lib/queries';
import { DEFAULT_REPORT_COLUMNS, REPORT_COLUMNS } from '@/pages/reports/reportColumns';
import { reportErrorMessage } from '@/pages/reports/reportUtils';

export default function ReportingPage() {
  const templatesQ = useReportTemplates();
  const createMutation = useCreateReportTemplate();
  const updateMutation = useUpdateReportTemplate();
  const [name, setName] = useState('Field health summary');
  const [selectedColumns, setSelectedColumns] = useState<string[]>(DEFAULT_REPORT_COLUMNS);
  const [editingId, setEditingId] = useState<string | null>(null);
  const selectedTemplate = useMemo(
    () => templatesQ.data?.find((template) => template.id === editingId),
    [editingId, templatesQ.data],
  );

  function toggleColumn(column: string) {
    setSelectedColumns((current) =>
      current.includes(column)
        ? current.filter((item) => item !== column)
        : [...current, column],
    );
  }

  async function handleSave() {
    const payload = {
      name,
      columns: selectedColumns,
      filters: {},
      sort: { sortBy: 'score', sortOrder: 'desc' },
    };
    try {
      if (editingId) {
        await updateMutation.mutateAsync({ templateId: editingId, payload });
      } else {
        await createMutation.mutateAsync(payload);
      }
    } catch {
      // TanStack Query keeps the sanitized error for rendering.
    }
  }

  function startEdit(templateId: string) {
    const template = templatesQ.data?.find((item) => item.id === templateId);
    if (!template) return;
    setEditingId(template.id);
    setName(template.name);
    setSelectedColumns(template.columns);
  }

  const error = templatesQ.error ?? createMutation.error ?? updateMutation.error;

  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="reporting-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Reports</p>
        <h1 className="mt-1 text-2xl font-semibold">Reporting templates</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Build reusable CSV column sets from normalized field, index, weather, and report data.
        </p>
      </section>

      { error && (
        <div className="mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100" role="status">
          { reportErrorMessage(error) }
        </div>
      ) }

      <div className="mt-4 grid gap-4 lg:grid-cols-[320px_1fr]">
        <section className="rounded-xl border border-border/80 bg-card/90 p-4">
          <h2 className="text-lg font-semibold">Saved templates</h2>
          <div className="mt-3 grid gap-2">
            { templatesQ.data?.map((template) => (
              <button
                key={ template.id }
                className="rounded-md border border-border px-3 py-2 text-left text-sm hover:bg-accent"
                onClick={ () => startEdit(template.id) }
                type="button"
              >
                <span className="block font-medium">{ template.name }</span>
                <span className="text-xs text-muted-foreground">{ template.columns.length } columns</span>
              </button>
            )) }
            { !templatesQ.data?.length && (
              <p className="text-sm text-muted-foreground">
                { templatesQ.isLoading ? 'Loading templates...' : 'No templates yet.' }
              </p>
            ) }
          </div>
        </section>

        <section className="rounded-xl border border-border/80 bg-card/90 p-4">
          <h2 className="text-lg font-semibold">{ selectedTemplate ? 'Edit template' : 'Create template' }</h2>
          <label className="mt-4 block text-sm text-muted-foreground">
            Template name
            <input
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
              value={ name }
              onChange={ (event) => setName(event.target.value) }
            />
          </label>
          <div className="mt-4 grid gap-2 md:grid-cols-2">
            { REPORT_COLUMNS.map((column) => (
              <label key={ column.id } className="flex items-center gap-2 text-sm text-muted-foreground">
                <input
                  checked={ selectedColumns.includes(column.id) }
                  onChange={ () => toggleColumn(column.id) }
                  type="checkbox"
                />
                { column.label }
              </label>
            )) }
          </div>
          <div className="mt-5 flex gap-2">
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-40"
              disabled={ !name.trim() || selectedColumns.length === 0 || createMutation.isPending || updateMutation.isPending }
              onClick={ () => void handleSave() }
              type="button"
            >
              { editingId ? 'Update template' : 'Create template' }
            </button>
            { editingId && (
              <button
                className="rounded-md border border-border px-4 py-2 text-sm"
                onClick={ () => {
                  setEditingId(null);
                  setName('Field health summary');
                  setSelectedColumns(DEFAULT_REPORT_COLUMNS);
                } }
                type="button"
              >
                New template
              </button>
            ) }
          </div>
        </section>
      </div>
    </main>
  );
}
