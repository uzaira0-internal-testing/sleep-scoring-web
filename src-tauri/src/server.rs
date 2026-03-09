use std::net::SocketAddr;
use std::sync::{Arc, Mutex, RwLock};

use axum::{
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
    routing::get,
    Json, Router,
};
use rusqlite::Connection;
use serde::Serialize;

use crate::db;

/// Shared state for the axum server.
/// group_hash uses RwLock so it can be updated after user login.
#[derive(Clone)]
pub struct ServerState {
    pub db: Arc<Mutex<Connection>>,
    pub group_hash: Arc<RwLock<String>>,
    pub username: Arc<RwLock<String>>,
    pub instance_id: String,
}

#[derive(Serialize)]
struct HealthResponse {
    status: String,
    username: String,
    instance_id: String,
}

#[derive(Serialize)]
struct MarkersResponse {
    markers: Vec<MarkerJson>,
}

#[derive(Serialize)]
struct MarkerJson {
    username: String,
    sleep_markers: String,
    nonwear_markers: String,
    is_no_sleep: bool,
    notes: String,
    content_hash: String,
}

/// Log an error and return 500. Used for poisoned locks and failed joins.
fn internal_err(msg: &str, err: impl std::fmt::Display) -> StatusCode {
    log::error!("{msg}: {err}");
    StatusCode::INTERNAL_SERVER_ERROR
}

/// Validate the X-Group-Hash header matches the server's group hash.
/// Rejects all requests if the server has no group hash configured yet.
fn check_auth(headers: &HeaderMap, expected: &str) -> Result<(), StatusCode> {
    // Reject all requests before group_hash is configured (prevents empty == empty bypass)
    if expected.is_empty() {
        return Err(StatusCode::SERVICE_UNAVAILABLE);
    }
    let provided = headers
        .get("X-Group-Hash")
        .and_then(|v| v.to_str().ok())
        .ok_or(StatusCode::FORBIDDEN)?;
    if provided != expected {
        return Err(StatusCode::FORBIDDEN);
    }
    Ok(())
}

/// Read group_hash and validate the request's X-Group-Hash header.
fn verify_auth(state: &ServerState, headers: &HeaderMap) -> Result<(), StatusCode> {
    let group_hash = state.group_hash.read().map_err(|e| internal_err("RwLock poisoned", e))?;
    check_auth(headers, &group_hash)
}

/// Run a blocking DB query, handling lock poisoning and join failures.
async fn db_query<T: Send + 'static>(
    state: &ServerState,
    f: impl FnOnce(&rusqlite::Connection) -> rusqlite::Result<T> + Send + 'static,
) -> Result<T, StatusCode> {
    let db = state.db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().map_err(|e| internal_err("DB mutex poisoned", e))?;
        f(&conn).map_err(|e| internal_err("SQLite query failed", e))
    })
    .await
    .map_err(|e| internal_err("Task join failed", e))?
}

async fn health(
    State(state): State<ServerState>,
    headers: HeaderMap,
) -> Result<impl IntoResponse, StatusCode> {
    verify_auth(&state, &headers)?;
    let username = state.username.read().map_err(|e| internal_err("RwLock poisoned", e))?;
    Ok(Json(HealthResponse {
        status: "ok".to_string(),
        username: username.clone(),
        instance_id: state.instance_id.clone(),
    }))
}

async fn list_files(
    State(state): State<ServerState>,
    headers: HeaderMap,
) -> Result<impl IntoResponse, StatusCode> {
    verify_auth(&state, &headers)?;
    let files = db_query(&state, |conn| db::get_all_files(conn)).await?;
    Ok(Json(files))
}

async fn get_markers(
    State(state): State<ServerState>,
    headers: HeaderMap,
    Path((file_hash, date)): Path<(String, String)>,
) -> Result<impl IntoResponse, StatusCode> {
    verify_auth(&state, &headers)?;
    let rows = db_query(&state, move |conn| {
        db::get_markers_for_file_date(conn, &file_hash, &date)
    })
    .await?;

    let markers: Vec<MarkerJson> = rows
        .into_iter()
        .map(|r| MarkerJson {
            username: r.username,
            sleep_markers: r.sleep_markers,
            nonwear_markers: r.nonwear_markers,
            is_no_sleep: r.is_no_sleep,
            notes: r.notes,
            content_hash: r.content_hash,
        })
        .collect();

    Ok(Json(MarkersResponse { markers }))
}

#[derive(Serialize)]
struct StudySettingsResponse {
    settings: Option<StudySettingsJson>,
}

#[derive(Serialize)]
struct StudySettingsJson {
    value_json: String,
    content_hash: String,
    updated_at: String,
}

async fn get_study_settings(
    State(state): State<ServerState>,
    headers: HeaderMap,
) -> Result<impl IntoResponse, StatusCode> {
    verify_auth(&state, &headers)?;
    let row = db_query(&state, |conn| db::get_study_settings(conn, "study")).await?;
    let settings = row.map(|r| StudySettingsJson {
        value_json: r.value_json,
        content_hash: r.content_hash,
        updated_at: r.updated_at,
    });
    Ok(Json(StudySettingsResponse { settings }))
}

/// Build the axum router.
pub fn build_router(state: ServerState) -> Router {
    Router::new()
        .route("/api/peers/health", get(health))
        .route("/api/peers/files", get(list_files))
        .route("/api/peers/markers/:file_hash/:date", get(get_markers))
        .route("/api/peers/study-settings", get(get_study_settings))
        .with_state(state)
}

/// Start the server on a random port (for testing). Returns the bound address.
pub async fn start_on_random_port(
    db: Arc<Mutex<Connection>>,
    group_hash: &str,
    username: &str,
    instance_id: &str,
) -> SocketAddr {
    let state = ServerState {
        db,
        group_hash: Arc::new(RwLock::new(group_hash.to_string())),
        username: Arc::new(RwLock::new(username.to_string())),
        instance_id: instance_id.to_string(),
    };
    let app = build_router(state);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    addr
}
