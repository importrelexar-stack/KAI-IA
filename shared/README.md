# shared/

Contratos compartidos entre KAI Core y sus clientes (web, desktop, Android).

- `openapi.json`: especificación OpenAPI de la API v1. Se regenera con:

  ```powershell
  cd backend
  .venv\Scripts\python -m app.export_openapi
  ```
