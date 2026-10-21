# KAI Desktop (Windows) — Tauri 2

App de escritorio de KAI: un instalador para Windows que incluye **KAI Core empaquetado** (no hace falta
instalar Python ni Node.js).

## Qué hace

- Inicia KAI Core (carpeta `kai-core\` instalada junto a la app, empaquetada con PyInstaller con la interfaz y los motores de voz
  locales) y muestra la interfaz cuando responde. Si ya hay un KAI corriendo en el puerto 8765 (por
  ejemplo, la instalación de desarrollo), lo reutiliza.
- Datos en `%LOCALAPPDATA%\KAI` (base, registros, modelos de voz). La clave de API se guarda en el
  Administrador de credenciales de Windows, igual que en la versión web.
- Ícono en la bandeja del sistema: **Abrir KAI** / **Salir**. Cerrar la ventana la oculta.
- Atajo global **Ctrl+Alt+K** para mostrar KAI. Una sola instancia.
- Al salir pide a KAI Core un cierre ordenado (endpoint protegido con un token por sesión). Si la app se
  cierra de golpe, KAI Core lo detecta (`KAI_PARENT_PID`) y se detiene solo.

## Descargar

El workflow **App de escritorio (Windows)** genera el instalador en cada cambio:

- Artefacto `KAI-AI-instalador-windows` en cada ejecución del workflow.
- Descarga directa [Instalar-KAI-AI.exe](https://github.com/importrelexar-stack/KAI-IA/releases/download/kai-ai-windows/Instalar-KAI-AI.exe) (release `kai-ai-windows`, se actualiza con cada cambio).

El instalador es por usuario (no pide permisos de administrador). Windows SmartScreen puede advertir
porque el instalador no está firmado digitalmente: «Más información» → «Ejecutar de todos modos».

## Compilar localmente (Windows)

Requisitos: Python 3.11+, Node.js LTS, Rust (`rustup`), Microsoft C++ Build Tools y WebView2 (incluido en
Windows 11).

```powershell
cd apps\web; npm ci; npm run build; cd ..\..
cd backend
python -m pip install -r requirements.txt -r requirements-voice.txt "pyinstaller>=6.10,<7"
pyinstaller kai-core.spec --noconfirm          # genera la carpeta dist\kai-core\
Copy-Item dist\kai-core\* ..\apps\desktop\src-tauri\kai-core\ -Recurse -Force
cd ..\apps\desktop
npm ci
npx tauri build      # instalador en src-tauri\target\release\bundle\nsis\
```

## Limitaciones conocidas

- El instalador no está firmado (SmartScreen avisa).
- La voz con la ventana oculta y la palabra «Hey KAI» en segundo plano todavía requieren la pantalla Voz
  abierta.
- Sin actualización automática: se reinstala con la versión nueva (los datos se conservan).
