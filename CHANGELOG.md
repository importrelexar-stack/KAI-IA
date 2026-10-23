# Cambios

## [0.5.0] — 2026-10-20 — Fase 4b (app de escritorio)

### Agregado
- App de escritorio Tauri 2 con instalador NSIS para Windows: KAI Core empaquetado (PyInstaller, con
  interfaz y voz local) como sidecar, pantalla de carga, bandeja, Ctrl+Alt+K, instancia única.
- KAI Core empaquetado guarda los datos en `%LOCALAPPDATA%\KAI`.
- Cierre ordenado (`POST /api/v1/system/shutdown` con token por sesión) y watchdog del proceso padre:
  KAI Core no queda huérfano si la app se cierra de golpe.
- Workflow que construye el sidecar y el instalador en Windows, los ejecuta y verifica que KAI responde.

## [0.4.0] — 2026-10-20 — Fase 4 (automatización de Windows)

### Agregado
- Permisos de automatización: carpetas autorizadas (lectura / lectura y escritura), aplicaciones y scripts
  registrados, nivel por herramienta (permitir / preguntar / bloquear).
- Agentes KAI Files y KAI Automation: listar, buscar, leer (texto, PDF, Word), crear carpetas y archivos,
  mover, ordenar carpetas, enviar a la papelera, abrir archivos y apps, ejecutar scripts registrados.
- Acciones con confirmación: tarjeta Autorizar/Rechazar en el chat, ejecución al aprobar con permisos
  re-verificados, resultado en la conversación y en la tarea, auditoría.
- Pantalla Archivos con explorador de lo que KAI puede ver.

### Corregido
- Voz: remuestreo con filtro antialiasing; prueba de integración real determinística y en verde.
- CI: salida UTF-8 en Windows.

## [0.3.0] — 2026-10-20 — Fase 3 (memoria y agentes)

### Agregado
- Memoria persistente (preferencias, datos, notas de proyecto) con búsqueda local FTS5, propuestas que
  requieren aprobación, rechazo de secretos, edición y borrado individual/total.
- Proyectos: objetivo, estado, próximos pasos, registro de decisiones y avances, tareas y notas vinculadas.
- Orquestador con tool use: herramientas de memoria, tareas, planes con dependencias y proyectos; búsqueda
  web opcional (KAI Research); límites de pasos, tokens y tiempo; acciones visibles en el chat.
- Tareas con proyecto, dependencias y origen (usuario/KAI).
- Pantalla Memoria (memorias y proyectos), configuración de memoria y agentes, catálogo de agentes con
  herramientas.
- Migraciones automáticas de bases de datos anteriores.

### Corregido / mejorado
- Estilos de componentes en la capa de Tailwind: los anchos de campos y selectores se respetan.
- Voz: Whisper `small` por defecto (en Windows, `base` transcribía mal frases cortas en español).

## [0.2.0] — 2026-10-20 — Fase 2 (voz) + robustez de la Fase 1

### Agregado
- Voz: pantalla Voz con hablar/escuchar, Whisper local (faster-whisper), Piper `es_AR-daniela-high`,
  alternativa del navegador, respuestas breves para voz (`channel: "voice"`), interrupción (botón, Esc,
  barge-in), manos libres «Hey KAI» con consentimiento, dictado en el chat, selección de micrófono/salida,
  descarga de modelos a pedido, estados `listening`/`speaking` en el núcleo visual.
- Endpoints `/voice/status`, `/voice/transcribe`, `/voice/synthesize`, `/voice/models/{kind}/download`,
  `/voice/state`.
- CI: ejecución real de los scripts en Windows PowerShell 5.1 y prueba de voz de punta a punta con modelos
  reales; release `web-latest` con la interfaz compilada.

### Corregido / mejorado
- El control de origen bloqueaba la interfaz si se cambiaba `KAI_PORT`: ahora el puerto propio siempre
  está permitido.
- Proveedor Anthropic: si la API rechaza una función opcional (reintento en servidor, caché) se reintenta
  sin ella automáticamente.
- Scripts: avisos de pip/npm ya no cortan PowerShell 5.1; UTF-8 forzado; `py -3`; interfaz precompilada
  si no hay Node.js.

## [0.1.0] — 2026-10-20 — Fase 1 (MVP)

### Agregado
- KAI Core (FastAPI): API v1 versionada con OpenAPI, manejo de errores uniforme, logging con rotación y
  redacción de secretos.
- Proveedor Anthropic con el SDK oficial: streaming, esfuerzo configurable, caché de prompt, reintento
  en servidor ante rechazos de seguridad, mapeo de errores. Proveedor de demostración sin IA.
- Chat por SSE con cancelación, historial persistente en SQLite, renombrado y borrado (individual y total).
- Configuración: clave de API en variable de entorno o Administrador de credenciales de Windows,
  preferencias de modelo/esfuerzo/tokens/contexto, presupuesto diario, instrucciones personalizadas.
- Estados del asistente en tiempo real por WebSocket.
- Motor de tareas por estados con autorizaciones e historial.
- CoworkBridge manual: preparación de instrucciones, exportación `.md`, importación de resultados y archivos.
- Seguridad: control de origen/host, token para clientes remotos, límite de solicitudes, auditoría.
- Interfaz React + Tailwind: Dashboard con núcleo animado, Chat, Agentes, Automatizaciones, Cowork,
  Historial, Configuración, Estado del sistema; Voz, Memoria y Archivos como funciones futuras.
- Scripts de Windows (instalar, compilar interfaz, iniciar, detener, desarrollo, pruebas) y `.bat`.
- Pruebas: backend (pytest) y frontend (Vitest). CI en GitHub Actions (Windows y Linux).
- Documentación completa en `docs/`.
