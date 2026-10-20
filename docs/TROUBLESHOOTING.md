# Solución de problemas

Los registros están en `data\logs\kai.log` (aplicación) y `data\logs\server.err.log` (servidor).

| Síntoma | Causa probable | Solución |
|---|---|---|
| «No se encontró Python 3.11+» | Python no instalado o fuera del PATH | Instalá Python marcando *Add to PATH*; cerrá y abrí la terminal. Probá `py --version`. |
| «la ejecución de scripts está deshabilitada» | Política de PowerShell | Usá los `.bat` o `powershell -ExecutionPolicy Bypass -File scripts\...` (sólo afecta a ese proceso). |
| `start.ps1`: «KAI Core no pudo iniciar» | Puerto 8765 ocupado | `netstat -ano | findstr 8765` para ver el proceso, o cambiá `KAI_PORT` en `.env`. |
| La página muestra «La interfaz no está compilada» | Falta `apps\web\dist` | Instalá Node.js LTS y ejecutá `scripts\build-web.ps1`. |
| «El chat real no está disponible» | Sin clave de API | Cargala en Configuración o en `.env` (`ANTHROPIC_API_KEY`). |
| «La clave de API fue rechazada (401)» | Clave inválida o revocada | Generá otra en console.anthropic.com. Recordá: Pro/Max no es una clave de API. |
| «No tiene permiso… (403)» / «modelo no disponible» | La cuenta no tiene acceso a ese modelo | Elegí otro modelo en Configuración. |
| «Anthropic limitó las solicitudes (429)» | Límite de tu cuenta | Esperá y reintentá; revisá los límites en la consola. |
| «Se alcanzó el presupuesto diario» | Presupuesto de KAI agotado | Ampliá `Presupuesto diario` en Configuración o esperá al día siguiente (UTC). |
| «No se pudo conectar con Anthropic» | Sin Internet, proxy o firewall | Verificá la conexión; con proxy corporativo definí `HTTPS_PROXY`. |
| «Sin almacén seguro del sistema» y la clave se pierde al reiniciar | `keyring` sin backend | En Windows no debería pasar; si pasa, usá `.env`. |
| «Sin conexión con KAI Core» en la barra lateral | Backend detenido o WebSocket bloqueado | Iniciá con `start.bat`; revisá antivirus/firewall local. |
| `403 forbidden_origin` | La interfaz se abrió desde otro origen | Usá `http://127.0.0.1:8765` o agregá el origen en `KAI_ALLOWED_ORIGINS`. |
| `stop.ps1` no lo detiene | Iniciado en modo desarrollo | Cerrá las ventanas de `start-dev.ps1` o `Ctrl+C`. |
| «No hay permiso para usar el micrófono» | Permiso denegado en el navegador o en Windows | Ícono del candado → Micrófono → Permitir. En Windows: Configuración → Privacidad → Micrófono. |
| «El micrófono está ocupado» | Otra app lo usa en modo exclusivo | Cerrá Teams/Zoom/grabadoras y reintentá. |
| «No te escuché» | Volumen bajo o micrófono equivocado | Elegí el micrófono en Voz → Dispositivos; mirá la barra de nivel mientras hablás. |
| Botón «Descargar modelo» da error | Sin Internet o huggingface.co bloqueado por firewall/proxy | Habilitá el acceso a huggingface.co o usá la opción «Navegador». |
| Motor local «No instalado» | Falló la instalación de faster-whisper/piper-tts | Ejecutá `backend\.venv\Scripts\python -m pip install -r backend\requirements-voice.txt` y mirá el error. |
| La voz suena en otro dispositivo | Salida predeterminada de Windows | Elegí la salida en Voz → Dispositivos (Chrome/Edge). |
| Manos libres no se activa | Falta consentimiento o modelo Whisper | Aceptá el aviso y descargá el modelo de reconocimiento. |
| Base de datos corrupta | Corte de energía durante escritura | Detené KAI, renombrá `data\kai.db` (se crea una nueva al iniciar). |
