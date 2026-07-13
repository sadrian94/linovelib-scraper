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

fn main() {
    // Find a free port starting at 12400
    let port = portpicker::pick_unused_port().unwrap_or(8000);

    // Start Python FastAPI sidecar
    let python_exec = if cfg!(target_os = "windows") { "python" } else { "python3" };
    
    // Resolve relative path of the python script depending on current working directory
    let mut script_path = std::path::PathBuf::from("backend/server.py");
    if !script_path.exists() {
        let parent_path = std::path::PathBuf::from("../backend/server.py");
        if parent_path.exists() {
            script_path = parent_path;
        }
    }

    let child = Command::new(python_exec)
        .args([script_path.to_str().unwrap_or("backend/server.py"), &port.to_string()])
        .spawn();

    let server_child = match child {
        Ok(c) => Some(c),
        Err(e) => {
            eprintln!("Failed to spawn Python backend: {}", e);
            None
        }
    };

    tauri::Builder::default()
        .manage(Mutex::new(port))
        .manage(ServerProcess {
            child: Mutex::new(server_child),
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
