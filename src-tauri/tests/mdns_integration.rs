use std::time::Duration;

use sleep_scoring_desktop::mdns::MdnsManager;

/// Test that mDNS registration and browsing works on loopback.
///
/// NOTE: This test requires multicast support on loopback, which may not
/// be available in all CI environments. Mark as #[ignore] if needed.
#[tokio::test]
#[ignore = "requires multicast on loopback, run locally"]
async fn test_register_and_discover() {
    let group_hash = "test1234";
    let id1 = uuid::Uuid::new_v4().to_string();
    let id2 = uuid::Uuid::new_v4().to_string();

    let _reg1 = MdnsManager::register("alice", 9001, group_hash, &id1).unwrap();
    let _reg2 = MdnsManager::register("bob", 9002, group_hash, &id2).unwrap();

    tokio::time::sleep(Duration::from_secs(3)).await;

    let peers = MdnsManager::browse(group_hash).unwrap();
    assert!(peers.len() >= 2);
    let usernames: Vec<&str> = peers.iter().map(|p| p.username.as_str()).collect();
    assert!(usernames.contains(&"alice"));
    assert!(usernames.contains(&"bob"));
}

/// Test that different group hashes don't see each other.
#[tokio::test]
#[ignore = "requires multicast on loopback, run locally"]
async fn test_group_isolation() {
    let id_a = uuid::Uuid::new_v4().to_string();
    let id_b = uuid::Uuid::new_v4().to_string();

    let _reg_a = MdnsManager::register("alice", 9003, "group_aaa", &id_a).unwrap();
    let _reg_b = MdnsManager::register("bob", 9004, "group_bbb", &id_b).unwrap();

    tokio::time::sleep(Duration::from_secs(3)).await;

    let peers_a = MdnsManager::browse("group_aaa").unwrap();
    let peers_b = MdnsManager::browse("group_bbb").unwrap();

    assert!(peers_a.iter().all(|p| p.username != "bob"));
    assert!(peers_b.iter().all(|p| p.username != "alice"));
}

/// Test that self-filtering works correctly.
#[tokio::test]
#[ignore = "requires multicast on loopback, run locally"]
async fn test_self_filtering() {
    let id = uuid::Uuid::new_v4().to_string();
    let _reg = MdnsManager::register("alice", 9005, "group_self", &id).unwrap();

    tokio::time::sleep(Duration::from_secs(3)).await;

    let peers = MdnsManager::browse("group_self").unwrap();
    let filtered: Vec<_> = peers.into_iter().filter(|p| p.instance_id != id).collect();
    assert_eq!(filtered.len(), 0);
}
