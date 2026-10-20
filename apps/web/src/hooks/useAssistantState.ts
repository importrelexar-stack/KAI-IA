import { useEffect, useRef, useState } from "react";
import type { AssistantState } from "../lib/api";

export interface RealtimeEvent {
  type: string;
  [k: string]: unknown;
}

/** Estado real del asistente vía WebSocket (/api/v1/ws/events), con reconexión. */
export function useAssistantState(onEvent?: (e: RealtimeEvent) => void) {
  const [state, setState] = useState<AssistantState>("idle");
  const [detail, setDetail] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    let attempt = 0;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/api/v1/ws/events`);
      ws.onopen = () => {
        attempt = 0;
        setConnected(true);
      };
      ws.onmessage = (msg) => {
        try {
          const ev = JSON.parse(msg.data) as RealtimeEvent;
          if (ev.type === "state") {
            setState(ev.state as AssistantState);
            setDetail((ev.detail as string | null) ?? null);
          }
          if (ev.type !== "ping") handler.current?.(ev);
        } catch {
          /* mensaje inválido */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, Math.min(10_000, 1000 * 2 ** attempt++));
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      ws?.close();
    };
  }, []);

  return { state, detail, connected };
}
