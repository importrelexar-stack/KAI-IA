// Sin consola en Windows en la versión de producción.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    kai_desktop_lib::run()
}
