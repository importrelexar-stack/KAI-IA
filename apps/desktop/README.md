# KAI Desktop (Windows) — Tauri 2

**Estado: planificado (no implementado en la Fase 1).**

En la Fase 1, KAI se usa en el navegador: `scripts\start.ps1` inicia KAI Core, que sirve la interfaz en
`http://127.0.0.1:8765`. La interfaz ya es una SPA lista para empaquetar.

## Diseño previsto

- **Tauri 2** como contenedor nativo de `apps/web` (WebView2 en Windows).
- KAI Core (Python) como **proceso administrado** (sidecar): Tauri lo inicia al abrir la app, verifica
  `/api/v1/health` y lo detiene al cerrar. Orígenes `tauri://localhost` / `http://tauri.localhost` ya están
  autorizados en KAI Core.
- Empaquetado del backend con PyInstaller (o Python embebido) para no requerir Python instalado.
- Instalador MSI/NSIS generado por `tauri build`.
- Ícono en bandeja del sistema y atajo global para invocar a KAI (fase de voz).

## Requisitos para desarrollarlo

- Rust (rustup) y Microsoft C++ Build Tools.
- WebView2 Runtime (incluido en Windows 11).
- Node.js LTS.

Nada de esto se instala automáticamente: se documentará paso a paso cuando se implemente.
