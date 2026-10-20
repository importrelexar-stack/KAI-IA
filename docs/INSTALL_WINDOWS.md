# Instalación en Windows 10/11

## 1. Requisitos

| Componente | Necesario para | Cómo instalarlo |
|---|---|---|
| **Python 3.11 o superior** | KAI Core (obligatorio) | [python.org](https://www.python.org/downloads/windows/) — marcá *Add python.exe to PATH* — o `winget install Python.Python.3.13` |
| **Node.js LTS** (20.19+ / 22.12+) | Compilar la interfaz | [nodejs.org](https://nodejs.org) o `winget install OpenJS.NodeJS.LTS` |
| Git | Clonar el repositorio | [git-scm.com](https://git-scm.com) o `winget install Git.Git` |
| Clave de API de Anthropic | Chat real con Claude | [console.anthropic.com](https://console.anthropic.com) |

No hace falta Rust ni Android Studio en la Fase 1. Los scripts **no instalan programas** ni cambian
configuraciones globales: si falta algo, te dicen qué instalar.

> Claude Pro/Max **no** equivale a acceso a la API. La API se factura aparte, por uso.

## 2. Instalación

```powershell
cd C:\ruta\a\KAI-IA
.\install.bat
```

`install.bat` ejecuta `scripts\install.ps1` omitiendo la política de ejecución **sólo para ese proceso**.
Si preferís PowerShell directo y tu política lo bloquea:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install.ps1
```

El instalador:

1. Busca Python 3.11+ (`py` o `python`).
2. Crea `backend\.venv` e instala `backend\requirements.txt` (con `-Dev`, también las de pruebas).
3. Copia `.env.example` a `.env` si no existe (nunca lo sobrescribe).
4. Si hay Node.js, compila la interfaz en `apps\web\dist`. Si no, te avisa: KAI Core funciona igual y
   expone la API en `http://127.0.0.1:8765/docs`.

## 3. Configurar Claude

Opción A — desde la interfaz (recomendada): **Configuración → Clave de API de Anthropic → Guardar**. La
clave se guarda en el **Administrador de credenciales de Windows** (servicio `kai-ai`). Con **Probar
clave** se valida sin consumir tokens.

Opción B — archivo `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Si existe en `.env`, tiene prioridad y la interfaz no permite cambiarla.

En **Configuración** también elegís modelo, esfuerzo de razonamiento, máximo de tokens, contexto enviado y
**presupuesto diario de tokens** (por defecto 500.000; 0 = sin límite).

## 4. Iniciar y detener

```powershell
.\start.bat              # producción: http://127.0.0.1:8765 (abre el navegador)
scripts\start.ps1 -Demo  # modo demostración: sin IA, respuestas marcadas como DEMOSTRACIÓN
.\stop.bat               # detiene KAI Core
```

`start.ps1` corre KAI Core en segundo plano, guarda el PID en `data\kai.pid` y escribe registros en
`data\logs\`. `stop.ps1` detiene sólo ese proceso (y su proceso hijo).

## 5. Modo desarrollo

```powershell
scripts\install.ps1 -Dev
scripts\start-dev.ps1        # backend con recarga (8765) + Vite (5173) en ventanas separadas
```

Abrí `http://127.0.0.1:5173`. Vite reenvía `/api` (HTTP y WebSocket) al backend. Para detener, cerrá
ambas ventanas o `Ctrl+C`.

## 6. Pruebas

```powershell
scripts\test.ps1
```

Corre `pytest` en el backend y, si hay Node.js, verificación de tipos + Vitest en el frontend. Las pruebas
**no usan claves reales**: el proveedor de IA está simulado.

## 7. Datos

Todo queda en `data\` (excluido de git): `kai.db` (SQLite), `logs\`, `cowork\` (archivos importados) y
`access_token`. Para mover la carpeta, definí `KAI_DATA_DIR` en `.env`.

## 8. Desinstalar

Detené KAI, borrá la carpeta del repositorio y, si guardaste la clave desde la interfaz, eliminá la
credencial `kai-ai` en *Panel de control → Administrador de credenciales → Credenciales de Windows*
(o usá **Borrar** en Configuración antes de desinstalar).
