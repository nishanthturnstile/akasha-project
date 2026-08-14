import { useState } from 'react';
import { DiscoveryBrowser } from '@/components/discovery/DiscoveryBrowser';
import { useCreateScoutTask } from '@/lib/queries';
import { reportErrorMessage } from '@/pages/reports/reportUtils';
import { useSeasonContext } from '@/state/seasonContext';
import { useMapView } from '@/state/useMapView';

export default function ScoutTasksPage() {
  const [longitude, setLongitude] = useState(77.59);
  const [latitude, setLatitude] = useState(12.97);
  const [notes, setNotes] = useState('');
  const createMutation = useCreateScoutTask();
  const { seasonId } = useSeasonContext();
  const view = useMapView();
  const error = createMutation.error;

  async function addTask() {
    await createMutation.mutateAsync({
      fieldId: view.selectedPlotId,
      longitude,
      latitude,
      notes,
      status: 'new',
      priority: 'medium',
    });
  }

  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden bg-background p-4 text-foreground" data-testid="scout-tasks-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Operations</p>
        <h1 className="mt-1 text-2xl font-semibold">Scout tasks</h1>
        <p className="mt-1 text-sm text-muted-foreground">Create map-pin scouting tasks and track new/closed work.</p>
      </section>
      <section className="mt-4 grid gap-3 rounded-xl border border-border/80 bg-card/90 p-4 md:grid-cols-4">
        <input className="rounded-md border border-border bg-background px-3 py-2" type="number" value={ longitude } onChange={ (event) => setLongitude(Number(event.target.value)) } />
        <input className="rounded-md border border-border bg-background px-3 py-2" type="number" value={ latitude } onChange={ (event) => setLatitude(Number(event.target.value)) } />
        <input className="rounded-md border border-border bg-background px-3 py-2 md:col-span-3" placeholder="Task notes" value={ notes } onChange={ (event) => setNotes(event.target.value) } />
        <button className="w-full rounded-md bg-primary px-4 py-2 text-primary-foreground sm:w-auto" onClick={ () => void addTask() } type="button">Add task by pin</button>
      </section>
      { error && <p className="mt-4 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning">{ reportErrorMessage(error) }</p> }
      <section className="mt-4 flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border/80 bg-card/90">
        {seasonId
          ? <DiscoveryBrowser target="scouting" seasonId={seasonId} />
          : <p className="p-6 text-sm text-muted-foreground">Select a season to discover scouting tasks.</p>}
      </section>
    </main>
  );
}
