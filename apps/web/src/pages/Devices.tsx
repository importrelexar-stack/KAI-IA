import { useEffect, useState } from "react";
import { Loader2, QrCode, RefreshCw, Smartphone, Trash2 } from "lucide-react";
import { Badge, Card, Notice, PageHeader, formatDate } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { devicesApi, type Device, type PairingOut, type RemoteStatus } from "../lib/api";

/** Fase 5: acceso desde el teléfono por la red privada (LAN o Tailscale) y dispositivos vinculados. */
export function DevicesPage() {
  const remote = useApi<RemoteStatus>("/devices/remote");
  const devices = useApi<Device[]>("/devices");
  const [pairing, setPairing] = useState<PairingOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!pairing) return;
    const t = setInterval(() => {
      setNow(Date.now());
      void devices.reload();
    }, 3000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pairing]);

  const left = pairing ? Math.max(0, Math.round((new Date(pairing.expires_at).getTime() - now) / 1000)) : 0;

  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(enabled: boolean) {
    const r = await run(() => devicesApi.setRemote(enabled));
    if (r) remote.setData(r);
    if (!enabled) setPairing(null);
  }

  const r = remote.data;
  const active = devices.data?.filter((d) => !d.revoked) ?? [];

  return (
    <div className="space-y-4">
      <PageHeader title="Dispositivos" subtitle="Usá KAI desde tu teléfono Android dentro de tu red privada." actions={
        <button className="btn" onClick={() => { void remote.reload(); void devices.reload(); }}><RefreshCw className="h-4 w-4" />Actualizar</button>
      } />
      {(error || remote.error) && <Notice tone="danger">{error ?? remote.error}</Notice>}

      <Card title="Acceso remoto">
        {r ? (
          <div className="space-y-3 text-sm">
            <label className="flex items-center gap-3">
              <input type="checkbox" checked={r.enabled} disabled={busy} onChange={(e) => void toggle(e.target.checked)} />
              <span>Permitir que dispositivos vinculados se conecten a KAI</span>
            </label>
            <p className="text-muted">
              KAI sólo acepta conexiones desde redes privadas (tu Wi-Fi o <strong>Tailscale</strong>) y nunca desde Internet.
              Cada teléfono necesita vincularse con un código. Recomendado: Tailscale, porque cifra la conexión
              y funciona fuera de casa sin abrir puertos del router.
            </p>
            {r.restart_required && (
              <Notice tone="warn">
                {r.enabled
                  ? "Reiniciá KAI (stop.bat y start.bat, o Salir y abrir la app) para que empiece a escuchar en la red privada."
                  : "Reiniciá KAI para que deje de escuchar en la red."}
                {" "}Windows puede pedirte permiso en el firewall: aceptá sólo para «Redes privadas».
              </Notice>
            )}
            {r.enabled && !r.restart_required && <Badge tone="ok">Escuchando en la red privada · puerto {r.port}</Badge>}
            {r.enabled && r.addresses.length === 0 && <Notice tone="warn">No se encontró ninguna dirección de red privada en este equipo.</Notice>}
            {r.addresses.length > 0 && <p className="text-muted">Direcciones de este equipo: {r.addresses.join(", ")}</p>}
          </div>
        ) : <Loader2 className="h-4 w-4 animate-spin" />}
      </Card>

      <Card title="Vincular un teléfono">
        {!r?.enabled ? (
          <p className="text-sm text-muted">Activá el acceso remoto para generar un código.</p>
        ) : (
          <div className="flex flex-col gap-4 md:flex-row md:items-start">
            <div className="space-y-2 text-sm md:w-1/2">
              <ol className="list-decimal space-y-1 pl-5 text-muted">
                <li>Instalá la app KAI en tu Android.</li>
                <li>Conectá el teléfono a la misma red Wi-Fi o a tu red Tailscale.</li>
                <li>En la app tocá «Vincular» y escaneá el QR, o escribí el código.</li>
              </ol>
              <button className="btn btn-primary" disabled={busy || r.restart_required} onClick={() => void run(async () => setPairing(await devicesApi.pairing()))}>
                <QrCode className="h-4 w-4" />{pairing ? "Generar otro código" : "Generar código"}
              </button>
              {r.restart_required && <p className="text-xs text-warn">Primero reiniciá KAI.</p>}
            </div>
            {pairing && (
              <div className="rounded-xl border border-line p-4 text-center md:w-1/2">
                {left > 0 ? (
                  <>
                    <div className="mx-auto w-48 rounded-lg bg-white p-2 [&_svg]:h-auto [&_svg]:w-full" aria-label="Código QR de vinculación"
                      dangerouslySetInnerHTML={{ __html: pairing.qr_svg }} />
                    <p className="mt-3 font-mono text-2xl tracking-[0.3em]">{pairing.code}</p>
                    <p className="text-xs text-muted">Vence en {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")} · sirve una sola vez</p>
                    <p className="mt-1 text-xs text-muted">{pairing.urls.join(" · ")}</p>
                  </>
                ) : <p className="text-sm text-muted">El código venció. Generá uno nuevo.</p>}
              </div>
            )}
          </div>
        )}
      </Card>

      <Card title={`Dispositivos vinculados (${active.length})`}>
        {devices.data && devices.data.length === 0 && <p className="text-sm text-muted">Todavía no vinculaste ningún dispositivo.</p>}
        <ul className="divide-y divide-line">
          {devices.data?.map((d) => (
            <li key={d.id} className="flex items-center gap-3 py-2 text-sm">
              <Smartphone className="h-4 w-4 text-muted" aria-hidden />
              <div className="flex-1">
                <div>{d.name} <span className="text-muted">· {d.platform}</span></div>
                <div className="text-xs text-muted">
                  Vinculado {formatDate(d.created_at)}{d.last_seen_at && ` · última conexión ${formatDate(d.last_seen_at)}`}{d.last_ip && ` desde ${d.last_ip}`}
                </div>
              </div>
              {d.revoked ? <Badge>Revocado</Badge> : (
                <button className="btn btn-danger" disabled={busy}
                  onClick={() => { if (confirm(`¿Revocar «${d.name}»? Ese teléfono dejará de tener acceso.`)) void run(async () => { await devicesApi.revoke(d.id); await devices.reload(); }); }}>
                  <Trash2 className="h-4 w-4" />Revocar
                </button>
              )}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
