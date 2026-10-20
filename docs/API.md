# API de KAI Core (v1)

Base: `http://127.0.0.1:8765/api/v1` · Documentación interactiva: `/docs` · Contrato: `shared/openapi.json`.

Errores con formato uniforme:

```json
{ "error": { "code": "provider_not_configured", "message": "…", "details": [] } }
```

Clientes que no sean locales deben enviar `X-KAI-Token: <data/access_token>`.

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
{ "message": "Hola KAI", "conversation_id": null, "stream": true }
```

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
