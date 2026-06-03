import { useState } from 'react';
import { useCreateScoutTask, useScoutTasks, useUpdateScoutTask } from '@/lib/queries';
import { reportErrorMessage } from '@/pages/reports/reportUtils';

export default function ScoutTasksPage() {
  const [status, setStatus] = useState<'new' | 'closed'>('new');
  const [longitude, setLongitude] = useState(77.59);
  const [latitude, setLatitude] = useState(12.97);
  const [notes, setNotes] = useState('');
  const tasksQ = useScoutTasks({ status });
  const createMutation = useCreateScoutTask();
  const updateMutation = useUpdateScoutTask();
  const error = tasksQ.error ?? createMutation.error ?? updateMutation.error;

  async function addTask() {
    await createMutation.mutateAsync({ longitude, latitude, notes, status: 'new', priority: 'medium' });
  }

  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="scout-tasks-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Operations</p>
        <h1 className="mt-1 text-2xl font-semibold">Scout tasks</h1>
        <p className="mt-1 text-sm text-muted-foreground">Create map-pin scouting tasks and track new/closed work.</p>
      </section>
      <section className="mt-4 grid gap-3 rounded-xl border border-border/80 bg-card/90 p-4 md:grid-cols-4">
        <button className={ status === 'new' ? 'rounded-md bg-primary px-3 py-2 text-primary-foreground' : 'rounded-md border border-border px-3 py-2' } onClick={ () => setStatus('new') } type="button">New</button>
        <button className={ status === 'closed' ? 'rounded-md bg-primary px-3 py-2 text-primary-foreground' : 'rounded-md border border-border px-3 py-2' } onClick={ () => setStatus('closed') } type="button">Closed</button>
        <input className="rounded-md border border-border bg-background px-3 py-2" type="number" value={ longitude } onChange={ (event) => setLongitude(Number(event.target.value)) } />
        <input className="rounded-md border border-border bg-background px-3 py-2" type="number" value={ latitude } onChange={ (event) => setLatitude(Number(event.target.value)) } />
        <input className="rounded-md border border-border bg-background px-3 py-2 md:col-span-3" placeholder="Task notes" value={ notes } onChange={ (event) => setNotes(event.target.value) } />
        <button className="rounded-md bg-primary px-4 py-2 text-primary-foreground" onClick={ () => void addTask() } type="button">Add task by pin</button>
      </section>
      { error && <p className="mt-4 rounded-md border border-amber-500/40 p-3 text-sm text-amber-100">{ reportErrorMessage(error) }</p> }
      <section className="mt-4 grid gap-2 rounded-xl border border-border/80 bg-card/90 p-4">
        { tasksQ.data?.map((task) => (
          <article key={ task.id } className="rounded-md border border-border p-3">
            <p className="font-medium">{ task.fieldName ?? 'Map pin' } · { task.priority }</p>
            <p className="text-sm text-muted-foreground">{ task.latitude }, { task.longitude } — { task.notes ?? 'No notes' }</p>
            <button
              className="mt-2 rounded-md border border-border px-3 py-1.5 text-sm"
              onClick={ () =>
                void updateMutation.mutateAsync({
                  taskId: task.id,
                  payload: { status: task.status === 'new' ? 'closed' : 'new' },
                })
              }
              type="button"
            >
              { task.status === 'new' ? 'Close task' : 'Reopen task' }
            </button>
          </article>
        )) }
        { !tasksQ.data?.length && <p className="text-sm text-muted-foreground">No { status } scout tasks.</p> }
      </section>
    </main>
  );
}
