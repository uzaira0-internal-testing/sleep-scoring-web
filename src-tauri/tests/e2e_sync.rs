use sleep_scoring_desktop::db;

mod common;
use common::start_test_server_with_group;

#[tokio::test]
async fn test_peer_marker_exchange() {
    // Start two servers (simulating two Tauri instances)
    let (addr_a, db_a) = start_test_server_with_group("e2e_group").await;
    let (_addr_b, db_b) = start_test_server_with_group("e2e_group").await;

    // Alice writes markers on server A
    {
        let conn = db_a.lock().unwrap();
        db::upsert_markers(
            &conn,
            "shared_file_hash",
            "2024-01-15",
            "alice",
            r#"[{"onset_timestamp": 1000, "offset_timestamp": 2000, "marker_index": 0, "marker_type": "main_sleep"}]"#,
            "[]",
            false,
            "Looks like clear sleep period",
            "alice_hash_1",
        )
        .unwrap();
    }

    // Bob pulls from server A
    let client = reqwest::Client::new();
    let resp = client
        .get(format!(
            "http://{addr_a}/api/peers/markers/shared_file_hash/2024-01-15"
        ))
        .header("X-Group-Hash", "e2e_group")
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);
    let body: serde_json::Value = resp.json().await.unwrap();
    let markers = body["markers"].as_array().unwrap();
    assert_eq!(markers.len(), 1);
    assert_eq!(markers[0]["username"], "alice");

    // Bob saves Alice's markers into his own DB (simulating frontend import)
    let alice_marker = &markers[0];
    {
        let conn = db_b.lock().unwrap();
        db::upsert_markers(
            &conn,
            "shared_file_hash",
            "2024-01-15",
            "alice",
            alice_marker["sleep_markers"].as_str().unwrap_or("[]"),
            alice_marker["nonwear_markers"].as_str().unwrap_or("[]"),
            alice_marker["is_no_sleep"].as_bool().unwrap_or(false),
            alice_marker["notes"].as_str().unwrap_or(""),
            alice_marker["content_hash"].as_str().unwrap_or(""),
        )
        .unwrap();
    }

    // Verify Bob now has Alice's markers
    let bob_rows =
        db::get_markers_for_file_date(&db_b.lock().unwrap(), "shared_file_hash", "2024-01-15")
            .unwrap();
    assert_eq!(bob_rows.len(), 1);
    assert_eq!(bob_rows[0].username, "alice");
}

#[tokio::test]
async fn test_content_hash_dedup() {
    let (_addr, db) = start_test_server_with_group("dedup_group").await;

    let markers_json = r#"[{"onset": 100}]"#;
    let content_hash = "deterministic_hash_abc";

    {
        let conn = db.lock().unwrap();
        db::upsert_markers(&conn, "dedup_file", "2024-01-15", "alice", markers_json, "[]", false, "", content_hash).unwrap();
        db::upsert_markers(&conn, "dedup_file", "2024-01-15", "alice", markers_json, "[]", false, "", content_hash).unwrap();
    }

    let rows = db::get_markers_for_file_date(&db.lock().unwrap(), "dedup_file", "2024-01-15").unwrap();
    assert_eq!(rows.len(), 1);
}

#[tokio::test]
async fn test_multi_user_same_file() {
    let (addr, db) = start_test_server_with_group("multi_group").await;

    {
        let conn = db.lock().unwrap();
        db::upsert_markers(&conn, "multi_file", "2024-01-15", "alice", r#"[{"onset": 100}]"#, "[]", false, "", "alice_ch").unwrap();
        db::upsert_markers(&conn, "multi_file", "2024-01-15", "bob", r#"[{"onset": 200}]"#, "[]", false, "", "bob_ch").unwrap();
    }

    let client = reqwest::Client::new();
    let resp = client
        .get(format!(
            "http://{addr}/api/peers/markers/multi_file/2024-01-15"
        ))
        .header("X-Group-Hash", "multi_group")
        .send()
        .await
        .unwrap();
    let body: serde_json::Value = resp.json().await.unwrap();
    let markers = body["markers"].as_array().unwrap();
    assert_eq!(markers.len(), 2);
}
