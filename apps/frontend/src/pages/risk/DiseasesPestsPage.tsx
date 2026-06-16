import { useMapView } from '@/state/useMapView';
import { useFieldRiskSummary, usePlots } from '@/lib/queries';
import { reportErrorMessage, fmt } from '@/pages/reports/reportUtils';
import type { RiskLevel } from '@/types/api';
import { SelectFieldNotice } from '@/components/shell/SelectFieldNotice';

const LEVELS: RiskLevel[] = ['low', 'medium', 'high', 'unknown'];

function levelClass(level: RiskLevel) {
  if (level === 'high') return 'border-red-500/50 bg-red-500/10 text-red-100';
  if (level === 'medium') return 'border-amber-500/50 bg-amber-500/10 text-amber-100';
  if (level === 'low') return 'border-emerald-500/50 bg-emerald-500/10 text-emerald-100';
  return 'border-border bg-muted/20 text-muted-foreground';
}

export default function DiseasesPestsPage() {
  const { selectedPlotId } = useMapView();
  const plotsQ = usePlots();
  const riskQ = useFieldRiskSummary(selectedPlotId);
  const fieldName = plotsQ.data?.find((plot) => plot.id === selectedPlotId)?.name ?? selectedPlotId;

  if (!selectedPlotId) {
    return (
      <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="diseases-pests-page">
        <SelectFieldNotice
          title="Diseases & Pests"
          message="Select a field to view non-diagnostic field-watch context."
        />
      </main>
    );
  }

  const risk = riskQ.data;

  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="diseases-pests-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Decision support</p>
        <h1 className="mt-1 text-2xl font-semibold">Diseases & Pests</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Selected field: { fieldName }
        </p>
        <p className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100">
          This is not a disease or pest diagnostic model. It is field-watch context to help prioritize scouting.
        </p>
      </section>

      { riskQ.isLoading && <div className="glass scan-sweep mt-4 h-24 rounded-xl" /> }
      { riskQ.error && (
        <p className="mt-4 rounded-md border border-amber-500/40 p-3 text-sm text-amber-100">
          { reportErrorMessage(riskQ.error) }
        </p>
      ) }

      <section className="mt-4 grid gap-4 lg:grid-cols-[1fr_320px]">
        <article className={ `rounded-xl border p-4 ${levelClass(risk?.fieldWatchLevel ?? 'unknown')}` }>
          <p className="text-sm uppercase tracking-[0.18em]">Field watch priority</p>
          <h2 className="mt-2 text-3xl font-semibold">{ risk?.fieldWatchLevel ?? 'unknown' }</h2>
          <p className="mt-2 text-sm">Score: { fmt(risk?.score, 4) }</p>
          <p className="mt-3 text-sm">{ risk?.vegetationStressContext ?? 'Risk context is loading.' }</p>
        </article>
        <article className="rounded-xl border border-border/80 bg-card/90 p-4">
          <h2 className="text-lg font-semibold">Crop stage context</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            { risk?.cropStage.cropType ?? 'Crop not recorded' } · { risk?.cropStage.stageLabel ?? 'unknown' }
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Days after start: { fmt(risk?.cropStage.daysAfterStart, 0) }
          </p>
          <p className="mt-1 text-xs text-muted-foreground">Model: { risk?.cropStage.modelVersion ?? 'generic-v1' }</p>
        </article>
      </section>

      <section className="mt-4 rounded-xl border border-border/80 bg-card/90 p-4">
        <h2 className="text-lg font-semibold">Risk context legend</h2>
        <div className="mt-3 grid gap-2 md:grid-cols-4">
          { LEVELS.map((level) => (
            <div key={ level } className={ `rounded-md border p-3 text-sm ${levelClass(level)}` }>
              { level } — { level === 'unknown' ? 'insufficient validated inputs' : 'relative scouting priority' }
            </div>
          )) }
        </div>
      </section>

      <section className="mt-4 grid gap-3 rounded-xl border border-border/80 bg-card/90 p-4">
        <h2 className="text-lg font-semibold">Evidence components</h2>
        { risk?.components.map((component) => (
          <article key={ component.id } className="rounded-md border border-border p-3">
            <div className="flex flex-wrap justify-between gap-2">
              <span className="font-medium">{ component.label }</span>
              <span className="text-sm text-muted-foreground">{ component.level }</span>
            </div>
            <p className="text-sm text-muted-foreground">
              { component.available ? component.evidence.join(' ') || 'Evidence available.' : component.limitations.join(' ') }
            </p>
          </article>
        )) }
      </section>

      <section className="mt-4 rounded-xl border border-dashed border-border/80 bg-card/80 p-4">
        <h2 className="text-lg font-semibold">Manage disease and pest list</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Disease and pest list management is planned. No recommendations are generated here.
        </p>
      </section>
    </main>
  );
}
