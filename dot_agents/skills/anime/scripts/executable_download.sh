#!/usr/bin/env bash
# rqbit download wrapper with queue management
# Usage: download.sh <magnet_url> <output_dir> [log_file]

set -euo pipefail

MAGNET="${1:?Usage: $0 <magnet> <output_dir>}"
OUTPUT_DIR="${2:?Usage: $0 <magnet> <output_dir>}"
LOG_FILE="${3:-/tmp/rqbit-$(date +%s).log}"
PID_FILE="${4:-}"

mkdir -p "$OUTPUT_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

echo "[$(date '+%H:%M:%S')] Starting download..." | tee -a "$LOG_FILE"
echo "  Output: $OUTPUT_DIR" | tee -a "$LOG_FILE"

# Run rqbit with exit-on-finish
rqbit download \
  -o "$OUTPUT_DIR" \
  -e \
  --overwrite \
  "$MAGNET" >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%H:%M:%S')] Download completed successfully" | tee -a "$LOG_FILE"
else
    echo "[$(date '+%H:%M:%S')] Download FAILED (exit code: $EXIT_CODE)" | tee -a "$LOG_FILE"
fi

# Cleanup PID file if exists
[ -n "$PID_FILE" ] && rm -f "$PID_FILE"

exit $EXIT_CODE