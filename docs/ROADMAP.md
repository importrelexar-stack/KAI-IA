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

## ✅ Fase 3 — Memoria y agentes (esta versión)

Memoria de preferencias, datos y proyectos con aprobación y controles de privacidad; búsqueda local FTS5;
proyectos con decisiones, avances y próximos pasos; orquestador con tool use (Memory, Planner, Research
opcional); tareas con dependencias; límites de pasos, tokens y tiempo; migraciones automáticas.

Pendiente: búsqueda semántica con embeddings locales (la interfaz está preparada), agente Code (pasa a la
Fase 4 junto con el acceso a archivos).

## ✅ Fase 4 — Automatización Windows (esta versión)

Carpetas autorizadas con modo lectura/escritura, búsqueda y lectura (texto, PDF, Word), creación,
escritura con copia de seguridad, movimiento sin sobrescritura, orden de carpetas con vista previa,
papelera, apertura de archivos y apps registradas, scripts registrados con tiempo máximo, niveles por
herramienta, confirmación desde el chat y auditoría.

## ✅ Fase 4b — App de escritorio (esta versión)

Tauri 2 con KAI Core como sidecar (PyInstaller, incluye voz local), instalador NSIS por usuario, bandeja,
Ctrl+Alt+K, instancia única, cierre ordenado y watchdog. Build y prueba automática en Windows.

Pendiente: firma digital del instalador, actualización automática, voz/«Hey KAI» con la ventana oculta,
lectura de planillas Excel.

## 🧪 Fase 5 — Android (beta, esta versión)

KAI Core: acceso remoto sólo desde redes privadas (LAN / Tailscale) y con interruptor, vinculación por
código de un solo uso con QR, token por dispositivo (hash, revocable, el teléfono puede desvincularse),
permisos limitados para dispositivos (no administran KAI), adjuntos en el chat (documentos como datos,
imágenes visibles para Claude) desde la web y el teléfono.

App Kotlin + Compose: vinculación por QR o a mano, chat en streaming, adjuntar archivos y fotos
(se achican antes de enviar), voz (graba en el teléfono, transcribe y habla con los motores locales de la PC),
tareas con autorizar/rechazar mostrando la acción exacta, historial, notificaciones de autorizaciones
(cada 15 min y con la app abierta), token cifrado con Android Keystore. Compilación, lint y pruebas en CI,
más una prueba de contrato del cliente contra KAI Core real.

Por qué «beta»: el APK se compila y prueba en CI, pero todavía no se probó en un teléfono físico.

Agregado después: rutinas en el teléfono (ver, ejecutar, aviso al terminar) y respuestas con formato.

Pendiente: notificaciones en tiempo real (push sin Google requiere un servicio en primer plano), «Hey KAI»
en el teléfono, firma de release y publicación en tiendas.

## ✅ Fase 6 — Integraciones (esta versión)

- **MCP**: KAI es cliente MCP (SDK oficial). Servidores locales (stdio) o remotos (HTTP con token);
  herramientas con nivel permitir/preguntar/bloquear (solo lectura → permitir por defecto; el resto →
  autorización); claves en el almacén de credenciales; resultados marcados como datos externos. Calendario,
  correo y gestión de proyectos se conectan a través de servidores MCP de cada servicio.
- **Navegación**: búsqueda y lectura de páginas web de Anthropic (`web_search`/`web_fetch`), opcionales.
- **Automatizaciones complejas**: rutinas programadas (diarias, por días de la semana o por intervalo)
  que corren con las reglas del chat; combinadas con MCP y archivos permiten flujos de varios pasos.
- **Claude Cowork**: sigue sin API pública; se mantiene el puente manual. Se integrará sólo si Anthropic
  publica una integración oficial.

Agregado después: inicio de sesión **OAuth** para servidores MCP remotos (registro dinámico + PKCE con el
SDK oficial; tokens en el almacén de credenciales; «Cerrar sesión»).

Pendiente: recursos y prompts de MCP (hoy: sólo herramientas).
