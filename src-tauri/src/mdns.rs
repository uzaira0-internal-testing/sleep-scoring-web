use std::time::{Duration, Instant};

use mdns_sd::{ServiceDaemon, ServiceEvent, ServiceInfo};
use serde::Serialize;

const SERVICE_TYPE: &str = "_sleepscoring._tcp.local.";

/// Information about a discovered peer.
#[derive(Debug, Clone, Serialize)]
pub struct PeerInfo {
    pub username: String,
    pub address: String,
    pub instance_id: String,
}

/// Manages mDNS service registration for this instance.
pub struct MdnsManager {
    daemon: Option<ServiceDaemon>,
    #[allow(dead_code)]
    fullname: String,
}

impl MdnsManager {
    /// Register this instance on the local network.
    pub fn register(
        username: &str,
        port: u16,
        group_hash: &str,
        instance_id: &str,
    ) -> Result<Self, mdns_sd::Error> {
        let daemon = ServiceDaemon::new()?;
        let hostname = gethostname::gethostname()
            .to_string_lossy()
            .to_string();
        let instance_name = format!("{username}@{hostname}");

        // Note: group_hash is NOT broadcast in mDNS TXT records (it's the auth secret).
        // Peers discover all services and filter by group_hash via the HTTP health endpoint.
        let properties = [
            ("username", username),
            ("instance_id", instance_id),
            ("version", "1"),
        ];

        let service = ServiceInfo::new(
            SERVICE_TYPE,
            &instance_name,
            &format!("{hostname}.local."),
            "",
            port,
            &properties[..],
        )?;

        daemon.register(service)?;
        Ok(Self {
            daemon: Some(daemon),
            fullname: instance_name,
        })
    }

    /// Browse for all sleep-scoring peers on the LAN. Collects for ~2 seconds.
    /// Group filtering happens via HTTP auth, not mDNS (group_hash is not broadcast).
    pub fn browse(_group_hash: &str) -> Result<Vec<PeerInfo>, mdns_sd::Error> {
        let daemon = ServiceDaemon::new()?;
        let receiver = daemon.browse(SERVICE_TYPE)?;
        let mut peers = Vec::new();

        let deadline = Instant::now() + Duration::from_secs(2);
        while Instant::now() < deadline {
            match receiver.recv_timeout(Duration::from_millis(100)) {
                Ok(event) => {
                    if let ServiceEvent::ServiceResolved(info) = event {
                        let username = info
                            .get_property_val_str("username")
                            .unwrap_or_default()
                            .to_string();
                        let instance_id = info
                            .get_property_val_str("instance_id")
                            .unwrap_or_default()
                            .to_string();
                        if username.is_empty() || instance_id.is_empty() {
                            log::warn!("Skipping mDNS peer with empty username or instance_id");
                            continue;
                        }
                        if let Some(addr) = info.get_addresses().iter().next() {
                            peers.push(PeerInfo {
                                username,
                                address: format!("http://{}:{}", addr, info.get_port()),
                                instance_id,
                            });
                        }
                    }
                }
                Err(flume::RecvTimeoutError::Timeout) => continue,
                Err(_) => break,
            }
        }

        if let Err(e) = daemon.shutdown() {
            log::warn!("mDNS browse shutdown failed: {e}");
        }
        Ok(peers)
    }

    /// Shut down the mDNS daemon (unregisters the service).
    pub fn shutdown(&mut self) -> Result<(), mdns_sd::Error> {
        if let Some(daemon) = self.daemon.take() {
            daemon.shutdown().map(|_| ())
        } else {
            Ok(())
        }
    }
}

impl Drop for MdnsManager {
    fn drop(&mut self) {
        if let Err(e) = self.shutdown() {
            log::warn!("mDNS shutdown failed in drop: {e}");
        }
    }
}
