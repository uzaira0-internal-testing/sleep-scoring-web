use std::net::SocketAddr;
use std::sync::{Arc, Mutex};

use rusqlite::Connection;

use sleep_scoring_desktop::{db, server};

/// Start a test server with the given group hash. Returns the bound address and DB handle.
pub async fn start_test_server_with_group(group: &str) -> (SocketAddr, Arc<Mutex<Connection>>) {
    let conn = Connection::open_in_memory().unwrap();
    db::init_db_conn(&conn).unwrap();
    let db = Arc::new(Mutex::new(conn));
    let id = uuid::Uuid::new_v4().to_string();
    let addr = server::start_on_random_port(db.clone(), group, "testuser", &id).await;
    (addr, db)
}
