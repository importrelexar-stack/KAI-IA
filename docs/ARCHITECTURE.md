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

## Integraciones y rutinas (Fase 6)

- `app/integrations/mcp_manager.py`: `McpManager` mantiene una `McpConnection` por servidor MCP. Cada
  conexión es una tarea asyncio que abre la sesión (stdio o HTTP streamable con el SDK oficial `mcp`),
  lista las herramientas y atiende las llamadas desde una cola (los contextos de MCP se abren y cierran
  en la misma tarea). Configuración en `settings.mcp_servers`; secretos en el almacén de credenciales.
- `app/integrations/mcp_tools.py`: el ejecutor de herramientas del chat deriva los nombres `mcp_*` acá:
  permitir → llamada directa; preguntar → tarea `awaiting_approval` con `action.kind = "mcp"`, que el
  endpoint de aprobación ejecuta (desde su hilo, en el loop de KAI con `run_coroutine_threadsafe`).
- `app/routines/`: `schedule.py` (horarios y próxima ejecución en hora local con DST) y `runner.py`
  (planificador cada 30 s que llama a `stream_chat` con la conversación propia de cada rutina).
- Web: `web_search_20260209` y `web_fetch_20260209` son herramientas del servidor de Anthropic.

## App de escritorio (Fase 4b)

```
KAI AI.exe (Tauri 2, WebView2)
  ├─ pantalla de carga local (apps/desktop/splash)
  ├─ inicia kai-core.exe (PyInstaller: KAI Core + interfaz + voz) con KAI_PARENT_PID y KAI_SHUTDOWN_TOKEN
  ├─ espera /api/v1/health y navega a http://127.0.0.1:8765 (misma interfaz que la versión web)
  ├─ bandeja (Abrir/Salir), Ctrl+Alt+K, instancia única
  └─ al salir: POST /api/v1/system/shutdown (token) → si no responde, termina el proceso
kai-core: si la app desaparece, el watchdog lo detecta y se detiene.
```

La interfaz no usa IPC de Tauri: habla con KAI Core por HTTP como en el navegador, así que una sola
base de código sirve para web, escritorio y, más adelante, Android.

## Automatización (Fase 4)

```
Claude ─tool_use─► automation_tools.request
                     ├─ nivel "deny"  → error
                     ├─ lectura / "allow" → prepare (valida) → execute → resultado
                     └─ "ask" → prepare (vista previa) → Task(awaiting_approval, action)
Usuario ─Autorizar─► POST /tasks/{id}/approval → run_approved → execute (re-valida permisos)
                     → Task completed/failed + mensaje en la conversación + auditoría
```

- `automation/permissions.py`: `Permissions` (carpetas, apps, scripts, niveles) y `PathGuard`, que
  resuelve rutas (incluidos enlaces simbólicos), exige que estén dentro de una carpeta autorizada, respeta
  sólo-lectura y bloquea carpetas del sistema, la carpeta de datos de KAI y nombres sensibles.
- `automation/files.py`: operaciones (listar, buscar, leer texto/PDF/DOCX, crear, escribir con copia de
  seguridad, mover sin sobrescribir, plan de orden, papelera con `send2trash`, abrir con `os.startfile`,
  scripts con `subprocess` sin shell y con tiempo máximo).
- `agents/automation_tools.py`: integra todo con el orquestador y el motor de tareas.

## Memoria y agentes (Fase 3)

```
Mensaje → preferencias aprobadas (system) + memorias relevantes (FTS5/BM25, bloque <memoria_relevante>)
        → Claude con herramientas ──tool_use──► run_tool (validación Pydantic) ──► SQLite
                  ▲                                                   │
                  └────────────── tool_result ◄──────────────────────┘   (hasta N pasos)
```

- `memory/store.py`: memorias con índice FTS5 (`unicode61 remove_diacritics 2`, sin acentos); si SQLite
  no trae FTS5 se usa búsqueda simple. La interfaz `MemoryStore.search` permite sumar embeddings después.
- `memory/projects.py`: proyectos con registro de decisiones/avances, archivos y próximos pasos.
- `agents/tools.py`: herramientas por agente (Memory, Planner) con esquemas autocontenidos
  (`additionalProperties: false`). Lo que manda el modelo se valida antes de ejecutar; los errores vuelven
  como `tool_result` con `is_error`. Ninguna herramienta borra datos ni sale del equipo.
- `providers/anthropic_provider.py`: bucle de tool use con streaming; reenvía el contenido del asistente
  tal cual (incluye bloques de pensamiento) y maneja `pause_turn` (búsqueda web del servidor). Corta por
  pasos (`max_tool_iterations`), tokens por solicitud o tiempo, avisando al usuario.
- Estado `executing` en el núcleo visual mientras corre una herramienta; auditoría `agent.tool`.
- `database/migrations.py`: agrega columnas nuevas y el índice FTS5 a bases existentes.

## Voz

```
Interfaz: micrófono → AudioWorklet (PCM) → detector de voz (energía + ruido adaptativo, pre-roll 450 ms)
          → WAV 16 kHz mono en memoria → POST /voice/transcribe
KAI Core: WhisperSTT (faster-whisper, CPU int8, VAD) → texto → /chat (channel=voice) → Claude
          → respuesta → POST /voice/synthesize → PiperTTS (es_AR) → WAV → reproducción (setSinkId)
```

- `voice/base.py` define `SpeechToText` y `TextToSpeech`; `WhisperSTT` y `PiperTTS` son las
  implementaciones locales; la interfaz puede usar la Web Speech API del navegador como alternativa.
- Los modelos se cargan de forma diferida y se ejecutan en hilos (`asyncio.to_thread`) con un lock por motor.
- La descarga de modelos es explícita (botón) y se informa por WebSocket.
- **Manos libres**: la interfaz entrega cada frase detectada a Whisper local; sólo si empieza con «Hey KAI»
  (variantes tolerantes: «Ey Kai», «Oye Kay»…) se envía la orden a Claude. Durante la respuesta hablada, si
  el usuario habla, se interrumpe (barge-in).
- Estados: la interfaz informa `listening` / `speaking` (`/voice/state`); KAI Core los muestra cuando no
  tiene trabajo propio (`processing` tiene prioridad).
- El audio nunca se escribe en disco ni en la base.

## Estado del asistente

`StateManager` mantiene el estado real (`idle`, `listening`, `processing`, `speaking`, `executing`,
`error`), cuenta operaciones concurrentes y publica cada cambio en el `EventBus`. El WebSocket
`/api/v1/ws/events` reenvía esos eventos (y los de tareas y descargas de voz) a todas las interfaces.
`executing` se usará en la Fase 4.

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
