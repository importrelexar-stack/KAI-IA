# Cambios

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
