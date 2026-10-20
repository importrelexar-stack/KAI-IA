# KAI AI

Asistente personal para **Windows** y **Android** (beta), con Claude como motor de IA.
Arquitectura modular: interfaz React, núcleo local **KAI Core** (FastAPI + SQLite) y proveedores de IA
intercambiables.

> **Estado: Fases 1 a 6 implementadas** (Android en beta). Chat real con Claude, historial persistente,
> configuración segura de la clave, motor de tareas, CoworkBridge manual, núcleo visual con estados reales,
> **conversación por voz en español de Argentina** (reconocimiento y síntesis locales, «Hey KAI» con
> consentimiento, interrupción, dictado), **memoria persistente y proyectos**, **orquestador con agentes**,
> **archivos y aplicaciones con permisos y confirmación**, **app de escritorio con instalador**,
> **app Android** (vinculación por QR, chat, voz, archivos, autorizaciones), **integraciones MCP** y
> **lectura web**, **rutinas programadas**, y pruebas automatizadas.

## Instalar la app de escritorio (recomendado)

**[⬇ Descargar Instalar-KAI-AI.exe](https://github.com/importrelexar-stack/KAI-IA/releases/download/kai-ai-windows/Instalar-KAI-AI.exe)** → doble clic → «Siguiente». No pide permisos de
administrador ni necesita Python o Node.js, y crea el acceso «KAI AI» en el escritorio. Si SmartScreen avisa
que no está firmado: «Más información» → «Ejecutar de todos modos». Ver [apps/desktop/README.md](apps/desktop/README.md).

Android (beta): **[⬇ KAI-AI.apk](https://github.com/importrelexar-stack/KAI-IA/releases/download/kai-ai-android/KAI-AI.apk)** (abrilo desde el teléfono).

## Inicio rápido desde el código (Windows)

Requisitos: **Python 3.11+**. Node.js LTS es opcional: sin Node, el instalador descarga la interfaz ya
compilada desde GitHub.

```powershell
git clone <url-del-repo> KAI-IA
cd KAI-IA
.\install.bat          # crea backend\.venv, instala dependencias, crea .env y compila la interfaz
.\start.bat            # inicia KAI y abre http://127.0.0.1:8765
```

Después, en **Configuración**, cargá tu clave de API de Anthropic (o ponela en `.env` como
`ANTHROPIC_API_KEY`). Detalle completo en [docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md).

| Acción | Comando |
|---|---|
| Instalar (crea el acceso «KAI AI» en el escritorio) | `.\install.bat` o `scripts\install.ps1 [-Dev] [-NoShortcut]` |
| Acceso directo en el escritorio | `.\crear-acceso-directo.bat` (`-StartMenu` también en el menú Inicio, `-Remove` lo quita) |
| Iniciar | `.\start.bat` o `scripts\start.ps1` |
| Modo demostración (sin IA) | `scripts\start.ps1 -Demo` |
| Detener | `.\stop.bat` o `scripts\stop.ps1` |
| Modo desarrollo (recarga automática) | `scripts\start-dev.ps1` |
| Pruebas | `scripts\test.ps1` |
| Recompilar interfaz | `scripts\build-web.ps1` |
| Documentación interactiva de la API | http://127.0.0.1:8765/docs |

> **Importante:** una suscripción Claude **Pro o Max no incluye acceso a la API**. KAI necesita una clave de
> [console.anthropic.com](https://console.anthropic.com) con facturación propia. Sin clave, KAI inicia
> igual e indica que el chat real no está disponible.

## Integraciones y rutinas (Fase 6)

- Pantalla **Integraciones**: conectá servidores **MCP** (el estándar abierto para conectar asistentes con
  aplicaciones: calendario, correo, notas, gestores de proyectos…), locales (un programa en tu PC) o remotos
  (HTTP con token o **iniciando sesión con OAuth**). Sus herramientas quedan disponibles para Claude: las de **solo lectura** se permiten por
  defecto y las que **modifican algo piden autorización**; podés ajustarlo por herramienta. Las claves van
  al Administrador de credenciales de Windows.
- **Web**: búsqueda y lectura de páginas (apagadas por defecto; tienen costo por uso).
- Pantalla **Rutinas**: pedidos que KAI hace solo («de lunes a viernes 8:30, resumime pendientes»), en
  su propia conversación, con las mismas reglas de autorización y presupuesto que el chat.
- **Claude Cowork**: no tiene una API pública, así que sigue siendo un puente manual (CoworkBridge).

## App Android (Fase 5, beta)

Vinculá el teléfono desde **Dispositivos** (QR de un solo uso, sólo por tu red privada o Tailscale). Ver
[apps/android/README.md](apps/android/README.md).

## Automatización de Windows (Fase 4)

- Pantalla **Archivos**: autorizás carpetas (sólo lectura o lectura y escritura), aplicaciones y scripts.
  Un explorador muestra exactamente lo que KAI puede ver.
- KAI puede **listar, buscar (por nombre o contenido) y leer** archivos de texto, PDF y Word; **crear
  carpetas y archivos de texto, mover, ordenar carpetas** por tipo o fecha, **enviar a la papelera**,
  **abrir** archivos y aplicaciones registradas y **ejecutar scripts registrados**.
- Cada acción tiene un nivel configurable (permitir / preguntar / bloquear). Las que modifican algo
  piden confirmación por defecto: aparecen en el chat con **Autorizar / Rechazar** y una vista previa, y
  los permisos se vuelven a verificar al ejecutar. Papelera y scripts siempre preguntan.
- Nunca: borrado definitivo, sobrescritura sin copia de seguridad, comandos libres, carpetas del sistema,
  datos de KAI ni archivos de credenciales. Todo queda en la auditoría.

## Memoria y agentes (Fase 3)

- **Memoria**: preferencias (siempre presentes), datos y notas de proyectos (se recuperan por relevancia
  con búsqueda local SQLite FTS5). Todo se puede ver, editar y borrar en la pantalla **Memoria**.
- **Lo que KAI propone recordar queda pendiente** hasta que lo apruebes (o activás la aprobación
  automática). KAI rechaza guardar contraseñas, claves o números de tarjeta.
- **Proyectos**: objetivo, estado, próximos pasos, decisiones y avances, tareas y notas vinculadas.
- **Orquestador**: Claude decide qué herramientas usar — buscar/proponer memoria, listar/crear tareas,
  **dividir objetivos en planes con dependencias**, crear y actualizar proyectos. Lo que hizo se ve en el
  chat como acciones. Límite configurable de pasos por respuesta, presupuesto de tokens y tiempo máximo.
- **KAI Research** (opcional, con costo): búsqueda web de Anthropic, desactivada por defecto.
- Las bases de datos de versiones anteriores se migran solas al iniciar.

## Voz (Fase 2)

- Pantalla **Voz**: tocás el núcleo o «Hablar», KAI detecta cuándo terminaste de hablar, transcribe,
  responde con Claude (respuestas breves pensadas para escuchar) y las lee en voz alta.
- **Motores locales** (sin conexión ni costo por uso): reconocimiento con **Whisper** (faster-whisper) y
  voz con **Piper** `es_AR-daniela-high` (Argentina). Los modelos (Whisper small ~465 MB + voz ~110 MB) se descargan desde la
  pantalla Voz sólo cuando lo decidís. Alternativa: voces y reconocimiento del navegador.
- **Interrupción**: botón, tecla `Esc`, o simplemente hablar encima en modo manos libres.
- **Manos libres «Hey KAI»**: requiere consentimiento explícito, reconocimiento local y la pantalla
  abierta; muestra un indicador rojo; lo que no empieza con «Hey KAI» se descarta.
- **Dictado** en el chat con el botón de micrófono.
- Selección de micrófono y de salida de audio. El audio nunca se guarda.

## Qué hay en la Fase 1

- **Chat con Claude** por streaming (SSE), con cancelación, Markdown, persistencia en SQLite y
  recuperación después de reiniciar. Modelo por defecto: `claude-opus-5-5` (configurable: Sonnet 5.5,
  Haiku 5.5, Fable 5.1), esfuerzo de razonamiento configurable, caché de prompt y reintento automático
  en servidor si un clasificador de seguridad rechaza la solicitud.
- **Control de costos**: presupuesto diario de tokens, registro de consumo, límite de mensajes por minuto.
- **Clave de API segura**: variable de entorno o Administrador de credenciales de Windows (`keyring`).
  Nunca se guarda en la base ni se devuelve por la API.
- **Núcleo visual animado** que refleja el estado real (inactivo, procesando, error…) vía WebSocket.
- **Motor de tareas** con estados (pendiente → esperando autorización → en ejecución → completada /
  fallida / cancelada), autorizaciones e historial.
- **CoworkBridge**: genera instrucciones estructuradas para Claude Cowork, exporta `.md`, e importa
  resultados y archivos. Es **manual** porque no existe una API pública para controlar sesiones de Cowork.
- **Seguridad**: escucha sólo en `127.0.0.1`, bloqueo de orígenes/hosts ajenos, token para clientes
  remotos, auditoría, validación de entradas, redacción de secretos en logs.
- Pantallas: Dashboard, Chat, Agentes, Automatizaciones, Cowork, Historial, Configuración, Estado del
  sistema; Voz, Memoria y Archivos marcadas como futuras.

## Estructura

```
KAI-IA/
├── apps/
│   ├── web/        Interfaz React + TypeScript + Vite + Tailwind
│   ├── desktop/    Tauri 2 (planificado)
│   └── android/    Kotlin + Compose (planificado)
├── backend/        KAI Core (FastAPI)
│   ├── app/
│   │   ├── api/v1/      Endpoints versionados
│   │   ├── core/        Configuración, estado, persona, errores, logging
│   │   ├── providers/   Proveedores de IA (Anthropic, demo) intercambiables
│   │   ├── services/    Chat, preferencias, consumo
│   │   ├── automation/  Motor de tareas por estados
│   │   ├── cowork/      CoworkBridge
│   │   ├── security/    Secretos, control de acceso, auditoría
│   │   ├── agents/      Catálogo de agentes (orquestador activo)
│   │   ├── memory/      Memoria (Fase 3)
│   │   ├── voice/       Interfaces STT/TTS/wake word (Fase 2)
│   │   ├── database/ models/ schemas/
│   └── tests/
├── shared/         Contrato OpenAPI
├── scripts/        Instalación y operación en Windows (PowerShell)
├── docs/           Documentación
└── assets/
```

## Documentación

- [Instalación en Windows](docs/INSTALL_WINDOWS.md)
- [Arquitectura](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Seguridad](docs/SECURITY.md)
- [Hoja de ruta](docs/ROADMAP.md)
- [Solución de problemas](docs/TROUBLESHOOTING.md)
- [Cambios](CHANGELOG.md)
