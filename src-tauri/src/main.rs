#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{Manager, State};

struct ServerProcess {
    child: Mutex<Option<Child>>,
}

#[tauri::command]
fn get_server_port(port: State<'_, Mutex<u16>>) -> u16 {
    *port.lock().unwrap()
}

fn start_server(app: &tauri::AppHandle, port: u16) -> Result<Child, String> {
    if cfg!(debug_assertions) {
        let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .expect("src-tauri must have a project parent");
        let script_path = project_root.join("server").join("app.py");
        let python = if cfg!(target_os = "windows") { "python" } else { "python3" };
        Command::new(python)
            .arg(script_path)
            .arg(port.to_string())
            .current_dir(project_root)
            .spawn()
            .map_err(|error| format!("Failed to start development server: {error}"))
    } else {
        let sidecar_name = if cfg!(target_os = "windows") {
            "binaries/bilinovel-server.exe"
        } else {
            "binaries/bilinovel-server"
        };
        let sidecar = app
            .path()
            .resource_dir()
            .map_err(|error| format!("Could not resolve app resources: {error}"))?
            .join(sidecar_name);
        let data_dir = app
            .path()
            .app_data_dir()
            .map_err(|error| format!("Could not resolve app data directory: {error}"))?;
        std::fs::create_dir_all(&data_dir)
            .map_err(|error| format!("Could not create app data directory: {error}"))?;
        Command::new(sidecar)
            .arg(port.to_string())
            .current_dir(&data_dir)
            .env("BILINOVEL_DATA_DIR", &data_dir)
            .spawn()
            .map_err(|error| format!("Failed to start packaged server: {error}"))
    }
}

fn main() {
    // Find a free port starting at 12400
    let port = portpicker::pick_unused_port().unwrap_or(8000);

    tauri::Builder::default()
        .setup(move |app| {
            let server_child = match start_server(app.handle(), port) {
                Ok(child) => Some(child),
                Err(error) => {
                    eprintln!("Failed to spawn Python server: {error}");
                    None
                }
            };
            app.manage(Mutex::new(port));
            app.manage(ServerProcess {
                child: Mutex::new(server_child),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_server_port])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if window.label() == "main" {
                    // Kill python backend when closing main window
                    let state: State<'_, ServerProcess> = window.state();
                    let mut child_lock = state.child.lock().unwrap();
                    if let Some(mut child) = child_lock.take() {
                        let _ = child.kill();
                        println!("Killed Python backend server.");
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
