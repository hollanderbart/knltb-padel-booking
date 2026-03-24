#!/usr/bin/env bash
# run_booking.sh — wordt aangeroepen door Home Assistant elke nacht 00:01
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/booking.log"
VENV="$SCRIPT_DIR/venv/bin/activate"

echo "$(date '+%Y-%m-%d %H:%M:%S') — Booking script gestart" >> "$LOG_FILE"

# Activeer venv
source "$VENV"

# Draai booking script, log output
# set -e is uitgeschakeld zodat exit 1 (geen slot beschikbaar) het script niet afbreekt
cd "$SCRIPT_DIR"
python booking.py >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

echo "$(date '+%Y-%m-%d %H:%M:%S') — Script klaar (exit $EXIT_CODE)" >> "$LOG_FILE"
exit $EXIT_CODE
