# Hoja de ruta

## ✅ Fase 1 — MVP funcional (esta versión)

Backend FastAPI, Claude API real con streaming, interfaz React, chat con historial persistente,
configuración de clave y preferencias, estados del asistente en tiempo real, motor de tareas, CoworkBridge
manual, seguridad base, scripts de Windows, pruebas y documentación.

## ✅ Fase 2 — Voz (esta versión)

Captura PCM con AudioWorklet, detección de voz con ruido adaptativo, Whisper local, Piper `es_AR`,
alternativa del navegador, respuestas habladas breves, interrupción (botón, Esc y barge-in), manos libres
«Hey KAI» con consentimiento, dictado en el chat, selección de dispositivos, descarga de modelos a pedido.

Pendiente para más adelante: streaming de transcripción y de síntesis (menor latencia), detector de palabra
de activación dedicado (más liviano que Whisper continuo), voz con la ventana minimizada (requiere la app
de escritorio Tauri).

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
