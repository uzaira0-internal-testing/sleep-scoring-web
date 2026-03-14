use rusqlite::{params, Connection, Result};
use serde::Serialize;
use std::path::Path;

/// A row from the markers table.
#[derive(Debug, Clone, Serialize)]
pub struct MarkerRow {
    pub id: i64,
    pub file_hash: String,
    pub date: String,
    pub username: String,
    pub sleep_markers: String,
    pub nonwear_markers: String,
    pub is_no_sleep: bool,
    pub notes: String,
    pub content_hash: String,
    pub updated_at: String,
}

/// A file entry with its available dates.
#[derive(Debug, Clone, Serialize)]
pub struct FileEntry {
    pub file_hash: String,
    pub dates: Vec<String>,
}

/// A row from the study_settings table.
#[derive(Debug, Clone, Serialize)]
pub struct StudySettingsRow {
    pub id: i64,
    pub key: String,
    pub value_json: String,
    pub content_hash: String,
    pub updated_at: String,
}

/// Initialize the SQLite database schema on an open connection.
pub fn init_db_conn(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS markers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT NOT NULL,
            date TEXT NOT NULL,
            username TEXT NOT NULL,
            sleep_markers TEXT NOT NULL,
            nonwear_markers TEXT NOT NULL,
            is_no_sleep INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(file_hash, date, username)
        );
        CREATE INDEX IF NOT EXISTS idx_markers_file_hash ON markers(file_hash);
        CREATE INDEX IF NOT EXISTS idx_markers_lookup ON markers(file_hash, date);

        CREATE TABLE IF NOT EXISTS study_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            value_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        ",
    )?;
    Ok(())
}

/// Initialize a new SQLite database at the given path.
pub fn init_db(path: &Path) -> Result<Connection> {
    let conn = Connection::open(path)?;
    // WAL mode allows concurrent readers + single writer without blocking.
    // busy_timeout prevents SQLITE_BUSY errors by retrying for up to 5 seconds.
    conn.execute_batch(
        "PRAGMA journal_mode=WAL;
         PRAGMA busy_timeout=5000;",
    )?;
    init_db_conn(&conn)?;
    Ok(conn)
}

/// Map a std::io::Error to a rusqlite::Error for filesystem operations.
fn io_to_sqlite_err(msg: &str, e: std::io::Error) -> rusqlite::Error {
    rusqlite::Error::SqliteFailure(
        rusqlite::ffi::Error::new(rusqlite::ffi::SQLITE_CANTOPEN),
        Some(format!("{msg}: {e}")),
    )
}

/// Ensure a directory exists, mapping errors to rusqlite::Error.
fn ensure_dir(path: &Path) -> Result<()> {
    std::fs::create_dir_all(path)
        .map_err(|e| io_to_sqlite_err("Failed to create directory", e))
}

/// Open (or create) a workspace-scoped SQLite database.
/// Path: `{data_dir}/workspaces/{workspace_id}/sleep-scoring.db`
pub fn open_workspace_db(data_dir: &Path, workspace_id: &str) -> Result<Connection> {
    let ws_dir = data_dir.join("workspaces").join(workspace_id);
    ensure_dir(&ws_dir)?;
    init_db(&ws_dir.join("sleep-scoring.db"))
}

/// Migrate legacy (pre-workspace) database to a workspace directory.
/// Copies `{data_dir}/sleep-scoring.db` → `{data_dir}/workspaces/{workspace_id}/sleep-scoring.db`
/// if the legacy file exists and the workspace directory does not yet have a database.
/// Returns `true` if migration was performed.
pub fn migrate_legacy_db(data_dir: &Path, workspace_id: &str) -> Result<bool> {
    let legacy_path = data_dir.join("sleep-scoring.db");
    let ws_dir = data_dir.join("workspaces").join(workspace_id);
    let ws_db_path = ws_dir.join("sleep-scoring.db");

    if legacy_path.exists() && !ws_db_path.exists() {
        ensure_dir(&ws_dir)?;
        // Copy to a temp file then atomic-rename to prevent corruption if
        // the process crashes mid-copy.
        let tmp_path = ws_db_path.with_extension("db.tmp");
        std::fs::copy(&legacy_path, &tmp_path)
            .map_err(|e| io_to_sqlite_err("Failed to copy legacy database to temp file", e))?;
        std::fs::rename(&tmp_path, &ws_db_path)
            .map_err(|e| io_to_sqlite_err("Failed to rename temp file to workspace database", e))?;
        Ok(true)
    } else {
        Ok(false)
    }
}

/// Insert or update markers for a (file_hash, date, username) triple.
pub fn upsert_markers(
    conn: &Connection,
    file_hash: &str,
    date: &str,
    username: &str,
    sleep_markers: &str,
    nonwear_markers: &str,
    is_no_sleep: bool,
    notes: &str,
    content_hash: &str,
) -> Result<()> {
    conn.execute(
        "INSERT INTO markers (file_hash, date, username, sleep_markers, nonwear_markers, is_no_sleep, notes, content_hash, updated_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, datetime('now'))
         ON CONFLICT(file_hash, date, username) DO UPDATE SET
           sleep_markers = excluded.sleep_markers,
           nonwear_markers = excluded.nonwear_markers,
           is_no_sleep = excluded.is_no_sleep,
           notes = excluded.notes,
           content_hash = excluded.content_hash,
           updated_at = excluded.updated_at",
        params![file_hash, date, username, sleep_markers, nonwear_markers, is_no_sleep as i32, notes, content_hash],
    )?;
    Ok(())
}

/// Get all marker rows for a specific file_hash + date.
pub fn get_markers_for_file_date(conn: &Connection, file_hash: &str, date: &str) -> Result<Vec<MarkerRow>> {
    let mut stmt = conn.prepare(
        "SELECT id, file_hash, date, username, sleep_markers, nonwear_markers, is_no_sleep, notes, content_hash, updated_at
         FROM markers WHERE file_hash = ?1 AND date = ?2",
    )?;

    let rows = stmt.query_map(params![file_hash, date], |row| {
        Ok(MarkerRow {
            id: row.get(0)?,
            file_hash: row.get(1)?,
            date: row.get(2)?,
            username: row.get(3)?,
            sleep_markers: row.get(4)?,
            nonwear_markers: row.get(5)?,
            is_no_sleep: row.get::<_, i32>(6)? != 0,
            notes: row.get(7)?,
            content_hash: row.get(8)?,
            updated_at: row.get(9)?,
        })
    })?;

    rows.collect()
}

/// Get all distinct file hashes with their dates (single query, no N+1).
pub fn get_all_files(conn: &Connection) -> Result<Vec<FileEntry>> {
    let mut stmt = conn.prepare(
        "SELECT file_hash, date FROM markers GROUP BY file_hash, date ORDER BY file_hash, date",
    )?;

    let rows: Vec<(String, String)> = stmt
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))?
        .collect::<Result<Vec<_>>>()?;

    let mut files: Vec<FileEntry> = Vec::new();
    for (hash, date) in rows {
        if let Some(last) = files.last_mut() {
            if last.file_hash == hash {
                last.dates.push(date);
                continue;
            }
        }
        files.push(FileEntry {
            file_hash: hash,
            dates: vec![date],
        });
    }

    Ok(files)
}

/// Upsert study settings by key.
pub fn upsert_study_settings(
    conn: &Connection,
    key: &str,
    value_json: &str,
    content_hash: &str,
) -> Result<()> {
    conn.execute(
        "INSERT INTO study_settings (key, value_json, content_hash, updated_at)
         VALUES (?1, ?2, ?3, datetime('now'))
         ON CONFLICT(key) DO UPDATE SET
           value_json = excluded.value_json,
           content_hash = excluded.content_hash,
           updated_at = excluded.updated_at",
        params![key, value_json, content_hash],
    )?;
    Ok(())
}

/// Get study settings by key.
pub fn get_study_settings(conn: &Connection, key: &str) -> Result<Option<StudySettingsRow>> {
    let mut stmt = conn.prepare(
        "SELECT id, key, value_json, content_hash, updated_at FROM study_settings WHERE key = ?1",
    )?;
    let mut rows = stmt.query_map(params![key], |row| {
        Ok(StudySettingsRow {
            id: row.get(0)?,
            key: row.get(1)?,
            value_json: row.get(2)?,
            content_hash: row.get(3)?,
            updated_at: row.get(4)?,
        })
    })?;
    match rows.next() {
        Some(row) => Ok(Some(row?)),
        None => Ok(None),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn setup() -> Connection {
        let conn = Connection::open_in_memory().unwrap();
        init_db_conn(&conn).unwrap();
        conn
    }

    #[test]
    fn test_upsert_and_get() {
        let conn = setup();
        upsert_markers(&conn, "hash1", "2024-01-15", "alice", "[]", "[]", false, "", "ch1").unwrap();
        let rows = get_markers_for_file_date(&conn, "hash1", "2024-01-15").unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].username, "alice");
    }

    #[test]
    fn test_upsert_idempotent() {
        let conn = setup();
        for _ in 0..3 {
            upsert_markers(&conn, "hash1", "2024-01-15", "alice", "[]", "[]", false, "", "ch1").unwrap();
        }
        let rows = get_markers_for_file_date(&conn, "hash1", "2024-01-15").unwrap();
        assert_eq!(rows.len(), 1);
    }

    #[test]
    fn test_multi_user() {
        let conn = setup();
        upsert_markers(&conn, "hash1", "2024-01-15", "alice", "[1]", "[]", false, "", "ch_a").unwrap();
        upsert_markers(&conn, "hash1", "2024-01-15", "bob", "[2]", "[]", false, "", "ch_b").unwrap();
        let rows = get_markers_for_file_date(&conn, "hash1", "2024-01-15").unwrap();
        assert_eq!(rows.len(), 2);
    }

    #[test]
    fn test_upsert_overwrites_values() {
        let conn = setup();
        upsert_markers(&conn, "hash1", "2024-01-15", "alice", "[old]", "[]", false, "old notes", "ch_old").unwrap();
        upsert_markers(&conn, "hash1", "2024-01-15", "alice", "[new]", "[nw]", true, "new notes", "ch_new").unwrap();
        let rows = get_markers_for_file_date(&conn, "hash1", "2024-01-15").unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].sleep_markers, "[new]");
        assert_eq!(rows[0].nonwear_markers, "[nw]");
        assert!(rows[0].is_no_sleep);
        assert_eq!(rows[0].notes, "new notes");
        assert_eq!(rows[0].content_hash, "ch_new");
    }

    #[test]
    fn test_get_all_files() {
        let conn = setup();
        upsert_markers(&conn, "hash_a", "2024-01-15", "alice", "[]", "[]", false, "", "ch1").unwrap();
        upsert_markers(&conn, "hash_a", "2024-01-16", "alice", "[]", "[]", false, "", "ch2").unwrap();
        upsert_markers(&conn, "hash_b", "2024-02-01", "bob", "[]", "[]", false, "", "ch3").unwrap();
        let files = get_all_files(&conn).unwrap();
        assert_eq!(files.len(), 2);
        let a = files.iter().find(|f| f.file_hash == "hash_a").unwrap();
        assert_eq!(a.dates.len(), 2);
    }

    #[test]
    fn test_open_workspace_db() {
        let tmp = tempfile::tempdir().unwrap();
        let conn = open_workspace_db(tmp.path(), "ws-abc-123").unwrap();
        // Verify schema works
        upsert_markers(&conn, "h1", "2024-01-01", "alice", "[]", "[]", false, "", "ch1").unwrap();
        let rows = get_markers_for_file_date(&conn, "h1", "2024-01-01").unwrap();
        assert_eq!(rows.len(), 1);
        // Verify file was created in the right place
        assert!(tmp.path().join("workspaces/ws-abc-123/sleep-scoring.db").exists());
    }

    #[test]
    fn test_migrate_legacy_db() {
        let tmp = tempfile::tempdir().unwrap();
        // Create a legacy database with some data
        let legacy_path = tmp.path().join("sleep-scoring.db");
        let legacy_conn = init_db(&legacy_path).unwrap();
        upsert_markers(&legacy_conn, "h1", "2024-01-01", "alice", "[1,2]", "[]", false, "note", "ch1").unwrap();
        drop(legacy_conn);

        // Migration should copy to workspace dir
        let migrated = migrate_legacy_db(tmp.path(), "ws-default").unwrap();
        assert!(migrated);
        assert!(tmp.path().join("workspaces/ws-default/sleep-scoring.db").exists());

        // Verify migrated data is intact
        let ws_conn = open_workspace_db(tmp.path(), "ws-default").unwrap();
        let rows = get_markers_for_file_date(&ws_conn, "h1", "2024-01-01").unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].sleep_markers, "[1,2]");
    }

    #[test]
    fn test_migrate_legacy_db_no_legacy() {
        let tmp = tempfile::tempdir().unwrap();
        // No legacy file → no migration
        let migrated = migrate_legacy_db(tmp.path(), "ws-123").unwrap();
        assert!(!migrated);
    }

    #[test]
    fn test_migrate_legacy_db_already_exists() {
        let tmp = tempfile::tempdir().unwrap();
        // Create legacy db
        let legacy_path = tmp.path().join("sleep-scoring.db");
        let legacy_conn = init_db(&legacy_path).unwrap();
        upsert_markers(&legacy_conn, "h1", "2024-01-01", "alice", "[old]", "[]", false, "", "ch1").unwrap();
        drop(legacy_conn);

        // Create workspace db with different data
        let ws_conn = open_workspace_db(tmp.path(), "ws-default").unwrap();
        upsert_markers(&ws_conn, "h1", "2024-01-01", "alice", "[new]", "[]", false, "", "ch2").unwrap();
        drop(ws_conn);

        // Migration should NOT overwrite existing workspace db
        let migrated = migrate_legacy_db(tmp.path(), "ws-default").unwrap();
        assert!(!migrated);

        // Verify workspace data is unchanged
        let ws_conn = open_workspace_db(tmp.path(), "ws-default").unwrap();
        let rows = get_markers_for_file_date(&ws_conn, "h1", "2024-01-01").unwrap();
        assert_eq!(rows[0].sleep_markers, "[new]");
    }
}
