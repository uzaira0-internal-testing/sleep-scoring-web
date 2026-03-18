#!/bin/bash
# Delegates to the unified backup script at ~/backups/sleep-scoring/backup.sh
# This wrapper exists so that references to this path still work.
exec /home/uzair/backups/sleep-scoring/backup.sh "$@"
