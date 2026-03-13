#!/usr/bin/env bash
# session-stop.sh — Harness Session Stop Hook
# Auto-saves session summary when a Claude Code session ends.
# Part of agents-harness-teams ECC-style session hooks.

set -euo pipefail

HARNESS_DIR=".harness"
CURRENT_TASK_FILE="${HARNESS_DIR}/current_task.txt"
SESSIONS_DIR="${HARNESS_DIR}/sessions"
EVENTS_DIR="${HARNESS_DIR}/events"

# Create sessions directory
mkdir -p "${SESSIONS_DIR}"

TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
SESSION_END=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Get current task ID
if [ ! -f "${CURRENT_TASK_FILE}" ]; then
    # No active task — write generic session summary
    SUMMARY_FILE="${SESSIONS_DIR}/session_${TIMESTAMP}.txt"
    cat > "${SUMMARY_FILE}" << EOF
session_end: ${SESSION_END}
task_id: none
completion_signal: false
status: no active task
notes: Session ended without an active task assigned by harness.
EOF
    echo "[harness] Session summary written: ${SUMMARY_FILE}"
    exit 0
fi

TASK_ID=$(cat "${CURRENT_TASK_FILE}" | tr -d '[:space:]')
SUMMARY_FILE="${SESSIONS_DIR}/${TASK_ID}_${TIMESTAMP}.txt"

# Check if completion signal was written
COMPLETION_SIGNAL="${EVENTS_DIR}/${TASK_ID}_complete.json"
if [ -f "${COMPLETION_SIGNAL}" ]; then
    COMPLETION_WRITTEN="true"
    COMPLETION_STATUS=$(python3 -c "import json; d=json.load(open('${COMPLETION_SIGNAL}')); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
    COMPLETION_SUMMARY=$(python3 -c "import json; d=json.load(open('${COMPLETION_SIGNAL}')); print(d.get('summary',''))" 2>/dev/null || echo "")
else
    COMPLETION_WRITTEN="false"
    COMPLETION_STATUS="incomplete"
    COMPLETION_SUMMARY="Session ended without writing completion signal."
fi

# Write session summary
cat > "${SUMMARY_FILE}" << EOF
session_end: ${SESSION_END}
task_id: ${TASK_ID}
completion_signal: ${COMPLETION_WRITTEN}
status: ${COMPLETION_STATUS}
summary: ${COMPLETION_SUMMARY}
EOF

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   agents-harness-teams: Session End       ║"
echo "╚══════════════════════════════════════════╝"
echo "[harness] Task:             ${TASK_ID}"
echo "[harness] Completion:       ${COMPLETION_WRITTEN}"
echo "[harness] Status:           ${COMPLETION_STATUS}"
echo "[harness] Session summary:  ${SUMMARY_FILE}"

if [ "${COMPLETION_WRITTEN}" = "false" ]; then
    echo ""
    echo "[harness] ⚠  WARNING: Completion signal not written."
    echo "[harness]    If the task is done, write:"
    echo "[harness]    echo '{\"task_id\":\"${TASK_ID}\",\"status\":\"done\",\"summary\":\"...\",\"artifacts\":[],\"timestamp\":\"${SESSION_END}\"}' > ${EVENTS_DIR}/${TASK_ID}_complete.json"
fi

echo ""
