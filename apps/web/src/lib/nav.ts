export function navigate(route: string, param?: string) {
  location.hash = `/${route}${param ? `/${param}` : ""}`;
}

const PENDING_KEY = "kai.pendingPrompt";

/** Abre el chat en una conversación nueva y le envía este pedido a KAI. */
export function askKai(prompt: string) {
  try { sessionStorage.setItem(PENDING_KEY, prompt); } catch { /* sin almacenamiento: se usa el evento */ }
  if (location.hash === "#/chat") window.dispatchEvent(new CustomEvent("kai:ask"));
  else navigate("chat");
}

/** El chat toma (una sola vez) el pedido pendiente. */
export function takePendingPrompt(): string | null {
  try {
    const p = sessionStorage.getItem(PENDING_KEY);
    if (p) sessionStorage.removeItem(PENDING_KEY);
    return p;
  } catch {
    return null;
  }
}
