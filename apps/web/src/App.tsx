import { useEffect, useState } from "react";
import {
  Activity, Bot, FolderOpen, History, LayoutDashboard, ListChecks, Brain, MessageSquare, Mic, Settings, Share2,
} from "lucide-react";
import { useAssistantState } from "./hooks/useAssistantState";
import { KaiCore, STATE_LABEL } from "./components/KaiCore";
import { Dashboard } from "./pages/Dashboard";
import { ChatPage } from "./pages/Chat";
import { HistoryPage } from "./pages/History";
import { TasksPage } from "./pages/Tasks";
import { CoworkPage } from "./pages/Cowork";
import { SettingsPage } from "./pages/Settings";
import { StatusPage } from "./pages/Status";
import { AgentsPage } from "./pages/Agents";
import { FuturePage } from "./components/ui";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "voice", label: "Voz", icon: Mic, future: true },
  { id: "agents", label: "Agentes", icon: Bot },
  { id: "tasks", label: "Automatizaciones", icon: ListChecks },
  { id: "cowork", label: "Cowork", icon: Share2 },
  { id: "memory", label: "Memoria", icon: Brain, future: true },
  { id: "files", label: "Archivos", icon: FolderOpen, future: true },
  { id: "history", label: "Historial", icon: History },
  { id: "settings", label: "Configuración", icon: Settings },
  { id: "status", label: "Estado del sistema", icon: Activity },
] as const;

type Route = (typeof NAV)[number]["id"];

function parseHash(): { route: Route; param: string | null } {
  const [r, p] = location.hash.replace(/^#\/?/, "").split("/");
  const route = (NAV.find((n) => n.id === r)?.id ?? "dashboard") as Route;
  return { route, param: p ?? null };
}

export default function App() {
  const [{ route, param }, setLoc] = useState(parseHash);
  const [taskTick, setTaskTick] = useState(0);
  const { state, detail, connected } = useAssistantState((e) => {
    if (e.type === "task") setTaskTick((t) => t + 1);
  });

  useEffect(() => {
    const onHash = () => setLoc(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  return (
    <div className="flex h-full">
      <nav className="flex w-60 shrink-0 flex-col border-r border-line bg-graphite/50 p-3 backdrop-blur" aria-label="Principal">
        <a href="#/dashboard" className="mb-5 flex items-center gap-3 px-2 pt-2">
          <KaiCore state={state} size={36} />
          <div>
            <div className="text-lg font-semibold tracking-[0.2em]">KAI</div>
            <div className="text-[11px] text-muted">{connected ? STATE_LABEL[state] : "Sin conexión con KAI Core"}</div>
          </div>
        </a>
        <ul className="space-y-0.5">
          {NAV.map(({ id, label, icon: Icon, ...rest }) => (
            <li key={id}>
              <a
                href={`#/${id}`}
                aria-current={route === id ? "page" : undefined}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                  route === id ? "bg-electric/15 text-ink" : "text-muted hover:bg-white/5 hover:text-ink"
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden />
                <span className="flex-1">{label}</span>
                {"future" in rest && <span className="text-[10px] uppercase text-muted/70">pronto</span>}
              </a>
            </li>
          ))}
        </ul>
        <div className="mt-auto px-2 pb-1 text-[11px] text-muted">KAI AI · Fase 1 (MVP)</div>
      </nav>

      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className={route === "chat" ? "h-full" : "mx-auto max-w-6xl p-8"}>
          {route === "dashboard" && <Dashboard state={state} detail={detail} connected={connected} />}
          {route === "chat" && <ChatPage conversationId={param} />}
          {route === "history" && <HistoryPage />}
          {route === "tasks" && <TasksPage refreshKey={taskTick} />}
          {route === "cowork" && <CoworkPage />}
          {route === "agents" && <AgentsPage />}
          {route === "settings" && <SettingsPage />}
          {route === "status" && <StatusPage />}
          {route === "voice" && (
            <FuturePage title="Voz" phase={2}
              description="Conversación por micrófono con respuesta hablada en español de Argentina. La grabación nunca se activará sin tu consentimiento explícito."
              items={["Activación con «Hey KAI»", "Speech-to-Text y Text-to-Speech (locales o en la nube)", "Detección de silencios, interrupción y cancelación", "Selección de micrófono y altavoces"]} />
          )}
          {route === "memory" && (
            <FuturePage title="Memoria" phase={3}
              description="Hoy KAI recuerda tus conversaciones (Historial). La memoria avanzada agregará preferencias, proyectos y contexto con búsqueda semántica, siempre consultable y eliminable."
              items={["Memoria de preferencias autorizadas", "Memoria de proyectos (objetivos, decisiones, próximos pasos)", "Recuperación contextual", "Controles de privacidad por memoria"]} />
          )}
          {route === "files" && (
            <FuturePage title="Archivos" phase={4}
              description="Acceso a carpetas autorizadas para leer, buscar y organizar documentos, con confirmación para cualquier acción sensible."
              items={["Lista de carpetas permitidas", "Lectura de PDF y documentos", "Organización con vista previa y confirmación", "Registro de auditoría de cada operación"]} />
          )}
        </div>
      </main>
    </div>
  );
}
