// Cliente de la API local de KAI Core.

export const API = "/api/v1";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    const err = body?.error;
    if (err?.details?.length) {
      const detail = err.details.map((d: { field: string; message: string }) => `${d.field}: ${d.message}`).join("; ");
      return new ApiError(res.status, err.code ?? "error", `${err.message} ${detail}`);
    }
    return new ApiError(res.status, err?.code ?? "error", err?.message ?? res.statusText);
  } catch {
    return new ApiError(res.status, "network", `KAI Core respondió ${res.status}`);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      ...init,
      headers: init.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init.headers },
    });
  } catch {
    throw new ApiError(0, "offline", "No se pudo conectar con KAI Core. ¿Está iniciado el servidor?");
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export const get = <T,>(p: string) => api<T>(p);
export const post = <T,>(p: string, body?: unknown) =>
  api<T>(p, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const put = <T,>(p: string, body: unknown) => api<T>(p, { method: "PUT", body: JSON.stringify(body) });
export const patch = <T,>(p: string, body: unknown) => api<T>(p, { method: "PATCH", body: JSON.stringify(body) });
export const del = <T,>(p: string) => api<T>(p, { method: "DELETE" });

// ---- Tipos ----

export type AssistantState = "idle" | "listening" | "processing" | "speaking" | "executing" | "error";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  model?: string | null;
  stop_reason?: string | null;
  input_tokens?: number;
  output_tokens?: number;
  tool_events?: ToolEvent[] | null;
  attachments?: AttachmentRef[] | null;
  created_at: string;
}

export interface AttachmentRef {
  id: string;
  name: string;
  kind: "document" | "image";
  size: number;
}

export interface AttachmentOut extends AttachmentRef {
  media_type: string;
  chars: number;
}

export function uploadAttachment(file: File): Promise<AttachmentOut> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  return api<AttachmentOut>("/chat/attachments", { method: "POST", body: fd });
}

export interface ToolEvent {
  name: string;
  summary: string;
  ok: boolean;
  task_id?: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationDetail extends ConversationSummary {
  messages: Message[];
}

export interface Preferences {
  model: string;
  effort: "low" | "medium" | "high" | "xhigh" | "max";
  max_tokens: number;
  history_window: number;
  daily_token_budget: number;
  use_fallbacks: boolean;
  language: string;
  user_name: string;
  custom_instructions: string;
  voice_stt_engine: "local" | "browser";
  voice_tts_engine: "local" | "browser";
  whisper_model: "tiny" | "base" | "small";
  piper_voice: "es_AR-daniela-high" | "es_MX-claude-high" | "es_ES-davefx-medium";
  voice_auto_speak: boolean;
  voice_handsfree_consent: boolean;
  memory_enabled: boolean;
  memory_auto_approve: boolean;
  agents_enabled: boolean;
  web_search_enabled: boolean;
  web_fetch_enabled: boolean;
  max_tool_iterations: number;
  fast_mode: boolean;
  auto_update: boolean;
}

export interface ApiKeyStatus {
  configured: boolean;
  source: "env" | "keyring" | "memory" | "none";
  masked: string | null;
  keyring_available: boolean;
  persisted: boolean;
}

export interface SettingsOut {
  preferences: Preferences;
  api_key: ApiKeyStatus;
  demo_mode: boolean;
  models: Record<string, string>;
  effort_levels: string[];
}

export interface SystemStatus {
  version: string;
  uptime_seconds: number;
  platform: string;
  python: string;
  database: { ok: boolean };
  assistant: { state: AssistantState; detail: string | null; active_operations: number };
  provider: { name: string; configured: boolean; model: string; effort: string; demo_mode: boolean };
  api_key: ApiKeyStatus;
  usage_today: { input_tokens: number; output_tokens: number; cache_read_tokens: number; requests: number; total_tokens: number };
  budget: { daily_tokens: number; remaining: number | null };
  realtime_clients: number;
  features: Record<string, string>;
}

export type TaskStatus = "pending" | "awaiting_approval" | "running" | "completed" | "failed" | "cancelled";

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: number;
  requires_approval: boolean;
  result: string | null;
  error: string | null;
  approvals: { decision: string; at: string }[];
  history: { status: string; at: string; note?: string }[];
  project_id: string | null;
  depends_on: string[];
  created_by: "user" | "kai";
  action?: { tool: string; args: Record<string, unknown>; conversation_id: string | null } | null;
  created_at: string;
  updated_at: string;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  status: "active" | "disabled" | "planned";
  phase: number;
  tools: string[];
}

export type MemoryKind = "preference" | "fact" | "project";

export interface MemoryItem {
  id: string;
  kind: MemoryKind;
  content: string;
  tags: string[];
  status: "active" | "proposed";
  source: "user" | "kai";
  project_id: string | null;
  conversation_id: string | null;
  use_count: number;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectLogEntry {
  kind: "decision" | "progress" | "note";
  text: string;
  by: "user" | "kai";
  at: string;
}

export interface Project {
  id: string;
  name: string;
  goal: string;
  status: "active" | "paused" | "done";
  next_steps: string;
  files: string[];
  log: ProjectLogEntry[];
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends Project {
  tasks: { id: string; title: string; status: TaskStatus; priority: number; depends_on: string[] }[];
  memories: string[];
}

export interface CoworkHandoff {
  id: string;
  title: string;
  objective: string;
  instructions_md: string;
  status: "draft" | "sent" | "completed" | "cancelled";
  result_text: string | null;
  result_files: { name: string; size: number; stored_at: string }[];
  created_at: string;
  updated_at: string;
}

export interface CoworkStatus {
  adapter: string;
  official_api: boolean;
  can_submit: boolean;
  description: string;
  untrusted_notice: string;
}

// ---- Chat por streaming (Server-Sent Events sobre POST) ----

export type ChatEvent =
  | { type: "meta"; conversation_id: string; user_message: Message; title: string; provider: string }
  | { type: "delta"; text: string }
  | ({ type: "tool" } & ToolEvent)
  | { type: "done"; conversation_id: string; assistant_message: Message; served_by_fallback: boolean }
  | { type: "error"; code: string; message: string; status: number };

export function parseSseChunk(buffer: string): { events: ChatEvent[]; rest: string } {
  const events: ChatEvent[] = [];
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    for (const line of block.split("\n")) {
      if (line.startsWith("data: ")) {
        try {
          events.push(JSON.parse(line.slice(6)));
        } catch {
          /* bloque incompleto o corrupto: se ignora */
        }
      }
    }
  }
  return { events, rest };
}

export async function streamChat(
  message: string,
  conversationId: string | null,
  onEvent: (e: ChatEvent) => void,
  signal: AbortSignal,
  channel: "text" | "voice" = "text",
  attachmentIds: string[] = [],
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id: conversationId, stream: true, channel, attachment_ids: attachmentIds }),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    throw new ApiError(0, "offline", "No se pudo conectar con KAI Core.");
  }
  if (!res.ok || !res.body) throw await parseError(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSseChunk(buffer);
      buffer = parsed.rest;
      parsed.events.forEach(onEvent);
    }
  } catch (e) {
    if ((e as Error).name !== "AbortError") throw e;
  }
}

// ---- Voz ----

export interface VoiceEngine {
  id: string;
  kind: "stt" | "tts";
  name: string;
  installed: boolean;
  model: string;
  model_ready: boolean;
  model_size_mb: number;
  detail: string;
}

export interface VoiceStatus {
  stt: VoiceEngine;
  tts: VoiceEngine;
  downloads: Record<string, { state: "downloading" | "done" | "error"; model: string; error?: string }>;
  preferences: Pick<Preferences, "voice_stt_engine" | "voice_tts_engine" | "whisper_model" | "piper_voice" | "voice_auto_speak" | "voice_handsfree_consent" | "language">;
  privacy: string;
}

export interface TranscriptOut {
  text: string;
  language: string;
  duration_seconds: number;
  engine: string;
}

export function transcribe(audio: Blob, language?: string, signal?: AbortSignal): Promise<TranscriptOut> {
  const fd = new FormData();
  fd.append("audio", audio, "voz.wav");
  if (language) fd.append("language", language);
  return api<TranscriptOut>("/voice/transcribe", { method: "POST", body: fd, signal });
}

export async function synthesize(text: string, signal?: AbortSignal): Promise<Blob> {
  let res: Response;
  try {
    res = await fetch(`${API}/voice/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "offline", "No se pudo conectar con KAI Core.");
  }
  if (!res.ok) throw await parseError(res);
  return res.blob();
}

/** Informa a KAI Core el estado de la interfaz de voz (el núcleo visual lo refleja). */
export function reportVoiceState(state: "listening" | "speaking" | "idle") {
  void fetch(`${API}/voice/state`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state }),
  }).catch(() => undefined);
}

// ---- Automatización (Fase 4) ----

export type Level = "allow" | "ask" | "deny";

export interface AutomationPermissions {
  folders: { path: string; mode: "read" | "read_write" }[];
  apps: { name: string; command: string; resolved?: string | null; available?: boolean }[];
  scripts: { name: string; path: string; timeout_seconds: number }[];
  start_menu_apps: boolean;
  levels: Record<string, Level>;
  default_levels: Record<string, Level>;
  always_ask: string[];
}

export interface BrowseResult {
  path: string;
  root: string;
  items: { nombre: string; tipo: "carpeta" | "archivo"; tamano: string | null; modificado: string }[];
}

// ---- Dispositivos (Fase 5) ----

export interface RemoteStatus {
  enabled: boolean;
  listening_on_network: boolean;
  restart_required: boolean;
  port: number;
  addresses: string[];
}

export interface PairingOut extends RemoteStatus {
  code: string;
  expires_at: string;
  urls: string[];
  payload: string;
  qr_svg: string;
}

export interface Device {
  id: string;
  name: string;
  platform: string;
  revoked: boolean;
  last_seen_at: string | null;
  last_ip: string | null;
  created_at: string;
}

export const devicesApi = {
  remote: () => api<RemoteStatus>("/devices/remote"),
  setRemote: (enabled: boolean) => api<RemoteStatus>("/devices/remote", { method: "PUT", body: JSON.stringify({ enabled }) }),
  pairing: () => api<PairingOut>("/devices/pairing", { method: "POST" }),
  list: () => api<Device[]>("/devices"),
  revoke: (id: string) => api<Device>(`/devices/${id}`, { method: "DELETE" }),
};

// ---- Integraciones (Fase 6) ----

export type ToolLevel = "allow" | "ask" | "deny";

export interface McpTool {
  name: string;
  description: string;
  read_only: boolean;
  destructive: boolean;
  level: ToolLevel;
  custom: boolean;
}

export interface McpServer {
  id: string;
  name: string;
  transport: "stdio" | "http";
  command: string;
  args: string[];
  env: Record<string, string>;
  secret_env: string[];
  url: string;
  has_token: boolean;
  enabled: boolean;
  status: "connecting" | "needs_auth" | "connected" | "error" | "stopped";
  oauth: boolean;
  auth_url: string | null;
  error: string | null;
  server_info: string;
  tools: McpTool[];
}

export interface IntegrationsOverview {
  web: { web_search_enabled: boolean; web_fetch_enabled: boolean };
  mcp: McpServer[];
  secure_storage: boolean;
}

export interface McpServerIn {
  name: string;
  transport: "stdio" | "http";
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  secret_env?: Record<string, string>;
  url?: string;
  token?: string;
  oauth?: boolean;
}

export const integrationsApi = {
  overview: () => api<IntegrationsOverview>("/integrations"),
  setWeb: (body: Partial<IntegrationsOverview["web"]>) => api<IntegrationsOverview["web"]>("/integrations/web", { method: "PUT", body: JSON.stringify(body) }),
  add: (body: McpServerIn) => api<McpServer>("/integrations/mcp", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: { enabled?: boolean; name?: string }) => api<McpServer>(`/integrations/mcp/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  reconnect: (id: string) => api<McpServer>(`/integrations/mcp/${id}/reconnect`, { method: "POST" }),
  setLevel: (id: string, tool: string, level: ToolLevel | "default") =>
    api<McpServer>(`/integrations/mcp/${id}/tools/${encodeURIComponent(tool)}`, { method: "PUT", body: JSON.stringify({ level }) }),
  remove: (id: string) => api<void>(`/integrations/mcp/${id}`, { method: "DELETE" }),
  oauthOpen: (id: string) => api<{ opened: boolean; auth_url: string }>(`/integrations/mcp/${id}/oauth/open`, { method: "POST" }),
  oauthLogout: (id: string) => api<McpServer>(`/integrations/mcp/${id}/oauth`, { method: "DELETE" }),
  setSecrets: (id: string, body: { secret_env?: Record<string, string>; token?: string }) =>
    api<McpServer>(`/integrations/mcp/${id}/secrets`, { method: "PUT", body: JSON.stringify(body) }),
};

/** "CLAVE=valor" por línea → objeto. Ignora líneas vacías; lanza error si una línea no tiene "=". */
export function parseEnvLines(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const i = line.indexOf("=");
    if (i <= 0) throw new Error(`Línea inválida (falta =): ${line}`);
    out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return out;
}

// ---- Rutinas (Fase 6) ----

export type RoutineSchedule =
  | { type: "daily"; time: string }
  | { type: "weekly"; days: number[]; time: string }
  | { type: "interval"; minutes: number };

export interface Routine {
  id: string;
  name: string;
  prompt: string;
  schedule: RoutineSchedule;
  schedule_text: string;
  enabled: boolean;
  conversation_id: string | null;
  next_run_at: string | null;
  last_run_at: string | null;
  last_status: "ok" | "error" | "running" | null;
  last_error: string | null;
  run_count: number;
}

export interface RoutineIn {
  name: string;
  prompt: string;
  schedule: RoutineSchedule;
  enabled?: boolean;
}

export const routinesApi = {
  list: () => api<Routine[]>("/routines"),
  create: (body: RoutineIn) => api<Routine>("/routines", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Partial<RoutineIn>) => api<Routine>(`/routines/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id: string) => api<void>(`/routines/${id}`, { method: "DELETE" }),
  run: (id: string) => api<{ status: string }>(`/routines/${id}/run`, { method: "POST" }),
};
