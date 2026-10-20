import { Badge, Card, PageHeader } from "../components/ui";
import { useApi } from "../hooks/useApi";
import type { Agent } from "../lib/api";

export function AgentsPage() {
  const agents = useApi<Agent[]>("/agents");
  return (
    <div>
      <PageHeader title="Agentes" subtitle="Estado real de cada agente. El orquestador (Claude) decide qué herramientas usar en cada respuesta." />
      <div className="grid gap-4 md:grid-cols-2">
        {agents.data?.map((a) => (
          <Card key={a.id}>
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">{a.name}</h3>
              {a.status === "active" ? <Badge tone="ok">Activo</Badge> : a.status === "disabled" ? <Badge tone="warn">Desactivado</Badge> : <Badge>Planificado · Fase {a.phase}</Badge>}
            </div>
            <p className="mt-2 text-sm text-muted">{a.description}</p>
            {a.tools.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">{a.tools.map((t) => <code key={t} className="rounded bg-void px-1.5 py-0.5 text-[11px] text-cyan">{t}</code>)}</div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
