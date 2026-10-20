# KAI Android — Kotlin + Jetpack Compose (beta)

El teléfono es un **cliente remoto de KAI Core**: funciona cuando la PC está encendida con KAI abierto y el
teléfono está en la **misma red privada** (tu Wi-Fi o, recomendado, **Tailscale**). KAI Core nunca se expone
a Internet.

> **Estado:** beta. El APK se compila, pasa lint y pruebas en CI (`.github/workflows/android.yml`), y el
> cliente se prueba contra un KAI Core real; todavía no se probó en un teléfono físico.

## Instalar

1. Descargá `kai-android.apk` de la release **android-latest** del repositorio (o el artefacto
   `kai-android-debug` de la última ejecución del workflow «App Android»).
2. En el teléfono, permití instalar apps de «orígenes desconocidos» para el navegador/gestor de archivos
   y abrí el APK. (Es un APK de depuración firmado con la clave de desarrollo, para uso personal.)

## Vincular

1. En la PC: KAI → **Dispositivos** → activá **Acceso remoto** y reiniciá KAI (Windows puede pedir permiso
   de firewall: aceptá sólo **Redes privadas**).
2. **Generar código**: aparece un QR y un código de 8 caracteres (dura 5 minutos, sirve una vez).
3. En el teléfono: **Escanear QR**, o escribí la dirección de la PC (ej. `192.168.1.10` o
   `mi-pc.tailnet.ts.net`) y el código.

### Tailscale (recomendado)

Instalá Tailscale en la PC y en el teléfono con la misma cuenta. Así la conexión va cifrada (WireGuard),
funciona fuera de casa y no hay que abrir puertos del router. KAI pone primero en el QR la dirección
`100.x.y.z` de Tailscale.

En la Wi-Fi de tu casa sin Tailscale el tráfico entre teléfono y PC **no va cifrado** (HTTP): usalo sólo en
redes de confianza.

## Qué hace

| Función | Detalle |
|---|---|
| Chat | Streaming, nueva conversación, interrumpir respuesta |
| Archivos | Adjuntar documentos (PDF, Word, texto) y fotos; las fotos se achican a 1568 px |
| Voz | Tocá el micrófono, hablá, se corta solo con el silencio. Transcribe y habla la PC (Whisper/Piper locales) |
| Tareas | Lista con estado; **Autorizar/Rechazar** muestra la acción exacta y pide confirmación |
| Historial | Conversaciones guardadas en la PC; las respuestas se muestran con formato (títulos, listas, negrita, código) |
| Rutinas | En la pestaña Tareas: ver las rutinas, «Ejecutar ahora» y «Ver resultado». Se crean y modifican desde la PC |
| Notificaciones | Avisa si hay acciones esperando autorización y cuando termina una rutina (cada 15 min y con la app abierta). La notificación sólo abre la app: no se aprueba a ciegas |
| Desvincular | Borra el token del teléfono y lo revoca en KAI |

## Seguridad

- El token (`kaid_…`) se guarda cifrado con una clave AES-GCM del **Android Keystore**; no se respalda
  ni se transfiere a otro teléfono (`allowBackup=false`).
- La app sólo se conecta a direcciones privadas (`ai.kai.core.PrivateNetwork`): un QR manipulado no puede
  enviar el token a Internet. KAI Core aplica la misma regla del lado del servidor.
- Un teléfono vinculado no puede cambiar la clave de API, los permisos de archivos, el acceso remoto ni
  administrar dispositivos.

## Estructura y compilación

```
apps/android
├── core/   Kotlin puro: cliente HTTP/SSE, vinculación, red privada, WAV (se prueba sin Android SDK)
└── app/    App Android (Compose): pantallas, voz, Keystore, WorkManager
```

```bash
cd apps/android
gradle :core:test                                    # cualquier JDK 17+
KAI_TEST_URL=http://127.0.0.1:8765 gradle :core:test # + contrato contra un KAI Core en modo demo
gradle :app:assembleDebug                            # requiere Android SDK (ANDROID_HOME)
```

Versiones: Gradle 8.14, AGP 8.7, Kotlin 2.1, compileSdk 35, minSdk 26 (Android 8.0).
