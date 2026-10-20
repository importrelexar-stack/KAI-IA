# API de KAI Core (v1)

Base: `http://127.0.0.1:8765/api/v1` · Documentación interactiva: `/docs` · Contrato: `shared/openapi.json`.

Errores con formato uniforme:

```json
{ "error": { "code": "provider_not_configured", "message": "…", "details": [] } }
```

Clientes que no sean locales (teléfonos en la red privada, con el acceso remoto activado) envían
`Authorization: Bearer kaid_…` (token del dispositivo) — o `X-KAI-Token: <data/access_token>` como administrador.

## Sistema

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Vida y estado del asistente |
| GET | `/system/status` | Versión, base, proveedor, clave (sin revelar), consumo, presupuesto, funciones |
| GET | `/agents` | Catálogo de agentes con su estado real (`active` / `planned`) |
| GET | `/audit?limit=` | Registro de auditoría |
| WS | `/ws/events` | Eventos `state`, `task`, `voice_download`, `ping` |

## Chat e historial

`POST /chat`

```json
{ "message": "Hola KAI", "conversation_id": null, "stream": true, "channel": "text", "attachment_ids": [] }
```

`message` puede ir vacío si hay `attachment_ids` (máx. 5, subidos antes con `POST /chat/attachments`).

- `stream: true` → `text/event-stream`:

  ```
  event: meta
  data: {"type":"meta","conversation_id":"…","user_message":{…},"title":"Hola KAI","provider":"anthropic"}

  event: delta
  data: {"type":"delta","text":"¡Hola! "}

  event: done
  data: {"type":"done","conversation_id":"…","assistant_message":{…},"served_by_fallback":false,"usage":{…}}
  ```

  o `event: error` con `code`, `message`, `status`.
- `stream: false` → JSON `{conversation_id, user_message, assistant_message, served_by_fallback}`.

Códigos: `503 provider_not_configured`, `429 rate_limited` / `budget_exceeded`, `401 auth_failed`,
`404 not_found` / `model_not_found`, `400 bad_request`, `502 upstream_error`, `503 connection_error`.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/conversations?limit=&offset=&q=` | Lista (más reciente primero) |
| GET | `/conversations/{id}` | Conversación con mensajes |
| PATCH | `/conversations/{id}` | Renombrar `{ "title": "…" }` |
| DELETE | `/conversations/{id}` | Eliminar (auditada) |
| DELETE | `/conversations?confirm=true` | Eliminar todo (sin `confirm` → `428`) |
| POST | `/chat/attachments` | Multipart `file`: documento (texto/PDF/Word → texto extraído) o imagen (JPEG/PNG/WebP/GIF ≤ 5 MB). Devuelve `{id, name, kind, media_type, size, chars}` |

## Dispositivos (Fase 5)

| Método | Ruta | Quién | Descripción |
|---|---|---|---|
| GET / PUT | `/devices/remote` | sólo la PC | Estado / activar acceso remoto `{ "enabled": true }` (requiere reiniciar KAI) |
| POST | `/devices/pairing` | sólo la PC | Código de 8 caracteres, vencimiento, URLs, `payload` (`kai://pair?c=…&u=…`) y `qr_svg` |
| POST | `/devices/pair` | teléfono | `{ "code", "name", "platform" }` → `{ "token", "device_id", "name" }` (5 intentos/min) |
| GET | `/devices/me` | teléfono | Dispositivo que consulta |
| DELETE | `/devices/me` | teléfono | Desvincularse (revoca su token) |
| GET | `/devices` | sólo la PC | Dispositivos vinculados |
| DELETE | `/devices/{id}` | sólo la PC | Revocar |

Errores: `403 public_network`, `403 remote_disabled`, `401 unauthorized`, `403 device_forbidden`,
`403 local_only`, `403 invalid_pairing_code`.

## Configuración

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/settings` | Preferencias, estado de la clave, modelos y niveles de esfuerzo |
| PUT | `/settings` | Actualización parcial de preferencias |
| PUT | `/settings/api-key` | Guardar clave `{ "api_key": "sk-ant-…" }` |
| DELETE | `/settings/api-key` | Borrar clave guardada |
| POST | `/settings/api-key/test` | Validar la clave listando modelos (no consume tokens) |

Preferencias: `model`, `effort` (`low`…`max`), `max_tokens` (256–64000), `history_window` (2–200),
`daily_token_budget` (0 = sin límite), `use_fallbacks`, `language`, `user_name`, `custom_instructions`.

## Tareas

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/tasks?status=&limit=` | Lista ordenada por prioridad |
| POST | `/tasks` | `{ title, description, priority (1-3), requires_approval }` |
| GET | `/tasks/{id}` | Detalle |
| POST | `/tasks/{id}/transition` | `{ status, note?, result?, error? }` (transición inválida → `409`) |
| POST | `/tasks/{id}/approval` | `{ approve, note? }` (sólo en `awaiting_approval`) |

## Cowork

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/cowork/status` | Adaptador activo y capacidades reales (`official_api: false`) |
| POST | `/cowork/prepare` | Genera instrucciones (`title`, `objective`, `context`, `deliverables[]`, `constraints[]`, `folders[]`, `conversation_id?`, `include_messages`) |
| GET | `/cowork/handoffs` | Lista |
| GET | `/cowork/handoffs/{id}` | Detalle |
| GET | `/cowork/handoffs/{id}/export` | Descarga `.md` |
| POST | `/cowork/handoffs/{id}/sent` | Marca como enviada y devuelve la guía manual |
| POST | `/cowork/handoffs/{id}/result` | Importa el resultado `{ text }` |
| POST | `/cowork/handoffs/{id}/files` | Importa archivo (multipart `file`, máx. `KAI_MAX_UPLOAD_MB`) |
| GET | `/cowork/handoffs/{id}/files/{name}` | Descarga un archivo importado |
| POST | `/cowork/handoffs/{id}/cancel` | Cancela |

## Memoria y proyectos

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/memory?kind=&status=&project_id=` | Lista (`kind`: preference/fact/project; `status`: active/proposed) |
| GET | `/memory/search?q=` | Búsqueda BM25 local (sólo memorias activas) |
| POST | `/memory` | `{ kind, content, tags?, project_id? }` (rechaza secretos: `422 sensitive_memory`) |
| PATCH | `/memory/{id}` | Editar contenido, tipo, etiquetas o proyecto |
| POST | `/memory/{id}/approve` | Aprobar una propuesta de KAI |
| DELETE | `/memory/{id}` | Eliminar |
| DELETE | `/memory?confirm=true` | Eliminar toda la memoria (sin `confirm` → `428`) |
| GET/POST | `/projects` | Listar / crear `{ name, goal?, next_steps?, files? }` |
| GET | `/projects/{id}` | Proyecto con registro, tareas y notas |
| PATCH | `/projects/{id}` | Editar nombre, objetivo, próximos pasos, estado (`active`/`paused`/`done`) |
| POST | `/projects/{id}/log` | `{ kind: decision \| progress \| note, text }` |
| DELETE | `/projects/{id}` | Eliminar (sus tareas y memorias se conservan) |

Tareas: `POST /tasks` acepta `project_id` y `depends_on` (ids); una tarea no pasa a `running` hasta que
sus dependencias estén completadas. `GET /tasks?project_id=` filtra por proyecto.

Chat: con agentes activos, el stream emite eventos `tool` (`{name, summary, ok}`) y el mensaje guardado
incluye `tool_events`. WebSocket: eventos `memory` y `project`.

Preferencias nuevas: `memory_enabled`, `memory_auto_approve`, `agents_enabled`, `web_search_enabled`,
`max_tool_iterations` (1–15).

## Automatización (Fase 4)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/automation/permissions` | Carpetas, aplicaciones (con disponibilidad), scripts y nivel de cada herramienta |
| PUT | `/automation/permissions` | `{ folders: [{path, mode: read\|read_write}], apps: [{name, command}], scripts: [{name, path, timeout_seconds}], levels: {herramienta: allow\|ask\|deny} }` — valida rutas; rechaza unidades completas, la carpeta de usuario entera, carpetas del sistema y la de datos de KAI |
| GET | `/automation/browse?path=` | Lista una carpeta autorizada |

Herramientas del orquestador: `listar_carpeta`, `buscar_archivos`, `leer_archivo`, `crear_carpeta`,
`escribir_archivo`, `mover_archivo`, `organizar_carpeta`, `enviar_a_papelera`, `abrir`, `ejecutar_script`.
Cuando una acción queda pendiente, el evento `tool` del chat incluye `task_id`; la tarea queda en
`awaiting_approval` con `action` y una vista previa en `description`. `POST /tasks/{id}/approval` con
`approve: true` la ejecuta (verificando permisos otra vez), la deja `completed`/`failed` con el resultado
y agrega el resultado a la conversación.

## Voz

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/voice/status` | Motores (instalado, modelo descargado, tamaño), descargas en curso y preferencias de voz |
| POST | `/voice/models/{stt\|tts}/download` | Descarga el modelo en segundo plano (`202`); progreso por WebSocket `voice_download` |
| POST | `/voice/transcribe` | Multipart `audio` (WAV/WebM/OGG/MP3, máx. 15 MB) + `language` opcional → `{text, language, duration_seconds, engine}` |
| POST | `/voice/synthesize` | `{ text }` → `audio/wav`. El texto se limpia de Markdown/URLs antes de leerse |
| POST | `/voice/state` | `{ state: "listening" \| "speaking" \| "idle" }`: la interfaz informa su estado para el núcleo visual |

Errores: `503 voice_not_installed` / `voice_model_missing`, `422 invalid_audio` / `empty_audio`,
`413 audio_too_large`, `429 rate_limited`.

`POST /chat` acepta `channel: "voice"`: la respuesta se pide breve y sin Markdown para leerse en voz alta.

Preferencias de voz (en `/settings`): `voice_stt_engine` y `voice_tts_engine` (`local` | `browser`),
`whisper_model` (`tiny` | `base` | `small`), `piper_voice`, `voice_auto_speak`, `voice_handsfree_consent`.

## Integraciones (Fase 6, sólo desde la PC)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/integrations` | Estado de la web y de cada servidor MCP (herramientas y niveles) |
| PUT | `/integrations/web` | `{ "web_search_enabled", "web_fetch_enabled" }` |
| POST | `/integrations/mcp` | Agregar: `{ name, transport: "stdio", command, args, env, secret_env }` o `{ name, transport: "http", url, token }` |
| PATCH | `/integrations/mcp/{id}` | `{ enabled, name }` |
| POST | `/integrations/mcp/{id}/reconnect` | Reconectar |
| PUT | `/integrations/mcp/{id}/secrets` | Volver a cargar `secret_env` o `token` |
| PUT | `/integrations/mcp/{id}/tools/{tool}` | `{ "level": "allow" \| "ask" \| "deny" \| "default" }` |
| DELETE | `/integrations/mcp/{id}` | Quitar (borra sus secretos) |

Las acciones MCP con nivel «preguntar» crean una tarea `awaiting_approval` con
`action = { kind: "mcp", tool: "Servidor/herramienta", args, … }`; se ejecutan con `POST /tasks/{id}/approval`.

## Rutinas (Fase 6, sólo desde la PC)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/routines` | Lista con `schedule_text`, `next_run_at`, `last_status`, `conversation_id` |
| POST | `/routines` | `{ name, prompt, schedule }` con `schedule` = `{type:"daily",time:"08:00"}` · `{type:"weekly",days:[0..6],time}` · `{type:"interval",minutes>=15}` |
| PATCH | `/routines/{id}` | Cambiar nombre, pedido, horario o `enabled` |
| DELETE | `/routines/{id}` | Eliminar (la conversación queda en el historial) |
| POST | `/routines/{id}/run` | Ejecutar ahora (202, en segundo plano) |

Evento WebSocket `routine` al terminar cada ejecución.
