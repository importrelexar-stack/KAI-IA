"""Dispositivos vinculados (Fase 5): emparejamiento por código de un solo uso y tokens por dispositivo.

Seguridad:
- El código de vinculación dura 5 minutos, sirve una sola vez y se invalida tras varios intentos fallidos.
- Cada dispositivo recibe su propio token; KAI guarda sólo el hash SHA-256 y se puede revocar.
- Las conexiones remotas sólo se aceptan desde redes privadas (LAN, Tailscale/CGNAT, IPv6 ULA),
  nunca desde direcciones públicas, y sólo si el acceso remoto está activado.
- Un dispositivo vinculado no puede administrar KAI (clave de API, permisos, dispositivos).
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import secrets
import socket
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import KaiError, NotFoundError
from app.models.entities import Device, PairingCode, SettingEntry, utcnow

PAIRING_TTL = timedelta(minutes=5)
MAX_FAILED_ATTEMPTS = 10
TOKEN_PREFIX = "kaid_"
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sin 0/O, 1/I/L
_REMOTE_KEY = "remote_access"
_CGNAT = ipaddress.ip_network("100.64.0.0/10")  # Tailscale
# Lista explícita: `ip.is_private` de Python también incluye redes de documentación y de pruebas.
_PRIVATE_NETS = [ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7")]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------- Red ----------

def is_private_address(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_loopback:
        return True
    return any(ip.version == net.version and ip in net for net in _PRIVATE_NETS)


def host_header_allowed_remote(host: str) -> bool:
    """Encabezado Host aceptable para conexiones desde la red privada."""
    host = host.lower().strip()
    if is_private_address(host):
        return True
    if host.endswith(".ts.net") or host.endswith(".local"):
        return True
    try:
        return host == socket.gethostname().lower()
    except OSError:
        return False


def local_addresses() -> list[str]:
    """Direcciones privadas de este equipo (LAN y Tailscale) para armar el QR."""
    found: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            addr = info[4][0]
            if ":" not in addr and is_private_address(addr) and not addr.startswith("127."):
                found.append(addr)
    except OSError:
        pass
    try:  # dirección de la interfaz principal (no envía paquetes)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            addr = s.getsockname()[0]
            if is_private_address(addr) and not addr.startswith("127."):
                found.append(addr)
    except OSError:
        pass
    # Tailscale primero (cifrado de extremo a extremo), después la LAN
    unique = list(dict.fromkeys(found))
    return sorted(unique, key=lambda a: (ipaddress.ip_address(a) not in _CGNAT, a))


# ---------- Acceso remoto ----------

def remote_enabled(db: Session) -> bool:
    row = db.get(SettingEntry, _REMOTE_KEY)
    return bool(row and isinstance(row.value, dict) and row.value.get("enabled"))


def set_remote_enabled(db: Session, enabled: bool) -> None:
    row = db.get(SettingEntry, _REMOTE_KEY)
    if row is None:
        db.add(SettingEntry(key=_REMOTE_KEY, value={"enabled": enabled}))
    else:
        row.value = {"enabled": enabled}
    db.commit()


# ---------- Vinculación ----------

def create_pairing_code(db: Session) -> tuple[str, datetime]:
    db.execute(update(PairingCode).where(PairingCode.used.is_(False)).values(used=True))
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    code = f"{raw[:4]}-{raw[4:]}"
    expires = utcnow() + PAIRING_TTL
    db.add(PairingCode(code_hash=_hash(raw), expires_at=expires))
    db.commit()
    return code, expires


def normalize_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", code.upper())


def pair_device(db: Session, code: str, name: str, platform: str, ip: str | None) -> tuple[Device, str]:
    now = utcnow()
    active = list(db.execute(select(PairingCode).where(PairingCode.used.is_(False))).scalars())
    match = next((p for p in active if p.code_hash == _hash(normalize_code(code))
                  and _aware(p.expires_at) > now), None)
    if match is None:
        for p in active:  # cada intento fallido acerca el bloqueo del código vigente
            p.attempts += 1
            if p.attempts >= MAX_FAILED_ATTEMPTS:
                p.used = True
        db.commit()
        raise KaiError("Código de vinculación inválido o vencido. Generá uno nuevo en KAI (Configuración → "
                       "Dispositivos).", code="invalid_pairing_code", status_code=403)
    match.used = True
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    device = Device(name=name.strip()[:80] or "Teléfono", platform=platform[:32], token_hash=_hash(token),
                    last_seen_at=now, last_ip=ip)
    db.add(device)
    db.commit()
    return device, token


def authenticate(db: Session, token: str, ip: str | None) -> Device | None:
    if not token.startswith(TOKEN_PREFIX):
        return None
    device = db.execute(select(Device).where(Device.token_hash == _hash(token))).scalars().first()
    if device is None or device.revoked:
        return None
    now = utcnow()
    if device.last_seen_at is None or now - _aware(device.last_seen_at) > timedelta(seconds=60) or device.last_ip != ip:
        device.last_seen_at = now
        device.last_ip = ip
        db.commit()
    return device


def revoke(db: Session, device_id: str) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise NotFoundError("El dispositivo no existe.")
    device.revoked = True
    db.commit()
    return device


# ---------- Qué puede hacer un dispositivo vinculado ----------

_DEVICE_RULES: list[tuple[set[str], re.Pattern[str]]] = [
    ({"GET"}, re.compile(r"^/api/v1/(health|system/status|agents|devices/me|voice/status|settings)$")),
    ({"GET"}, re.compile(r"^/api/v1/(conversations|tasks|memory|projects|cowork/handoffs)(/[^/]+)?(/files/.+)?$")),
    ({"GET"}, re.compile(r"^/api/v1/memory/search$")),
    ({"POST"}, re.compile(r"^/api/v1/(chat|chat/attachments|tasks|voice/transcribe|voice/synthesize|voice/state)$")),
    ({"POST"}, re.compile(r"^/api/v1/tasks/[^/]+/(approval|transition)$")),
    ({"POST"}, re.compile(r"^/api/v1/memory/[^/]+/approve$")),
    ({"PATCH", "DELETE"}, re.compile(r"^/api/v1/conversations/[^/]+$")),
    ({"GET"}, re.compile(r"^/api/v1/ws/events$")),
]


def device_may(method: str, path: str) -> bool:
    return any(method in methods and rx.match(path) for methods, rx in _DEVICE_RULES)
