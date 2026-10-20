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
  created_at: string;
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
  created_at: string;
  updated_at: string;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  status: "active" | "planned";
  phase: number;
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
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id: conversationId, stream: true }),
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
