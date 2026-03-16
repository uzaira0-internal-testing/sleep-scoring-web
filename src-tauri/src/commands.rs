use std::path::PathBuf;
use std::sync::atomic::{AtomicU16, Ordering};
use std::sync::{Arc, Mutex, RwLock};

use rusqlite::Connection;
use tauri::State;

use crate::db;
use crate::mdns::{self, PeerInfo};

/// A swappable database handle. Readers clone the inner Arc to get a stable
/// reference; the writer (switch_workspace) swaps the inner Arc atomically.
pub type DbHandle = Arc<RwLock<Arc<Mutex<Connection>>>>;

/// Application state managed by Tauri.
/// group_hash and username use RwLock because they're set after login.
pub struct AppState {
    pub db: DbHandle,
    pub data_dir: PathBuf,
    pub group_hash: Arc<RwLock<String>>,
    pub instance_id: String,
    pub username: Arc<RwLock<String>>,
    pub server_port: Arc<AtomicU16>,
    pub mdns_manager: Arc<Mutex<Option<crate::mdns::MdnsManager>>>,
    pub active_workspace_id: Arc<RwLock<Option<String>>>,
}

/// Set group hash and username after the user logs in.
/// This configures both the mDNS discovery filter and the axum auth.
#[tauri::command]
pub async fn set_group_config(
    state: State<'_, AppState>,
    group_hash: String,
    username: String,
) -> Result<(), String> {
    if group_hash.is_empty() {
        return Err("group_hash must not be empty".to_string());
    }
    *state.group_hash.write().map_err(|e| e.to_string())? = group_hash.clone();
    *state.username.write().map_err(|e| e.to_string())? = username.clone();

    let port = state.server_port.load(Ordering::Relaxed);
    if port > 0 {
        let mdns_mgr = state.mdns_manager.clone();
        let instance_id = state.instance_id.clone();
        tokio::task::spawn_blocking(move || {
            shutdown_mdns(&mdns_mgr);
            // Register new mDNS service
            match mdns::MdnsManager::register(&username, port, &group_hash, &instance_id) {
                Ok(mgr) => {
                    log::info!("mDNS registered: user={username}, port={port}");
                    let mut guard = mdns_mgr.lock().unwrap_or_else(|e| e.into_inner());
                    *guard = Some(mgr);
                }
                Err(e) => {
                    log::error!("mDNS registration failed: {e}");
                }
            }
        })
        .await
        .map_err(|e| e.to_string())?;
    }

    Ok(())
}

/// Discover peers on the LAN via mDNS, filtering out self.
#[tauri::command]
pub async fn discover_peers(state: State<'_, AppState>) -> Result<Vec<PeerInfo>, String> {
    let group_hash = state.group_hash.read().map_err(|e| e.to_string())?.clone();
    let own_id = state.instance_id.clone();

    if group_hash.is_empty() {
        return Ok(Vec::new()); // Not configured yet, no peers
    }

    let peers = tokio::task::spawn_blocking(move || mdns::MdnsManager::browse(&group_hash))
        .await
        .map_err(|e| e.to_string())?
        .map_err(|e| e.to_string())?;

    Ok(peers
        .into_iter()
        .filter(|p| p.instance_id != own_id)
        .collect())
}

/// Shut down the current mDNS registration if any.
fn shutdown_mdns(manager: &Mutex<Option<crate::mdns::MdnsManager>>) {
    let mut guard = manager.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(mut old) = guard.take() {
        if let Err(e) = old.shutdown() {
            log::warn!("Failed to shut down mDNS: {e}");
        }
    }
}

/// Validate a workspace ID: must be alphanumeric + hyphens, ≤128 chars (UUID format).
fn validate_workspace_id(workspace_id: &str) -> Result<(), String> {
    if workspace_id.is_empty() || workspace_id.len() > 128 {
        return Err("workspace_id must be 1-128 characters".to_string());
    }
    if !workspace_id
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '-')
    {
        return Err("workspace_id must contain only alphanumeric characters and hyphens".to_string());
    }
    Ok(())
}

/// Switch the active SQLite database to a workspace-scoped file.
/// Creates the workspace directory and database if needed.
/// Migrates from legacy database on first switch.
#[tauri::command]
pub async fn switch_workspace(
    state: State<'_, AppState>,
    workspace_id: String,
) -> Result<(), String> {
    validate_workspace_id(&workspace_id)?;

    let data_dir = state.data_dir.clone();

    // Migrate legacy DB if needed (runs before opening workspace DB)
    db::migrate_legacy_db(&data_dir, &workspace_id).map_err(|e| e.to_string())?;

    // Open workspace-scoped database
    let new_conn =
        db::open_workspace_db(&data_dir, &workspace_id).map_err(|e| e.to_string())?;

    // Atomically swap the database handle. Ongoing operations that already
    // cloned the old Arc<Mutex<Connection>> will finish with the old DB;
    // new operations will pick up the new one.
    {
        let mut db_guard = state.db.write().map_err(|e| e.to_string())?;
        *db_guard = Arc::new(Mutex::new(new_conn));
    }

    // Record active workspace
    {
        let mut ws_guard = state
            .active_workspace_id
            .write()
            .map_err(|e| e.to_string())?;
        *ws_guard = Some(workspace_id);
    }

    // Clear group_hash and username — force re-login for new workspace
    *state.group_hash.write().map_err(|e| e.to_string())? = String::new();
    *state.username.write().map_err(|e| e.to_string())? = String::new();

    // Shut down mDNS registration (peer discovery invalid for old workspace)
    shutdown_mdns(&state.mdns_manager);

    Ok(())
}

/// Delete a workspace's SQLite database directory.
/// Refuses to delete the currently active workspace.
#[tauri::command]
pub async fn delete_workspace_db(
    state: State<'_, AppState>,
    workspace_id: String,
) -> Result<(), String> {
    validate_workspace_id(&workspace_id)?;

    // Check it's not the currently active workspace
    {
        let active = state
            .active_workspace_id
            .read()
            .map_err(|e| e.to_string())?;
        if active.as_deref() == Some(&workspace_id) {
            return Err("Cannot delete the currently active workspace".to_string());
        }
    }

    let ws_dir = state
        .data_dir
        .join("workspaces")
        .join(&workspace_id);

    match std::fs::remove_dir_all(&ws_dir) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(format!("Failed to delete workspace directory: {e}")),
    }
}

/// Save markers to the local SQLite database (called from frontend after Dexie write).
#[tauri::command]
pub async fn save_markers_to_sqlite(
    state: State<'_, AppState>,
    file_hash: String,
    date: String,
    username: String,
    sleep_markers: String,
    nonwear_markers: String,
    is_no_sleep: bool,
    notes: String,
    content_hash: String,
) -> Result<(), String> {
    // Input validation
    if file_hash.len() > 128 || date.len() > 10 || username.len() > 256 {
        return Err("Invalid input: field too long".to_string());
    }
    const MAX_MARKERS_LEN: usize = 1_000_000; // 1MB limit per field
    if sleep_markers.len() > MAX_MARKERS_LEN || nonwear_markers.len() > MAX_MARKERS_LEN {
        return Err("Marker data exceeds maximum size".to_string());
    }

    // Snapshot the current DB handle under a short read-lock, then release
    // the RwLock before doing any blocking work. This ensures that if
    // switch_workspace swaps the handle concurrently, we finish with the
    // connection we started with (and new callers get the new one).
    let db_arc = {
        let guard = state.db.read().map_err(|e| e.to_string())?;
        Arc::clone(&guard)
    };
    tokio::task::spawn_blocking(move || {
        let conn = db_arc.lock().map_err(|e| e.to_string())?;
        db::upsert_markers(
            &conn,
            &file_hash,
            &date,
            &username,
            &sleep_markers,
            &nonwear_markers,
            is_no_sleep,
            &notes,
            &content_hash,
        )
        .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}
