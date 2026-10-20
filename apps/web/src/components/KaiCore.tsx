import type { AssistantState } from "../lib/api";

export const STATE_LABEL: Record<AssistantState, string> = {
  idle: "En espera",
  listening: "Escuchando",
  processing: "Procesando",
  speaking: "Hablando",
  executing: "Ejecutando tareas",
  error: "Error",
};

/** Núcleo visual animado. La animación refleja el estado real que informa KAI Core. */
export function KaiCore({ state, size = 220 }: { state: AssistantState; size?: number }) {
  return (
    <div
      className="kai-core"
      data-state={state}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Estado de KAI: ${STATE_LABEL[state]}`}
    >
      <span className="ring" />
      <span className="ring-dash" />
      <span className="wave" />
      <span className="wave" />
      <span className="orb" />
    </div>
  );
}
