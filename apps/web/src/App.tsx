import { useEffect, useState } from "react";
import {
  Activity, Bot, CalendarClock, FolderOpen, History, LayoutDashboard, ListChecks, Brain, MessageSquare, Mic, Plug, Settings, Share2, Smartphone,
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
import { VoicePage } from "./pages/Voice";
import { MemoryPage } from "./pages/Memory";
import { FilesPage } from "./pages/Files";
import { DevicesPage } from "./pages/Devices";
import { IntegrationsPage } from "./pages/Integrations";
import { RoutinesPage } from "./pages/Routines";
import { UpdateButton } from "./components/UpdateButton";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "voice", label: "Voz", icon: Mic },
  { id: "agents", label: "Agentes", icon: Bot },
  { id: "tasks", label: "Automatizaciones", icon: ListChecks },
  { id: "cowork", label: "Cowork", icon: Share2 },
  { id: "memory", label: "Memoria", icon: Brain },
  { id: "files", label: "Archivos", icon: FolderOpen },
  { id: "routines", label: "Rutinas", icon: CalendarClock },
  { id: "integrations", label: "Integraciones", icon: Plug },
  { id: "devices", label: "Dispositivos", icon: Smartphone },
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
  const [voiceTick, setVoiceTick] = useState(0);
  const [memoryTick, setMemoryTick] = useState(0);
  const [routineTick, setRoutineTick] = useState(0);
  const { state, detail, connected } = useAssistantState((e) => {
    if (e.type === "task") setTaskTick((t) => t + 1);
    if (e.type === "voice_download") setVoiceTick((t) => t + 1);
    if (e.type === "routine") setRoutineTick((t) => t + 1);
    if (e.type === "memory" || e.type === "project" || e.type === "task") setMemoryTick((t) => t + 1);
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
        <UpdateButton version="0.9.4" />
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
          {route === "voice" && <VoicePage refreshKey={voiceTick} />}
          {route === "memory" && <MemoryPage refreshKey={memoryTick} />}
          {route === "files" && <FilesPage />}
          {route === "devices" && <DevicesPage />}
          {route === "integrations" && <IntegrationsPage />}
          {route === "routines" && <RoutinesPage refreshKey={routineTick} />}
        </div>
      </main>
    </div>
  );
}
