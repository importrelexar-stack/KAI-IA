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
import { WelcomeGreeting } from "./components/WelcomeGreeting";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, group: "Principal" },
  { id: "chat", label: "Chat", icon: MessageSquare, group: "Principal" },
  { id: "voice", label: "Voz", icon: Mic, group: "Principal" },
  { id: "tasks", label: "Automatizaciones", icon: ListChecks, group: "Trabajo" },
  { id: "routines", label: "Rutinas", icon: CalendarClock, group: "Trabajo" },
  { id: "agents", label: "Agentes", icon: Bot, group: "Trabajo" },
  { id: "memory", label: "Memoria", icon: Brain, group: "Trabajo" },
  { id: "files", label: "Archivos", icon: FolderOpen, group: "Trabajo" },
  { id: "cowork", label: "Cowork", icon: Share2, group: "Trabajo" },
  { id: "integrations", label: "Integraciones", icon: Plug, group: "Conexiones" },
  { id: "devices", label: "Dispositivos", icon: Smartphone, group: "Conexiones" },
  { id: "history", label: "Historial", icon: History, group: "Sistema" },
  { id: "settings", label: "Configuración", icon: Settings, group: "Sistema" },
  { id: "status", label: "Estado del sistema", icon: Activity, group: "Sistema" },
] as const;
const GROUPS = ["Principal", "Trabajo", "Conexiones", "Sistema"] as const;

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
      <WelcomeGreeting />
      <nav className="flex w-64 shrink-0 flex-col border-r border-line/70 bg-graphite/60 p-3 backdrop-blur-xl" aria-label="Principal">
        <a href="#/dashboard" className="mb-4 flex items-center gap-3 rounded-xl px-2 py-2">
          <KaiCore state={state} size={40} />
          <div>
            <div className="text-gradient text-lg font-semibold tracking-[0.35em]">KAI</div>
            <div className="flex items-center gap-1.5 text-[11px] text-muted">
              <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-ok shadow-[0_0_6px_var(--color-ok)]" : "bg-danger"}`} aria-hidden />
              {connected ? STATE_LABEL[state] : "Sin conexión con KAI Core"}
            </div>
          </div>
        </a>
        <div className="-mr-1 min-h-0 flex-1 overflow-y-auto pr-1">
          {GROUPS.map((g) => (
            <div key={g} className="mb-3">
              <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-muted/60">{g}</div>
              <ul className="space-y-0.5">
                {NAV.filter((n) => n.group === g).map(({ id, label, icon: Icon }) => (
                  <li key={id}>
                    <a href={`#/${id}`} aria-current={route === id ? "page" : undefined} className="nav-item">
                      <Icon className="h-4 w-4" aria-hidden />
                      <span className="flex-1">{label}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <UpdateButton version="0.9.7" />
      </nav>

      <main className="min-w-0 flex-1 overflow-y-auto">
        <div key={route} className={route === "chat" ? "h-full" : "fade-up mx-auto max-w-6xl p-8"}>
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
