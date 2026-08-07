import { useState } from 'react';
import {
  useActivities,
  useCreateFieldActivity,
  useExportActivitiesCsv,
  usePlots,
  useUpdateFieldActivity,
} from '@/lib/queries';
import { downloadFile, reportErrorMessage } from '@/pages/reports/reportUtils';
import { fieldLabel } from '@/lib/fieldLabels';
import type { ActivityFilters } from '@/types/api';

export default function FieldActivityLogPage() {
  const [filters, setFilters] = useState<ActivityFilters>({ year: new Date().getFullYear() });
  const [activityType, setActivityType] = useState('fertilizer');
  const [assignee, setAssignee] = useState('');
  const plotsQ = usePlots();
  const activitiesQ = useActivities(filters);
  const createMutation = useCreateFieldActivity();
  const updateMutation = useUpdateFieldActivity();
  const exportMutation = useExportActivitiesCsv();
  const firstPlotId = plotsQ.data?.[0]?.id;

  async function addActivity() {
    if (!firstPlotId) return;
    await createMutation.mutateAsync({
      plotId: firstPlotId,
      payload: {
        activityType,
        activityDate: new Date().toISOString().slice(0, 10),
        assignee: assignee || null,
        status: 'planned',
      },
    });
  }

  async function exportCsv() {
    const file = await exportMutation.mutateAsync(filters);
    downloadFile(file);
  }

  const error = activitiesQ.error ?? createMutation.error ?? exportMutation.error;

  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="activity-log-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Operations</p>
        <h1 className="mt-1 text-2xl font-semibold">Field activity log</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Track field operations, inputs, assignees, costs, and yearly timelines.
        </p>
      </section>

      <section className="mt-4 grid gap-3 rounded-xl border border-border/80 bg-card/90 p-4 md:grid-cols-5">
        { ['groupName', 'cropType', 'variety', 'activityType', 'assignee'].map((key) => (
          <label key={ key } className="text-sm text-muted-foreground">
            { fieldLabel(key) }
            <input
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
              value={ String((filters as Record<string, unknown>)[key] ?? '') }
              onChange={ (event) => setFilters((current) => ({ ...current, [key]: event.target.value || undefined })) }
            />
          </label>
        )) }
        <label className="text-sm text-muted-foreground">
          Year
          <input
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
            type="number"
            value={ filters.year ?? '' }
            onChange={ (event) => setFilters((current) => ({ ...current, year: Number(event.target.value) || undefined })) }
          />
        </label>
        <button className="self-end justify-self-start rounded-md border border-border px-3 py-2 text-sm" onClick={ () => void exportCsv() } type="button">
          Download report
        </button>
      </section>

      <section className="mt-4 rounded-xl border border-border/80 bg-card/90 p-4">
        <h2 className="text-lg font-semibold">Add activity</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <input className="rounded-md border border-border bg-background px-3 py-2" value={ activityType } onChange={ (event) => setActivityType(event.target.value) } />
          <input className="rounded-md border border-border bg-background px-3 py-2" placeholder="Assignee" value={ assignee } onChange={ (event) => setAssignee(event.target.value) } />
          <button className="w-full rounded-md bg-primary px-4 py-2 text-primary-foreground disabled:opacity-40 sm:w-auto" disabled={ !firstPlotId || createMutation.isPending } onClick={ () => void addActivity() } type="button">
            Add activity
          </button>
        </div>
      </section>

      { error && <p className="mt-4 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning">{ reportErrorMessage(error) }</p> }

      <section className="mt-4 rounded-xl border border-border/80 bg-card/90 p-4">
        <h2 className="text-lg font-semibold">Yearly timeline</h2>
        <div className="mt-3 grid gap-2">
          { activitiesQ.data?.map((activity) => (
            <article key={ activity.id } className="rounded-md border border-border p-3">
              <div className="flex flex-wrap justify-between gap-2">
                <span className="font-medium">{ activity.activityDate } — { activity.activityType }</span>
                <span className="text-sm text-muted-foreground">{ activity.status }</span>
              </div>
              <p className="text-sm text-muted-foreground">
                { activity.fieldName ?? 'Unassigned field' } · { activity.assignee ?? 'Unassigned' }
              </p>
              { activity.status !== 'done' && (
                <button
                  className="mt-2 rounded-md border border-border px-3 py-1.5 text-sm"
                  onClick={ () =>
                    void updateMutation.mutateAsync({
                      activityId: activity.id,
                      payload: { status: 'done' },
                    })
                  }
                  type="button"
                >
                  Mark done
                </button>
              ) }
            </article>
          )) }
          { !activitiesQ.data?.length && <p className="text-sm text-muted-foreground">No activities match these filters.</p> }
        </div>
      </section>
    </main>
  );
}
