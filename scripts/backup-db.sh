#!/bin/bash
# =============================================================================
# PostgreSQL Backup Script — sleep-scoring-web
# =============================================================================
# Dumps the database from the Docker container and stores backups on the HOST
# filesystem (completely outside Docker volumes). Survives docker-compose down -v,
# volume prunes, and any other Docker nonsense.
#
# Usage:
#   ./scripts/backup-db.sh              # Full backup (DB + uploads)
#   ./scripts/backup-db.sh --db-only    # Database only
#   ./scripts/backup-db.sh --dry-run    # Show what would happen
#
# Restoring:
#   ./scripts/restore-db.sh /home/uzair/backups/sleep-scoring/db/<file>.dump
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
BACKUP_ROOT="/home/uzair/backups/sleep-scoring"
DB_BACKUP_DIR="$BACKUP_ROOT/db"
UPLOADS_BACKUP_DIR="$BACKUP_ROOT/uploads"
LOG_DIR="$BACKUP_ROOT/logs"
LOG_FILE="$LOG_DIR/backup.log"

CONTAINER_NAME="sleep-scoring-postgres"
BACKEND_CONTAINER="sleep-scoring-backend"

# Auto-detect credentials from the running container
DB_USER=$(docker exec "$CONTAINER_NAME" bash -c 'echo $POSTGRES_USER' 2>/dev/null || echo "sleep")
DB_NAME=$(docker exec "$CONTAINER_NAME" bash -c 'echo $POSTGRES_DB' 2>/dev/null || echo "sleep_scoring")

RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

DB_ONLY=false
DRY_RUN=false

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
for arg in "$@"; do
    case $arg in
        --db-only)   DB_ONLY=true ;;
        --dry-run)   DRY_RUN=true ;;
        -h|--help)
            head -16 "$0" | tail -14
            exit 0
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

die() {
    log "FATAL: $1"
    exit 1
}

# Ensure backup directories exist
mkdir -p "$DB_BACKUP_DIR" "$UPLOADS_BACKUP_DIR" "$LOG_DIR"

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------
log "=== Backup starting ==="

# Verify the postgres container is running
if ! docker inspect --format='{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null | grep -q running; then
    die "Container '$CONTAINER_NAME' is not running. Cannot backup."
fi

# Verify we can connect to the database
if ! docker exec "$CONTAINER_NAME" pg_isready -U "$DB_USER" -d "$DB_NAME" -q 2>/dev/null; then
    die "PostgreSQL is not accepting connections inside '$CONTAINER_NAME'."
fi

if $DRY_RUN; then
    log "[DRY RUN] Would create: $DB_BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.dump"
    log "[DRY RUN] Would create: $DB_BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"
    if ! $DB_ONLY; then
        log "[DRY RUN] Would rsync uploads to: $UPLOADS_BACKUP_DIR/"
    fi
    log "[DRY RUN] Would delete backups older than $RETENTION_DAYS days"
    exit 0
fi

# -----------------------------------------------------------------------------
# 1. Database backup — custom format (fast restore, compressed)
# -----------------------------------------------------------------------------
DUMP_FILE="$DB_BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.dump"
log "Dumping database (custom format) → $DUMP_FILE"

docker exec "$CONTAINER_NAME" \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom \
    > "$DUMP_FILE" \
    || die "pg_dump (custom format) failed"

DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
log "Custom dump complete: $DUMP_SIZE"

# -----------------------------------------------------------------------------
# 2. Database backup — SQL (portable, human-readable)
# -----------------------------------------------------------------------------
SQL_GZ_FILE="$DB_BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"
log "Dumping database (SQL + gzip) → $SQL_GZ_FILE"

docker exec "$CONTAINER_NAME" \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --format=plain \
    | gzip -9 \
    > "$SQL_GZ_FILE" \
    || die "pg_dump (SQL format) failed"

SQL_GZ_SIZE=$(du -h "$SQL_GZ_FILE" | cut -f1)
log "SQL dump complete: $SQL_GZ_SIZE"

# -----------------------------------------------------------------------------
# 3. Backup uploaded files (tar from backend container to host)
# -----------------------------------------------------------------------------
if ! $DB_ONLY; then
    if docker inspect --format='{{.State.Status}}' "$BACKEND_CONTAINER" 2>/dev/null | grep -q running; then
        log "Syncing uploaded files → $UPLOADS_BACKUP_DIR/"
        docker exec "$BACKEND_CONTAINER" \
            tar cf - -C /app/uploads . 2>/dev/null \
            | tar xf - -C "$UPLOADS_BACKUP_DIR/" 2>/dev/null \
            || log "WARNING: Upload file backup had issues (directory may be empty)"

        UPLOAD_FILE_COUNT=$(find "$UPLOADS_BACKUP_DIR" -type f 2>/dev/null | wc -l)
        log "Upload backup complete: $UPLOAD_FILE_COUNT files"
    else
        log "WARNING: Backend container not running, skipping upload file backup"
    fi
fi

# -----------------------------------------------------------------------------
# 4. WAL archive — copy archived WAL files from Docker volume to host
# -----------------------------------------------------------------------------
WAL_BACKUP_DIR="$BACKUP_ROOT/wal"
mkdir -p "$WAL_BACKUP_DIR"

WAL_VOLUME="sleep-scoring-web_wal_archive"
if docker volume inspect "$WAL_VOLUME" >/dev/null 2>&1; then
    log "Copying WAL archive files → $WAL_BACKUP_DIR/"
    # Use a temp container to read from the volume
    docker run --rm -v "$WAL_VOLUME":/wal -v "$WAL_BACKUP_DIR":/host alpine sh -c \
        'cp -n /wal/0* /host/ 2>/dev/null; echo "$(ls /wal/0* 2>/dev/null | wc -l) WAL files in archive"' 2>/dev/null \
        || log "WARNING: WAL archive copy had issues"
    WAL_HOST_COUNT=$(find "$WAL_BACKUP_DIR" -name "0*" -type f 2>/dev/null | wc -l)
    log "WAL files on host: $WAL_HOST_COUNT"
else
    log "WARNING: WAL archive volume not found, skipping"
fi

# -----------------------------------------------------------------------------
# 5. Base backup for PITR (weekly — only on Sundays or if none exists)
# -----------------------------------------------------------------------------
BASEBACKUP_DIR="$BACKUP_ROOT/basebackup"
mkdir -p "$BASEBACKUP_DIR"

DAY_OF_WEEK=$(date +%u)  # 7 = Sunday
LATEST_BASE=$(find "$BASEBACKUP_DIR" -name "base_*.tar.gz" -mtime -7 2>/dev/null | head -1)

if [ "$DAY_OF_WEEK" = "7" ] || [ -z "$LATEST_BASE" ]; then
    BASE_FILE="$BASEBACKUP_DIR/base_${TIMESTAMP}.tar.gz"
    log "Taking base backup (for PITR) → $BASE_FILE"
    docker exec "$CONTAINER_NAME" pg_basebackup -U "$DB_USER" -D /tmp/basebackup -Ft -z -P 2>/dev/null \
        && docker cp "$CONTAINER_NAME":/tmp/basebackup/base.tar.gz "$BASE_FILE" \
        && docker exec "$CONTAINER_NAME" rm -rf /tmp/basebackup \
        && log "Base backup complete: $(du -h "$BASE_FILE" | cut -f1)" \
        || log "WARNING: Base backup failed"
    # Keep only 4 base backups (roughly 1 month)
    find "$BASEBACKUP_DIR" -name "base_*.tar.gz" -type f | sort | head -n -4 | xargs rm -f 2>/dev/null
else
    log "Skipping base backup (latest: $(basename "$LATEST_BASE"))"
fi

# -----------------------------------------------------------------------------
# 6. Retention — delete backups older than $RETENTION_DAYS days
# -----------------------------------------------------------------------------
log "Cleaning backups older than $RETENTION_DAYS days..."

DELETED_DUMPS=$(find "$DB_BACKUP_DIR" -name "*.dump" -mtime +$RETENTION_DAYS -delete -print | wc -l)
DELETED_SQLS=$(find "$DB_BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
DELETED_WALS=$(find "$WAL_BACKUP_DIR" -name "0*" -mtime +$RETENTION_DAYS -delete -print 2>/dev/null | wc -l)

log "Cleaned up: $DELETED_DUMPS .dump, $DELETED_SQLS .sql.gz, $DELETED_WALS WAL files"

# Also clean WAL files from the Docker volume that are older than retention
if docker volume inspect "$WAL_VOLUME" >/dev/null 2>&1; then
    docker run --rm -v "$WAL_VOLUME":/wal alpine sh -c \
        "find /wal -name '0*' -mtime +$RETENTION_DAYS -delete 2>/dev/null" || true
fi

# -----------------------------------------------------------------------------
# 7. Summary
# -----------------------------------------------------------------------------
TOTAL_BACKUPS=$(find "$DB_BACKUP_DIR" -name "*.dump" | wc -l)
TOTAL_SIZE=$(du -sh "$DB_BACKUP_DIR" | cut -f1)
WAL_SIZE=$(du -sh "$WAL_BACKUP_DIR" 2>/dev/null | cut -f1 || echo "0")

log "=== Backup complete ==="
log "  Database dumps: $TOTAL_BACKUPS backups, $TOTAL_SIZE total"
log "  WAL archive: $WAL_HOST_COUNT files, $WAL_SIZE"
log "  Retention: $RETENTION_DAYS days"
log "  Latest: $DUMP_FILE"
