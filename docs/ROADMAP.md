# Hoja de ruta

## ✅ Fase 1 — MVP funcional (esta versión)

Backend FastAPI, Claude API real con streaming, interfaz React, chat con historial persistente,
configuración de clave y preferencias, estados del asistente en tiempo real, motor de tareas, CoworkBridge
manual, seguridad base, scripts de Windows, pruebas y documentación.

## Fase 2 — Voz

Implementar `voice/` (interfaces ya definidas): captura de micrófono en la interfaz (Web Audio /
Tauri), STT y TTS intercambiables (local: whisper.cpp / Piper; nube), palabra de activación «Hey KAI»
local con consentimiento explícito, detección de silencios, interrupción, selección de dispositivos,
endpoints `/voice/transcribe` y `/voice/synthesize`, estados `listening` / `speaking`.

## Fase 3 — Memoria y agentes

Memoria de preferencias, proyectos y operativa con controles de privacidad; búsqueda semántica
(embeddings locales + SQLite); orquestador con tool use de Claude; agentes Planner, Memory, Research y
Code con límites de tiempo, cancelación y presupuesto por tarea.

## Fase 4 — Automatización Windows

Herramientas con permisos individuales (carpetas permitidas, apertura de aplicaciones, búsqueda local,
lectura de PDF, organización de carpetas, scripts en lista blanca), ejecución desde el motor de tareas,
confirmaciones y auditoría detallada. Empaquetado Tauri 2 con KAI Core como sidecar e instalador.

## Fase 5 — Android

App Kotlin + Compose, emparejamiento seguro por QR, conexión por VPN privada, chat, voz, tareas,
historial y notificaciones.

## Fase 6 — Integraciones

Claude Cowork (si se publica una integración oficial), MCP, calendario, correo, gestión de proyectos,
navegación y automatizaciones complejas.
