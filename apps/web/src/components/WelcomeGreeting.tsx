import { useEffect, useRef, useState } from "react";
import { BarChart3, Boxes, CalendarRange, FileText, Megaphone, Send, X } from "lucide-react";
import { KaiCore } from "./KaiCore";
import { get, synthesize, type SettingsOut, type VoiceStatus } from "../lib/api";
import { askKai } from "../lib/nav";
import { browserVoice } from "../lib/speech";

const SEEN_KEY = "kai.greeted";

const RULES = "Comparaciones como «monto anterior → monto actual → diferencia $ → variación %». No inventes datos: si te falta "
  + "información, pedímela (puedo adjuntarte el Excel/CSV o conectar una integración). Terminá con CONCLUSIONES Y ACCIONES RECOMENDADAS.";

export const REPORTS = [
  { icon: BarChart3, title: "Ventas de la semana", text: "Por cuenta, comparado con la semana anterior",
    prompt: "Armame el reporte semanal de ventas de Mercado Libre: total por cuenta, comparación con la semana anterior, ranking de cuentas y productos/SKU con mayor y menor crecimiento." },
  { icon: CalendarRange, title: "Cierre del mes", text: "Facturación, cancelaciones y proyección",
    prompt: "Armame el reporte mensual de gestión de Mercado Libre: ventas por cuenta y por producto, comparación con el mes anterior, cancelaciones, devoluciones y reclamos, y proyección de ventas." },
  { icon: Megaphone, title: "Mercado Ads", text: "Inversión, ventas por publicidad y ROAS",
    prompt: "Armame el reporte de Mercado Ads: inversión, ventas por publicidad y ROAS por campaña y por publicación, qué potenciar, dónde reducir inversión y publicaciones con inversión alta y bajo retorno." },
  { icon: Boxes, title: "Stock y reposición", text: "Cobertura, riesgo de quiebre y exceso",
    prompt: "Armame el reporte de stock: stock disponible, rotación por SKU, días de cobertura, productos con riesgo de quedarse sin stock, exceso de inventario y TOP de reposición." },
  { icon: FileText, title: "Ejecutivo de una página", text: "Resumen general con lo más importante",
    prompt: "Armame un reporte ejecutivo de una página con lo más importante de ventas, publicidad y stock, con totales destacados y porcentajes de variación." },
] as const;

function greetingWord(d: Date) {
  const h = d.getHours();
  return h < 6 ? "Buenas noches" : h < 13 ? "Buen día" : h < 20 ? "Buenas tardes" : "Buenas noches";
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Bienvenida al abrir KAI: saludo, fecha y hora, y «¿Qué reporte querés que te arme?». Una vez por apertura. */
export function WelcomeGreeting() {
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const [name, setName] = useState("");
  const [custom, setCustom] = useState("");
  const speakCtrl = useRef<AbortController | null>(null);

  useEffect(() => {
    let seen = false;
    try { seen = sessionStorage.getItem(SEEN_KEY) === "1"; } catch { /* sin almacenamiento */ }
    if (seen) return;
    get<SettingsOut>("/settings").then((s) => {
      const p = s.preferences;
      if (!p.startup_greeting) return;
      try { sessionStorage.setItem(SEEN_KEY, "1"); } catch { /* idem */ }
      const userName = p.user_name?.trim() ?? "";
      setName(userName);
      setOpen(true);
      if (p.startup_greeting_voice) void speakGreeting(userName, p.language || "es-AR");
    }).catch(() => { /* KAI Core todavía no responde: no se muestra */ });
    return () => speakCtrl.current?.abort();
  }, []);

  useEffect(() => {
    if (!open) return;
    const t = setInterval(() => setNow(new Date()), 1000);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", onKey);
    return () => { clearInterval(t); window.removeEventListener("keydown", onKey); };
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  async function speakGreeting(userName: string, lang: string) {
    const d = new Date();
    const text = `${greetingWord(d)}${userName ? `, ${userName}` : ""}. Hoy es ${d.toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" })}, `
      + `son las ${d.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", hour12: false })}. ¿Qué reporte querés que te arme?`;
    const ctrl = new AbortController();
    speakCtrl.current = ctrl;
    try {
      const v = await get<VoiceStatus>("/voice/status");
      const local = v.preferences.voice_tts_engine !== "browser" && v.tts.installed && v.tts.model_ready;
      if (local) {
        const blob = await synthesize(text, ctrl.signal);
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        ctrl.signal.addEventListener("abort", () => audio.pause(), { once: true });
        audio.onended = () => URL.revokeObjectURL(url);
        await audio.play();
      } else if (browserVoice.ttsAvailable()) {
        await browserVoice.speak(text, lang, ctrl.signal);
      }
    } catch { /* sin voz disponible o el sistema no permite reproducir: el saludo igual se ve */ }
  }

  function close() {
    speakCtrl.current?.abort();
    setOpen(false);
  }

  function choose(prompt: string) {
    close();
    askKai(`${prompt.trim().replace(/[.\s]+$/, "")}. ${RULES}`);
  }

  if (!open) return null;
  const date = capitalize(now.toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long", year: "numeric" }));
  const time = now.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", hour12: false });

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="welcome-title">
      <div className="panel fade-up relative w-full max-w-3xl overflow-hidden p-8">
        <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-electric/20 blur-3xl" aria-hidden />
        <button className="absolute right-4 top-4 rounded-lg p-1.5 text-muted hover:bg-white/5 hover:text-ink" onClick={close} aria-label="Cerrar bienvenida">
          <X className="h-5 w-5" />
        </button>
        <div className="relative flex flex-col items-center gap-6 text-center md:flex-row md:text-left">
          <KaiCore state="speaking" size={120} />
          <div className="flex-1">
            <h2 id="welcome-title" className="text-gradient text-3xl font-semibold tracking-tight md:text-4xl">
              {greetingWord(now)}{name ? `, ${name}` : ""}
            </h2>
            <p className="mt-2 text-muted">{date}</p>
            <p className="font-[family-name:var(--font-display)] text-4xl font-light tracking-wider text-cyan" aria-live="off">{time}</p>
          </div>
        </div>

        <p className="relative mt-7 text-lg font-medium">¿Qué reporte querés que te arme?</p>
        <div className="relative mt-3 grid gap-2 sm:grid-cols-2">
          {REPORTS.map(({ icon: Icon, title, text, prompt }) => (
            <button key={title} className="panel panel-hover flex items-center gap-3 p-3 text-left" onClick={() => choose(prompt)}>
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-electric/25 to-violet/15 text-cyan"><Icon className="h-4 w-4" /></span>
              <span className="min-w-0">
                <span className="block text-sm font-medium">{title}</span>
                <span className="block truncate text-xs text-muted">{text}</span>
              </span>
            </button>
          ))}
        </div>
        <form className="relative mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (custom.trim()) choose(custom); }}>
          <label htmlFor="welcome-custom" className="sr-only">Otro reporte</label>
          <input id="welcome-custom" className="field" placeholder="Otro reporte… (ej.: ventas de ayer de la cuenta principal)" value={custom}
            onChange={(e) => setCustom(e.target.value)} />
          <button className="btn btn-primary" disabled={!custom.trim()} aria-label="Pedir reporte"><Send className="h-4 w-4" /></button>
        </form>
        <div className="relative mt-5 flex items-center justify-between text-xs text-muted">
          <span>Si te falta el archivo, KAI te lo va a pedir: podés adjuntar Excel, CSV o PDF en el chat.</span>
          <button className="underline hover:text-ink" onClick={close}>Ahora no</button>
        </div>
      </div>
    </div>
  );
}
