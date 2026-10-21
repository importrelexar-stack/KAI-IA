//! KAI AI — app de escritorio.
//!
//! - Inicia KAI Core (sidecar empaquetado con PyInstaller) o reutiliza uno que ya esté corriendo.
//! - Muestra una pantalla de carga y abre la interfaz servida por KAI Core cuando responde.
//! - Ícono en la bandeja (Abrir / Salir); cerrar la ventana la oculta.
//! - Atajo global Ctrl+Alt+K para mostrar KAI. Una sola instancia.
//! - Al salir, pide a KAI Core que se detenga y, si no responde, lo termina.

use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, Url, WindowEvent};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const PORT: u16 = 8765;
const STARTUP_TIMEOUT: Duration = Duration::from_secs(90);
const SHORTCUT: &str = "ctrl+alt+k";
/// Código con el que KAI Core sale cuando se cierra para instalar una actualización (ver backend/app/core/updates.py).
const UPDATE_EXIT_CODE: i32 = 75;

struct Sidecar {
    child: Mutex<Option<CommandChild>>,
    shutdown_token: String,
}

static QUITTING: AtomicBool = AtomicBool::new(false);

fn kai_url() -> String {
    format!("http://127.0.0.1:{PORT}/")
}

/// GET HTTP mínimo (sin dependencias extra) contra KAI Core local.
fn http(method: &str, path: &str, headers: &[(&str, &str)]) -> Option<String> {
    let addr: SocketAddr = ([127, 0, 0, 1], PORT).into();
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_millis(400)).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(3))).ok()?;
    let mut req = format!("{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\nConnection: close\r\nContent-Length: 0\r\n");
    for (k, v) in headers {
        req.push_str(&format!("{k}: {v}\r\n"));
    }
    req.push_str("\r\n");
    stream.write_all(req.as_bytes()).ok()?;
    let mut buf = String::new();
    stream.read_to_string(&mut buf).ok()?;
    Some(buf)
}

fn kai_is_healthy() -> bool {
    http("GET", "/api/v1/health", &[])
        .map(|r| r.starts_with("HTTP/1.1 200") && r.contains("\"status\":\"ok\""))
        .unwrap_or(false)
}

fn port_in_use() -> bool {
    let addr: SocketAddr = ([127, 0, 0, 1], PORT).into();
    TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok()
}

fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

fn show_error(app: &AppHandle, html: &str) {
    if let Some(w) = app.get_webview_window("main") {
        let escaped = html.replace('\\', "\\\\").replace('\'', "\\'");
        let _ = w.eval(&format!("window.kaiShowError && window.kaiShowError('{escaped}')"));
        let _ = w.show();
    }
}

fn open_kai(app: &AppHandle) {
    if let (Some(w), Ok(url)) = (app.get_webview_window("main"), Url::parse(&kai_url())) {
        let _ = w.navigate(url);
    }
}

fn start_sidecar(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<Sidecar>();
    let cmd = app
        .shell()
        .sidecar("kai-core")
        .map_err(|e| e.to_string())?
        .env("KAI_PORT", PORT.to_string())
        .env("KAI_SHUTDOWN_TOKEN", state.shutdown_token.clone())
        // Si la app se cierra de golpe, KAI Core lo detecta y se detiene (no queda huérfano).
        .env("KAI_PARENT_PID", std::process::id().to_string())
        // KAI Core está empaquetado con PyInstaller: si esta app se abrió desde otro proceso de PyInstaller
        // (p. ej. el ayudante de actualización), heredó variables _PYI_* que apuntan a una carpeta temporal
        // ya borrada («Failed to load Python DLL»). Así KAI Core siempre arranca de cero.
        .env("PYINSTALLER_RESET_ENVIRONMENT", "1")
        .env("PYTHONUTF8", "1");
    let (mut rx, child) = cmd.spawn().map_err(|e| e.to_string())?;
    *state.child.lock().unwrap() = Some(child);

    // Hay que leer la salida del proceso: si nadie la consume, el búfer se llena y KAI Core se traba.
    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                    log::debug!("kai-core: {}", String::from_utf8_lossy(&line).trim_end());
                }
                CommandEvent::Terminated(payload) => {
                    if payload.code == Some(UPDATE_EXIT_CODE) {
                        // KAI Core se cerró para actualizarse: el ayudante instala la versión nueva y reabre KAI.
                        QUITTING.store(true, Ordering::SeqCst);
                        show_error(&handle, "Actualizando KAI AI…<br>La app se cierra y vuelve a abrirse sola en unos segundos.");
                    } else if !QUITTING.load(Ordering::SeqCst) {
                        show_error(
                            &handle,
                            &format!(
                                "KAI Core se detuvo inesperadamente (código {:?}).<br>Revisá <code>%LOCALAPPDATA%\\KAI\\logs\\kai.log</code> y volvé a abrir KAI.",
                                payload.code
                            ),
                        );
                    }
                    break;
                }
                _ => {}
            }
        }
    });
    Ok(())
}

fn stop_sidecar(app: &AppHandle) {
    QUITTING.store(true, Ordering::SeqCst);
    let state = app.state::<Sidecar>();
    let child = state.child.lock().unwrap().take();
    if let Some(child) = child {
        // 1) Pedido de cierre ordenado (KAI Core termina sus escrituras y su proceso hijo).
        let token = state.shutdown_token.clone();
        let _ = http("POST", "/api/v1/system/shutdown", &[("X-KAI-Shutdown", token.as_str())]);
        let deadline = Instant::now() + Duration::from_secs(5);
        while Instant::now() < deadline && port_in_use() {
            std::thread::sleep(Duration::from_millis(150));
        }
        // 2) Si sigue vivo, se termina.
        let _ = child.kill();
    }
}

fn wait_and_open(app: AppHandle, spawned: bool) {
    std::thread::spawn(move || {
        let start = Instant::now();
        while start.elapsed() < STARTUP_TIMEOUT {
            if kai_is_healthy() {
                open_kai(&app);
                return;
            }
            if QUITTING.load(Ordering::SeqCst) {
                return;
            }
            std::thread::sleep(Duration::from_millis(300));
        }
        let hint = if spawned {
            "KAI Core no respondió a tiempo. Revisá <code>%LOCALAPPDATA%\\KAI\\logs\\kai.log</code>."
        } else {
            "El puerto 8765 está ocupado por otro programa. Cerralo o cambiá <code>KAI_PORT</code>."
        };
        show_error(&app, hint);
    });
}

fn random_token() -> String {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    format!("{:x}{:x}", nanos, std::process::id() as u128 * 2654435761)
}

pub fn run() {
    let app = tauri::Builder::default()
        // Debe ir primero: si KAI ya está abierto, se muestra esa ventana en lugar de abrir otra.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_shell::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state == ShortcutState::Pressed {
                        show_main(app);
                    }
                })
                .build(),
        )
        .manage(Sidecar { child: Mutex::new(None), shutdown_token: random_token() })
        .setup(|app| {
            let handle = app.handle().clone();

            // Bandeja del sistema
            let open = MenuItem::with_id(app, "open", "Abrir KAI", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Salir", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            let mut tray = TrayIconBuilder::with_id("kai")
                .tooltip("KAI AI")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_main(app),
                    "quit" => {
                        stop_sidecar(app);
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                        show_main(tray.app_handle());
                    }
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.build(app)?;

            // Atajo global (si otro programa ya lo usa, KAI sigue funcionando sin él)
            if let Err(e) = app.global_shortcut().register(SHORTCUT) {
                log::warn!("No se pudo registrar {SHORTCUT}: {e}");
            }

            // KAI Core: se reutiliza si ya corre (instalación de desarrollo); si no, se inicia.
            if kai_is_healthy() {
                open_kai(&handle);
            } else if port_in_use() {
                wait_and_open(handle, false);
            } else {
                match start_sidecar(&handle) {
                    Ok(()) => wait_and_open(handle, true),
                    Err(e) => show_error(&handle, &format!("No se pudo iniciar KAI Core: {e}")),
                }
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // Cerrar la ventana la oculta en la bandeja; para salir: menú de la bandeja → Salir.
            if let WindowEvent::CloseRequested { api, .. } = event {
                if !QUITTING.load(Ordering::SeqCst) {
                    let _ = window.hide();
                    api.prevent_close();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("no se pudo crear la app de KAI");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_sidecar(handle);
        }
    });
}
