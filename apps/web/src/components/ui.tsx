import type { ReactNode } from "react";
import { AlertTriangle, Info } from "lucide-react";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-gradient text-3xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </header>
  );
}

export function Card({ title, children, className = "" }: { title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel p-5 ${className}`}>
      {title && (
        <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted">
          <span className="h-3 w-1 rounded-full bg-gradient-to-b from-cyan to-electric shadow-[0_0_8px_var(--color-cyan)]" aria-hidden />
          {title}
        </h2>
      )}
      {children}
    </section>
  );
}

const TONES = {
  ok: "bg-ok/10 text-ok border-ok/30",
  warn: "bg-warn/10 text-warn border-warn/30",
  danger: "bg-danger/10 text-danger border-danger/30",
  info: "bg-electric/10 text-cyan border-electric/30",
  muted: "bg-white/5 text-muted border-line",
} as const;

export function Badge({ tone = "muted", children }: { tone?: keyof typeof TONES; children: ReactNode }) {
  return <span className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>{children}</span>;
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "danger"; children: ReactNode }) {
  const Icon = tone === "info" ? Info : AlertTriangle;
  const color = tone === "info" ? "border-electric/30 text-ink" : tone === "warn" ? "border-warn/40 text-warn" : "border-danger/40 text-danger";
  return (
    <div className={`flex gap-3 rounded-xl border bg-graphite/70 p-3 text-sm backdrop-blur ${color}`} role={tone === "info" ? "status" : "alert"}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function FuturePage({ title, phase, description, items }: { title: string; phase: number; description: string; items: string[] }) {
  return (
    <div>
      <PageHeader title={title} subtitle={`Función futura — Fase ${phase}`} />
      <Card>
        <div className="mb-3"><Badge tone="warn">No disponible todavía</Badge></div>
        <p className="text-sm text-muted">{description}</p>
        <ul className="mt-4 space-y-1.5 text-sm">
          {items.map((i) => (
            <li key={i} className="flex gap-2"><span className="text-electric">›</span>{i}</li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-muted">Esta pantalla no simula operaciones: se habilitará cuando la función esté implementada y probada.</p>
      </Card>
    </div>
  );
}

export function formatDate(iso: string) {
  return new Date(iso).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });
}
