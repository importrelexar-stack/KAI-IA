# Arquitectura de KAI AI

## Capas

```
┌──────────────────────────── Interfaces ────────────────────────────┐
│  Web (React/Vite)   ·   Desktop (Tauri, plan)   ·   Android (plan) │
└──────────────┬──────────────────────────────┬──────────────────────┘
        HTTP + SSE (/api/v1)          WebSocket (/api/v1/ws/events)
┌──────────────▼──────────────────────────────▼──────────────────────┐
│                           KAI CORE (FastAPI)                       │
│  api/v1  →  services (chat, settings, usage)  →  providers         │
│  core: config · StateManager/EventBus · persona · errors · logging │
│  automation: motor de tareas   ·   cowork: CoworkBridge            │
│  security: secretos · control de acceso · rate limit · auditoría   │
│  agents (catálogo) · memory (Fase 3) · voice (interfaces, Fase 2)  │
└──────────────┬──────────────────────────────┬──────────────────────┘
          SQLAlchemy                     SDK oficial `anthropic`
┌──────────────▼─────────────┐   ┌────────────▼───────────────────────┐
│  SQLite (data/kai.db)      │   │  Claude API (Messages, streaming)  │
└────────────────────────────┘   └────────────────────────────────────┘
```

## Flujo de un mensaje

1. La interfaz hace `POST /api/v1/chat` con `stream: true`.
2. `chat_service.stream_chat`:
   - verifica proveedor configurado, límite por minuto y presupuesto diario;
   - crea la conversación si no existe y guarda el mensaje del usuario;
   - arma el contexto con los últimos `history_window` mensajes (roles alternados, empieza en `user`);
   - pasa el estado a `processing` (el núcleo visual lo refleja por WebSocket);
   - transmite los fragmentos como eventos SSE `delta`;
   - al terminar guarda la respuesta, registra el consumo y vuelve a `idle` (o `error`).
3. Si el cliente cancela, se guarda lo recibido con `stop_reason = "cancelled"`.

Eventos SSE: `meta` (ids y título) → `delta`* → `done` | `error`.

## Proveedores de IA intercambiables

`providers/base.py` define `AIProvider` (`stream_chat`, `validate`, `configured`). Implementaciones:

- `AnthropicProvider`: SDK oficial, `client.beta.messages.stream`, `output_config.effort`,
  `cache_control` automático, `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`) en
  Opus 5.5 / Sonnet 5.5 / Fable 5.1, manejo de `stop_reason == "refusal"` y mapeo de errores a mensajes
  claros. El pensamiento adaptativo es el comportamiento por defecto de estos modelos.
- `DemoProvider`: sin IA, respuestas marcadas como demostración.

Para agregar otro proveedor: implementar `AIProvider` y registrarlo en `core/context.py`
(`provider_factory`). KAI Core no conoce detalles de ningún proveedor fuera de esa interfaz.

## Estado del asistente

`StateManager` mantiene el estado real (`idle`, `listening`, `processing`, `speaking`, `executing`,
`error`), cuenta operaciones concurrentes y publica cada cambio en el `EventBus`. El WebSocket
`/api/v1/ws/events` reenvía esos eventos (y los de tareas) a todas las interfaces. `listening`,
`speaking` y `executing` se usarán en las fases 2 y 4; la interfaz ya sabe animarlos.

## Persistencia

| Tabla | Contenido |
|---|---|
| `conversations`, `messages` | Historial (memoria conversacional) |
| `settings` | Preferencias del usuario (JSON) |
| `usage` | Tokens por día y modelo (control de costos) |
| `tasks` | Tareas, estado, autorizaciones, historial |
| `cowork_handoffs` | Transferencias a Cowork y resultados |
| `audit_log` | Auditoría de acciones |

Todas las entidades tienen `user_id` (hoy `local`) para soportar múltiples usuarios más adelante.

## CoworkBridge

Investigación (oct. 2026): Claude Cowork corre dentro de Claude Desktop; las superficies programáticas
oficiales son de administración/monitoreo (Analytics API, OpenTelemetry). No hay API pública para crear o
controlar sesiones. Por eso:

- `CoworkAdapter` es la interfaz de extensión; `ManualCoworkAdapter` es la única implementación.
- `prepare` genera instrucciones Markdown con objetivo, contexto, extracto opcional de conversación,
  carpetas, entregables, restricciones de seguridad y formato de cierre con referencia.
- El usuario las copia/exporta a Cowork, y luego importa el texto de resultado y los archivos.
- Lo importado se trata como **datos no confiables**.

Si Anthropic publica una integración oficial, se implementa otro adaptador sin cambiar la API.

## Motor de tareas

Máquina de estados en `automation/tasks.py`:

```
pending ──► awaiting_approval ──► running ──► completed
   │              │                  ├──────► failed ──► pending (reintento, exige nueva autorización)
   └──────────────┴──────────────────┴──────► cancelled
```

Una tarea con `requires_approval` no puede pasar a `running` sin una aprobación vigente. En la Fase 1 las
transiciones son manuales; la ejecución de herramientas llega en la Fase 4.

## Decisiones

- **Servidor local único** en `127.0.0.1:8765` que sirve API e interfaz compilada: un solo proceso que
  Tauri podrá administrar como sidecar.
- **SSE para el chat** (simple, compatible con proxies y `fetch`), **WebSocket** para eventos de estado.
- **Router por hash** en la SPA: funciona igual servido por FastAPI, Vite o Tauri.
- **keyring** para secretos: usa el Administrador de credenciales en Windows sin código específico.
