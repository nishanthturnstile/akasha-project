import { useAssistantStatus } from '@/lib/queries';

export default function AiAssistantPage() {
  const statusQ = useAssistantStatus();
  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="assistant-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Assistant</p>
        <h1 className="mt-1 text-2xl font-semibold">AI assistant shell</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          { statusQ.data?.message ?? 'Assistant status loading.' }
        </p>
        <p className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100">
          The assistant may summarize only available Akasha evidence. It must not invent agronomic advice.
        </p>
      </section>
    </main>
  );
}
