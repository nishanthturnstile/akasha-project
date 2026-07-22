import { useState } from 'react';
import { useAssignFieldGroupFields, useCreateFieldGroup, useFieldGroups, usePlots } from '@/lib/queries';
import { reportErrorMessage } from '@/pages/reports/reportUtils';

export default function FieldGroupsPage() {
  const [name, setName] = useState('North Block');
  const groupsQ = useFieldGroups();
  const plotsQ = usePlots();
  const createMutation = useCreateFieldGroup();
  const assignMutation = useAssignFieldGroupFields();
  const error = groupsQ.error ?? createMutation.error ?? assignMutation.error;

  async function createGroup() {
    await createMutation.mutateAsync({ name });
  }

  async function assignFirst(groupId: string) {
    const first = plotsQ.data?.[0]?.id;
    if (!first) return;
    await assignMutation.mutateAsync({ groupId, plotIds: [first] });
  }

  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="field-groups-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Field manager</p>
        <h1 className="mt-1 text-2xl font-semibold">Field groups</h1>
        <p className="mt-1 text-sm text-muted-foreground">Create groups and assign fields for team workflows.</p>
      </section>
      <section className="mt-4 flex gap-3 rounded-xl border border-border/80 bg-card/90 p-4">
        <input className="rounded-md border border-border bg-background px-3 py-2" value={ name } onChange={ (event) => setName(event.target.value) } />
        <button className="rounded-md bg-primary px-4 py-2 text-primary-foreground" onClick={ () => void createGroup() } type="button">Add group</button>
      </section>
      { error && <p className="mt-4 rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning">{ reportErrorMessage(error) }</p> }
      <section className="mt-4 grid gap-2 rounded-xl border border-border/80 bg-card/90 p-4">
        { groupsQ.data?.map((group) => (
          <article key={ group.id } className="rounded-md border border-border p-3">
            <div className="flex justify-between gap-3">
              <div>
                <p className="font-medium">{ group.name }</p>
                <p className="text-sm text-muted-foreground">{ group.plotIds.length } assigned fields</p>
              </div>
              <button className="rounded-md border border-border px-3 py-1.5 text-sm" onClick={ () => void assignFirst(group.id) } type="button">Assign first field</button>
            </div>
          </article>
        )) }
        { !groupsQ.data?.length && <p className="text-sm text-muted-foreground">No field groups yet.</p> }
      </section>
    </main>
  );
}
