use std::net::SocketAddr;
use std::sync::{Arc, Mutex};

use rusqlite::Connection;

use sleep_scoring_desktop::db;

mod common;
use common::start_test_server_with_group;

async fn start_test_server() -> (SocketAddr, Arc<Mutex<Connection>>) {
    start_test_server_with_group("testgroup").await
}

#[tokio::test]
async fn test_health_endpoint() {
    let (addr, _db) = start_test_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .get(format!("http://{addr}/api/peers/health"))
        .header("X-Group-Hash", "testgroup")
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["status"], "ok");
    assert_eq!(body["username"], "testuser");
}

#[tokio::test]
async fn test_auth_rejection() {
    let (addr, _db) = start_test_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .get(format!("http://{addr}/api/peers/health"))
        .header("X-Group-Hash", "wronghash")
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 403);
}

#[tokio::test]
async fn test_markers_roundtrip() {
    let (addr, db) = start_test_server().await;
    db::upsert_markers(
        &db.lock().unwrap(),
        "filehash1",
        "2024-01-15",
        "alice",
        r#"[{"onset_timestamp": 1000, "offset_timestamp": 2000}]"#,
        "[]",
        false,
        "",
        "contenthash1",
    )
    .unwrap();

    let client = reqwest::Client::new();
    let resp = client
        .get(format!(
            "http://{addr}/api/peers/markers/filehash1/2024-01-15"
        ))
        .header("X-Group-Hash", "testgroup")
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert!(!body["markers"].as_array().unwrap().is_empty());
    assert_eq!(body["markers"][0]["username"], "alice");
}

#[tokio::test]
async fn test_files_list() {
    let (addr, db) = start_test_server().await;
    {
        let conn = db.lock().unwrap();
        db::upsert_markers(&conn, "hash_a", "2024-01-15", "alice", "[]", "[]", false, "", "ch1").unwrap();
        db::upsert_markers(&conn, "hash_a", "2024-01-16", "alice", "[]", "[]", false, "", "ch2").unwrap();
        db::upsert_markers(&conn, "hash_b", "2024-02-01", "bob", "[]", "[]", false, "", "ch3").unwrap();
    }

    let client = reqwest::Client::new();
    let resp = client
        .get(format!("http://{addr}/api/peers/files"))
        .header("X-Group-Hash", "testgroup")
        .send()
        .await
        .unwrap();
    let body: serde_json::Value = resp.json().await.unwrap();
    let files = body.as_array().unwrap();
    assert_eq!(files.len(), 2);
}

#[tokio::test]
async fn test_concurrent_writes() {
    let (_addr, db) = start_test_server().await;
    let handles: Vec<_> = (0..10)
        .map(|i| {
            let db = db.clone();
            tokio::spawn(async move {
                let conn = db.lock().unwrap();
                db::upsert_markers(
                    &conn,
                    "concurrent_hash",
                    "2024-01-15",
                    &format!("user_{i}"),
                    "[]",
                    "[]",
                    false,
                    "",
                    &format!("ch_{i}"),
                )
                .unwrap();
            })
        })
        .collect();

    for h in handles {
        h.await.unwrap();
    }

    let rows = db::get_markers_for_file_date(&db.lock().unwrap(), "concurrent_hash", "2024-01-15").unwrap();
    assert_eq!(rows.len(), 10);
}

#[tokio::test]
async fn test_upsert_idempotent() {
    let (_addr, db) = start_test_server().await;
    for _ in 0..2 {
        let conn = db.lock().unwrap();
        db::upsert_markers(
            &conn,
            "idem_hash",
            "2024-01-15",
            "alice",
            r#"[{"onset": 100}]"#,
            "[]",
            false,
            "",
            "same_content_hash",
        )
        .unwrap();
    }
    let rows = db::get_markers_for_file_date(&db.lock().unwrap(), "idem_hash", "2024-01-15").unwrap();
    assert_eq!(rows.len(), 1);
}

#[tokio::test]
async fn test_auth_missing_header() {
    let (addr, _db) = start_test_server().await;
    let client = reqwest::Client::new();
    // No X-Group-Hash header at all
    let resp = client
        .get(format!("http://{addr}/api/peers/health"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 403);
}

#[tokio::test]
async fn test_auth_empty_group_hash_returns_503() {
    // Server with empty group_hash (simulates pre-login state)
    let conn = rusqlite::Connection::open_in_memory().unwrap();
    sleep_scoring_desktop::db::init_db_conn(&conn).unwrap();
    let db = std::sync::Arc::new(std::sync::RwLock::new(std::sync::Arc::new(std::sync::Mutex::new(conn))));
    let addr = sleep_scoring_desktop::server::start_on_random_port(db, "", "testuser", "test-id").await;
    let client = reqwest::Client::new();
    let resp = client
        .get(format!("http://{addr}/api/peers/health"))
        .header("X-Group-Hash", "anything")
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 503);
}

#[tokio::test]
async fn test_empty_markers_response() {
    let (addr, _db) = start_test_server().await;
    let client = reqwest::Client::new();
    let resp = client
        .get(format!("http://{addr}/api/peers/markers/nonexistent/2024-01-01"))
        .header("X-Group-Hash", "testgroup")
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["markers"].as_array().unwrap().len(), 0);
}
