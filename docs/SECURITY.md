# Seguridad

## Modelo de amenazas (Fase 1)

KAI Core corre en la PC del usuario y controla una clave de API con costo. Riesgos principales: que otro
programa, una página web o un equipo de la red use la API local; que la clave se filtre; que contenido
externo manipule al asistente; y gastos descontrolados.

## Controles implementados

| Riesgo | Control |
|---|---|
| Acceso desde la red | Escucha en `127.0.0.1` por defecto. Clientes no locales necesitan `X-KAI-Token` (token aleatorio de 256 bits en `data/access_token`). |
| Páginas web maliciosas (CSRF) | Se rechaza cualquier `Origin` fuera de la lista permitida (HTTP y WebSocket). El chat exige JSON, que fuerza preflight CORS. |
| DNS rebinding | Se rechaza un encabezado `Host` que no sea local. |
| Filtración de la clave | Clave en variable de entorno o Administrador de credenciales de Windows (`keyring`). Nunca en SQLite, nunca devuelta por la API (sólo enmascarada), redactada en logs y auditoría. Si no hay almacén seguro, queda sólo en memoria y se avisa. |
| Inyección de instrucciones | El prompt de sistema declara que el contenido de documentos, webs, correos, resultados importados y herramientas son datos, no órdenes. Lo importado de Cowork se marca como no confiable y no se ejecuta. |
| Acciones sensibles | Motor de tareas con autorización obligatoria (`requires_approval`); un reintento invalida la autorización previa. Borrado total del historial requiere `confirm=true`. Las acciones de archivos y programas se confirman según los permisos de la pantalla Archivos. |
| Costos | Presupuesto diario de tokens, límite de mensajes por minuto, registro de consumo, caché de prompt, esfuerzo bajo por defecto. |
| Archivos importados | Nombres saneados (sin rutas, sin nombres reservados de Windows), confinados a `data/cowork/<id>/`, sin sobrescritura, tamaño máximo configurable. Descarga sólo de archivos registrados. |
| Micrófono y privacidad | El micrófono sólo se abre al tocar «Hablar» o con «manos libres» activado tras un consentimiento explícito (revocable), con indicador visible, y se cierra al salir de la pantalla. Manos libres exige reconocimiento local: el audio no sale del equipo y sólo lo que empieza con «Hey KAI» llega a Claude. El audio nunca se guarda. El reconocimiento del navegador (opcional) se identifica como servicio en la nube. |
| Memoria | Sólo lo aprobado por el usuario se usa; lo que propone KAI queda pendiente. Se rechazan contraseñas, claves y números de tarjeta. Todo es consultable, editable y eliminable (individual o total). La memoria se inyecta como datos marcados, no como instrucciones. |
| Herramientas del orquestador | Entradas validadas con esquemas estrictos; herramientas sin efectos destructivos ni acceso al sistema; límite de pasos, tokens y tiempo por respuesta; auditoría de cada uso; tareas sensibles creadas por KAI requieren autorización. La búsqueda web está desactivada por defecto. |
| Archivos y programas (Fase 4) | Nada accesible por defecto; carpetas autorizadas por el usuario con modo lectura o escritura; bloqueo permanente de carpetas del sistema, AppData, datos de KAI y archivos de credenciales; resolución de enlaces simbólicos; sin borrado definitivo (papelera) ni sobrescritura sin copia; sin comandos libres (sólo apps y scripts registrados, sin shell, con tiempo máximo); acciones que modifican algo con confirmación por defecto y permisos re-verificados al ejecutar; el contenido leído se marca como dato, no instrucción; auditoría de permisos y ejecuciones. |
| Acceso remoto y teléfonos (Fase 5) | Apagado por defecto; con el interruptor activo KAI escucha en la red pero sólo acepta clientes de redes privadas (10/8, 172.16/12, 192.168/16, Tailscale 100.64/10, IPv6 ULA) — nunca IPs públicas ni redes de documentación — y con encabezado Host privado/`.ts.net`/`.local`. Vinculación por código de 8 caracteres, 5 minutos, un solo uso, bloqueo tras 10 intentos fallidos y límite de 5 intentos por minuto por IP. Token por dispositivo guardado como hash SHA-256, revocable desde la PC o desde el propio teléfono. Lista blanca de lo que puede hacer un dispositivo (chat, adjuntos, voz, tareas, historial, memoria); no puede tocar la clave de API, permisos, acceso remoto ni dispositivos. Auditoría con el nombre del dispositivo. En el teléfono el token se cifra con Android Keystore y la app se niega a conectarse fuera de la red privada. |
| Integraciones MCP (Fase 6) | Sólo el usuario agrega servidores, desde la PC (ni Claude ni los teléfonos: 403). Un servidor local es un programa con los permisos del usuario: la interfaz lo advierte. Nivel por herramienta: solo lectura declarada → permitir; el resto → autorización (tarea pendiente, se ejecuta al aprobar); bloquear la quita de la lista que ve Claude. Variables secretas y tokens en el almacén de credenciales, nunca en la base ni en respuestas de la API. Servidores remotos sólo por HTTPS (HTTP únicamente en localhost). OAuth: KAI no ve tu contraseña (iniciás sesión en el sitio del servicio); registro dinámico con PKCE; el callback sólo se acepta desde la PC y con un `state` pendiente; tokens y datos del cliente en el almacén de credenciales; «Cerrar sesión» los borra. Resultados recortados (20 000 caracteres) y marcados como datos externos; la persona prohíbe seguir instrucciones que vengan en ellos. Auditoría de alta, cambios, niveles y uso. |
| Web (Fase 6) | Búsqueda y lectura apagadas por defecto; máx. 5 usos por respuesta; la lectura sólo abre URLs que ya están en la conversación; el contenido es dato, no instrucción. |
| Rutinas (Fase 6) | Sólo se crean desde la PC; corren con las mismas reglas que el chat (permisos, autorizaciones pendientes que nunca se aprueban solas, presupuesto diario); mínimo 15 minutos entre ejecuciones; 10 minutos máximo por ejecución; auditadas como `routine:<nombre>`. |
| Adjuntos | Tamaño máximo configurable (imágenes ≤ 5 MB); los documentos se convierten a texto y se entregan a Claude marcados como datos, no instrucciones; las imágenes sólo se envían en el turno actual. |
| Validación | Pydantic en todas las entradas con límites de tamaño; errores uniformes sin trazas internas. |
| Trazabilidad | `audit_log` para cambios de configuración, clave, tareas, Cowork, borrados y errores de chat. |

## Recomendaciones

- No abras el puerto de KAI en el router ni lo redirijas a Internet. Para usar KAI desde el teléfono fuera
  de casa usá Tailscale (VPN privada cifrada). En el firewall de Windows permití KAI sólo en «Redes privadas».
- En una Wi-Fi sin Tailscale el tráfico teléfono↔PC va sin cifrar: usá el acceso remoto sólo en redes de
  confianza y revocá los teléfonos que ya no uses (KAI → Dispositivos).
- No compartas `data/access_token` ni el archivo `.env`.
- Configurá un límite de gasto también en la consola de Anthropic.

## Reportar un problema

Abrí un issue privado o escribí al mantenedor del repositorio. No incluyas claves en los reportes.
