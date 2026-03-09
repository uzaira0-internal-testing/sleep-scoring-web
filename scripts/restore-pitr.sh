#!/bin/bash
# =============================================================================
# Point-in-Time Recovery (PITR) Script — sleep-scoring-web
# =============================================================================
# Restores the database to a specific point in time using a base backup + WAL.
#
# Usage:
#   ./scripts/restore-pitr.sh "2026-03-05 14:30:00"    # Restore to timestamp
#   ./scripts/restore-pitr.sh latest                     # Replay all available WAL
#   ./scripts/restore-pitr.sh --list                     # Show available backups
#
# WARNING: This STOPS the running database and REPLACES it with the restored one.
#          A safety backup of the current state is taken first.
# =============================================================================
set -euo pipefail

BACKUP_ROOT="/home/uzair/backups/sleep-scoring"
BASEBACKUP_DIR="$BACKUP_ROOT/basebackup"
WAL_BACKUP_DIR="$BACKUP_ROOT/wal"
DB_BACKUP_DIR="$BACKUP_ROOT/db"

CONTAINER_NAME="sleep-scoring-postgres"
COMPOSE_DIR="/opt/sleep-scoring-web/docker"
COMPOSE_FILE="docker-compose.local.yml"

die() { echo "FATAL: $1" >&2; exit 1; }

# -----------------------------------------------------------------------------
# --list: Show available recovery points
# -----------------------------------------------------------------------------
if [ "${1:-}" = "--list" ]; then
    echo "=== Available Base Backups ==="
    ls -lh "$BASEBACKUP_DIR"/base_*.tar.gz 2>/dev/null || echo "  (none)"
    echo ""
    echo "=== Available pg_dump Snapshots ==="
    ls -lh "$DB_BACKUP_DIR"/*.dump 2>/dev/null | tail -10 || echo "  (none)"
    echo ""
    echo "=== WAL Archive ==="
    WAL_COUNT=$(find "$WAL_BACKUP_DIR" -name "0*" -type f 2>/dev/null | wc -l)
    if [ "$WAL_COUNT" -gt 0 ]; then
        OLDEST=$(ls -tr "$WAL_BACKUP_DIR"/0* 2>/dev/null | head -1)
        NEWEST=$(ls -t "$WAL_BACKUP_DIR"/0* 2>/dev/null | head -1)
        echo "  $WAL_COUNT WAL files"
        echo "  Oldest: $(stat -c '%y' "$OLDEST" 2>/dev/null | cut -d. -f1)"
        echo "  Newest: $(stat -c '%y' "$NEWEST" 2>/dev/null | cut -d. -f1)"
    else
        echo "  (none)"
    fi
    echo ""
    echo "To restore: $0 \"YYYY-MM-DD HH:MM:SS\" or $0 latest"
    exit 0
fi

TARGET="${1:-}"
[ -z "$TARGET" ] && die "Usage: $0 <timestamp|latest|--list>"

# Find latest base backup
LATEST_BASE=$(ls -t "$BASEBACKUP_DIR"/base_*.tar.gz 2>/dev/null | head -1)
[ -z "$LATEST_BASE" ] && die "No base backup found in $BASEBACKUP_DIR. Run backup first."

echo "=== Point-in-Time Recovery ==="
echo "  Base backup: $(basename "$LATEST_BASE")"
echo "  Target time: $TARGET"
echo "  WAL files:   $(find "$WAL_BACKUP_DIR" -name '0*' -type f 2>/dev/null | wc -l)"
echo ""
echo "WARNING: This will STOP the database and REPLACE it."
echo "A safety backup of the current state will be taken first."
read -p "Continue? (yes/no): " CONFIRM
[ "$CONFIRM" = "yes" ] || die "Aborted."

# -----------------------------------------------------------------------------
# 1. Safety backup of current state
# -----------------------------------------------------------------------------
echo "Taking safety backup of current database..."
SAFETY_TS=$(date +%Y%m%d_%H%M%S)
docker exec "$CONTAINER_NAME" pg_dump -U sleep -d sleep_scoring --format=custom \
    > "$DB_BACKUP_DIR/sleep_scoring_${SAFETY_TS}_pre_pitr.dump" \
    || die "Safety backup failed"
echo "Safety backup saved: sleep_scoring_${SAFETY_TS}_pre_pitr.dump"

# -----------------------------------------------------------------------------
# 2. Stop services
# -----------------------------------------------------------------------------
echo "Stopping services..."
cd "$COMPOSE_DIR"
docker compose -f "$COMPOSE_FILE" stop backend frontend
docker compose -f "$COMPOSE_FILE" stop postgres

# -----------------------------------------------------------------------------
# 3. Replace data volume with base backup + recovery config
# -----------------------------------------------------------------------------
echo "Preparing recovery volume..."

# Create a temporary container to manipulate the data volume
PGDATA_VOLUME="sleep-scoring-web_postgres_data"

# Clear existing data and extract base backup
docker run --rm \
    -v "$PGDATA_VOLUME":/pgdata \
    -v "$(realpath "$LATEST_BASE")":/backup/base.tar.gz \
    -v "$WAL_BACKUP_DIR":/wal_source \
    alpine sh -c '
        echo "Clearing old data..."
        rm -rf /pgdata/*
        echo "Extracting base backup..."
        tar xzf /backup/base.tar.gz -C /pgdata/
        echo "Copying WAL files for replay..."
        mkdir -p /pgdata/pg_wal_restore
        cp /wal_source/0* /pgdata/pg_wal_restore/ 2>/dev/null || true
        echo "WAL files copied: $(ls /pgdata/pg_wal_restore/ 2>/dev/null | wc -l)"
        chown -R 70:70 /pgdata/
    '

# Create recovery signal and config
if [ "$TARGET" = "latest" ]; then
    RECOVERY_CONF="restore_command = 'cp /var/lib/postgresql/data/pg_wal_restore/%f %p 2>/dev/null || false'"
else
    RECOVERY_CONF="restore_command = 'cp /var/lib/postgresql/data/pg_wal_restore/%f %p 2>/dev/null || false'
recovery_target_time = '$TARGET'
recovery_target_action = 'promote'"
fi

docker run --rm -v "$PGDATA_VOLUME":/pgdata alpine sh -c "
    echo '$RECOVERY_CONF' >> /pgdata/postgresql.auto.conf
    touch /pgdata/recovery.signal
    chown 70:70 /pgdata/postgresql.auto.conf /pgdata/recovery.signal
"

# -----------------------------------------------------------------------------
# 4. Start postgres (it will enter recovery mode)
# -----------------------------------------------------------------------------
echo "Starting postgres in recovery mode..."
docker compose -f "$COMPOSE_FILE" up -d postgres
echo "Waiting for recovery to complete..."

for i in $(seq 1 60); do
    if docker exec "$CONTAINER_NAME" pg_isready -U sleep -q 2>/dev/null; then
        echo "Database is ready after recovery."
        break
    fi
    sleep 2
done

# Clean up recovery WAL files
docker exec "$CONTAINER_NAME" rm -rf /var/lib/postgresql/data/pg_wal_restore 2>/dev/null || true

# Verify
TABLES=$(docker exec "$CONTAINER_NAME" psql -U sleep -d sleep_scoring -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ')
echo "Recovery complete. Tables found: $TABLES"

# -----------------------------------------------------------------------------
# 5. Restart all services
# -----------------------------------------------------------------------------
echo "Starting all services..."
docker compose -f "$COMPOSE_FILE" up -d
echo ""
echo "=== PITR Complete ==="
echo "Restored to: $TARGET"
echo "Safety backup: $DB_BACKUP_DIR/sleep_scoring_${SAFETY_TS}_pre_pitr.dump"
