# KAI Android — Kotlin + Jetpack Compose

**Estado: planificado para la Fase 5 (no implementado).**

## Decisiones tomadas desde ahora

- **Kotlin + Jetpack Compose** (nativo): mejor acceso a permisos de micrófono, notificaciones y
  servicios en segundo plano que una alternativa multiplataforma, y la interfaz principal ya es web.
- El teléfono es un **cliente remoto de KAI Core**: KAI funciona cuando la PC con Windows está encendida
  y KAI Core está activo. No se asume ninguna API para controlar Claude Cowork desde el teléfono.
- **Nunca se expone KAI Core a Internet.** La conexión será por una red privada (VPN tipo WireGuard /
  Tailscale) y autenticada con el token de acceso de KAI (`data/access_token`, encabezado `X-KAI-Token`),
  que KAI Core ya exige a todo cliente que no sea local.
- El contrato de la API está en `shared/openapi.json` para generar el cliente.

## Funciones objetivo

Chat, voz, tareas e historial, notificaciones, envío de archivos, acciones remotas autorizadas y
emparejamiento seguro (QR con token de un solo uso + rotación).
