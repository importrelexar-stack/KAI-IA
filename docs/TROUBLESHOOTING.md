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
| KAI dice que guardó algo pero no aparece en la memoria | Las propuestas esperan aprobación | Pantalla Memoria → «Propuestas de KAI» → Aprobar. |
| «Por seguridad, KAI no guarda contraseñas…» | El texto parece una clave o tarjeta | Es intencional: no guardes secretos en la memoria. |
| «Me detuve porque alcancé el límite de pasos» | Tarea compleja con muchas herramientas | Pedile que siga, o subí «Máximo de pasos» en Configuración. |
| Estado del sistema muestra «fts5: false» | El SQLite de tu Python no trae FTS5 | La memoria funciona con búsqueda simple; actualizá Python desde python.org. |
| «No hay carpetas autorizadas» | Todavía no autorizaste ninguna | Pantalla Archivos → Carpetas autorizadas. |
| «La ruta está fuera de las carpetas autorizadas» | KAI intentó acceder a otra ubicación | Autorizá esa carpeta si corresponde. |
| «Esa carpeta contiene o es una ubicación protegida» | Intentaste autorizar una carpeta del sistema, AppData o la de datos de KAI | Elegí una subcarpeta tuya (Documentos, Escritorio, un proyecto). |
| «autorizada sólo para lectura» | La carpeta tiene modo lectura | Cambiá el modo a «Lectura y escritura» si querés que KAI modifique archivos ahí. |
| La acción autorizada falló | Cambió algo desde que KAI la pidió (permisos, archivo movido) | Mirá el error en la tarjeta del chat o en Automatizaciones y pedile que lo intente de nuevo. |
| SmartScreen bloquea el instalador | El instalador no está firmado | «Más información» → «Ejecutar de todos modos». |
| La app muestra «El puerto 8765 está ocupado» | Otro programa usa el puerto | Cerralo; si es otra copia de KAI (desarrollo), la app la reutiliza cuando responde. |
| La app muestra «KAI Core no respondió a tiempo» | Antivirus analizando el ejecutable la primera vez, o error al iniciar | Esperá y volvé a abrir; revisá `%LOCALAPPDATA%\KAI\logs\kai.log`. |
| No aparece la ventana al abrir KAI | Está oculta en la bandeja | Clic en el ícono de KAI en la bandeja o Ctrl+Alt+K. |
| Base de datos corrupta | Corte de energía durante escritura | Detené KAI, renombrá `data\kai.db` (se crea una nueva al iniciar). |
