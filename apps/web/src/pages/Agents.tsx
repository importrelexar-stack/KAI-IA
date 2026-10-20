import { Badge, Card, PageHeader } from "../components/ui";
import { useApi } from "../hooks/useApi";
import type { Agent } from "../lib/api";

export function AgentsPage() {
  const agents = useApi<Agent[]>("/agents");
  return (
    <div>
      <PageHeader title="Agentes" subtitle="Estado real de cada agente. Sólo el orquestador conversacional está activo en la Fase 1." />
      <div className="grid gap-4 md:grid-cols-2">
        {agents.data?.map((a) => (
          <Card key={a.id}>
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">{a.name}</h3>
              {a.status === "active" ? <Badge tone="ok">Activo</Badge> : <Badge>Planificado · Fase {a.phase}</Badge>}
            </div>
            <p className="mt-2 text-sm text-muted">{a.description}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
