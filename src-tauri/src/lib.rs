pub mod commands;
pub mod db;
pub mod mdns;
pub mod server;

use std::sync::atomic::{AtomicU16, Ordering};
use std::sync::{Arc, Mutex, RwLock};

use commands::AppState;
use tauri::Manager;

/// Configure and build the Tauri application.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_log::Builder::new()
                .target(tauri_plugin_log::Target::new(
                    tauri_plugin_log::TargetKind::Stdout,
                ))
                .target(tauri_plugin_log::Target::new(
                    tauri_plugin_log::TargetKind::Webview,
                ))
                .target(tauri_plugin_log::Target::new(
                    tauri_plugin_log::TargetKind::LogDir { file_name: None },
                ))
                .build(),
        )
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // Focus the main window when a second instance is launched
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let data_dir = app
                .path()
                .app_data_dir()
                .expect("failed to resolve app data dir");
            std::fs::create_dir_all(&data_dir)?;

            let db_path = data_dir.join("sleep-scoring.db");
            let conn = db::init_db(&db_path).expect("failed to initialize SQLite database");
            let db_arc = Arc::new(Mutex::new(conn));

            let instance_id = uuid::Uuid::new_v4().to_string();

            // Shared mutable config — empty until frontend calls set_group_config after login.
            // The axum server rejects all requests while group_hash is empty.
            let group_hash = Arc::new(RwLock::new(String::new()));
            let username = Arc::new(RwLock::new(String::new()));

            let server_port = Arc::new(AtomicU16::new(0));
            let mdns_manager: Arc<Mutex<Option<mdns::MdnsManager>>> = Arc::new(Mutex::new(None));

            let state = AppState {
                db: db_arc.clone(),
                data_dir: data_dir.clone(),
                group_hash: group_hash.clone(),
                instance_id: instance_id.clone(),
                username: username.clone(),
                server_port: server_port.clone(),
                mdns_manager: mdns_manager.clone(),
                active_workspace_id: Arc::new(RwLock::new(None)),
            };
            app.manage(state);

            // Start embedded axum server
            let server_db = db_arc.clone();
            let server_group = group_hash.clone();
            let server_user = username.clone();
            let server_id = instance_id.clone();
            let server_port_clone = server_port.clone();
            std::thread::spawn(move || {
                let rt = match tokio::runtime::Runtime::new() {
                    Ok(rt) => rt,
                    Err(e) => {
                        log::error!("Failed to create tokio runtime for server: {e}");
                        return;
                    }
                };
                rt.block_on(async {
                    let listener = match tokio::net::TcpListener::bind("0.0.0.0:0").await {
                        Ok(l) => l,
                        Err(e) => {
                            log::error!("Failed to bind server socket: {e}");
                            return;
                        }
                    };
                    let port = match listener.local_addr() {
                        Ok(addr) => addr.port(),
                        Err(e) => {
                            log::error!("Failed to get local address: {e}");
                            return;
                        }
                    };
                    server_port_clone.store(port, Ordering::Relaxed);
                    log::info!("Peer sync server listening on port {port}");

                    let server_state = server::ServerState {
                        db: server_db,
                        group_hash: server_group,
                        username: server_user,
                        instance_id: server_id.clone(),
                    };
                    let app = server::build_router(server_state);

                    // mDNS registration will happen once group_hash is set via set_group_config.
                    // For now just start the HTTP server.
                    if let Err(e) = axum::serve(listener, app).await {
                        log::error!("Axum server failed: {e}");
                    }
                });
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::discover_peers,
            commands::save_markers_to_sqlite,
            commands::set_group_config,
            commands::switch_workspace,
            commands::delete_workspace_db,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
