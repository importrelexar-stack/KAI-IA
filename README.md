# KAI AI

Asistente personal de escritorio para **Windows** (Android en camino), con Claude como motor de IA.
Arquitectura modular: interfaz React, núcleo local **KAI Core** (FastAPI + SQLite) y proveedores de IA
intercambiables.

> **Estado: Fase 1 (MVP) completada.** Chat real con Claude, historial persistente, configuración segura
> de la clave, motor de tareas por estados, CoworkBridge manual, núcleo visual animado con estados reales,
> scripts de instalación para Windows y pruebas automatizadas. Voz, agentes especializados, automatización
> de Windows y Android son fases siguientes y la interfaz las muestra como **funciones futuras**.

## Inicio rápido (Windows)

Requisitos: **Python 3.11+**. Para compilar la interfaz: **Node.js LTS** (20.19+ / 22.12+).

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
| Instalar | `.\install.bat` o `scripts\install.ps1 [-Dev]` |
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
