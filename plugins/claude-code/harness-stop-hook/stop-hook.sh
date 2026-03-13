#!/bin/bash
# ============================================================
# agents-harness-teams — Stop Hook
#
# Triggered when Claude Code tries to end a session.
# Pattern inspired by: ralph-wiggum (anthropics/claude-code)
#
# Behavior:
# 1. Check if a harness task is active (.harness/current_task.txt)
# 2. If no task → allow exit (exit 0)
# 3. If task found → check if complete.json was written
#    - Yes: exit 0 (allow exit, Watchdog will pick up)
#    - No: exit 1 + inject feedback (prevent exit, ask Claude to finish)
# ============================================================

set -euo pipefail

HARNESS_DIR=".harness"
CURRENT_TASK_FILE="${HARNESS_DIR}/current_task.txt"
EVENTS_DIR="${HARNESS_DIR}/events"
HEARTBEATS_DIR="${HARNESS_DIR}/heartbeats"

# Step 1: Check if harness task is active
if [[ ! -f "${CURRENT_TASK_FILE}" ]]; then
    # No active task — allow normal exit
    exit 0
fi

TASK_ID=$(cat "${CURRENT_TASK_FILE}" | tr -d '[:space:]')

if [[ -z "${TASK_ID}" ]]; then
    exit 0
fi

# Step 2: Update heartbeat before stopping
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${HEARTBEATS_DIR}/${TASK_ID}.txt"

# Step 3: Check if completion was already signaled
COMPLETE_FILE="${EVENTS_DIR}/${TASK_ID}_complete.json"

if [[ -f "${COMPLETE_FILE}" ]]; then
    # Task completion was properly signaled — allow exit
    echo "[harness-stop-hook] ✅ Task ${TASK_ID} completion verified. Allowing exit."
    exit 0
fi

# Step 4: Task NOT complete — block exit and inject feedback
# Read the success criteria from task context
CONTEXT_FILE="${HARNESS_DIR}/workers/${TASK_ID}/context.json"
CRITERIA=""
if [[ -f "${CONTEXT_FILE}" ]]; then
    # Extract success criteria with jq if available
    if command -v jq &>/dev/null; then
        CRITERIA=$(jq -r '.task_context.ancestry.task.success_criteria | join("\n- ")' "${CONTEXT_FILE}" 2>/dev/null || echo "")
    fi
fi

# Write feedback for Claude to read
FEEDBACK_FILE="${HARNESS_DIR}/workers/${TASK_ID}/stop_hook_feedback.txt"
cat > "${FEEDBACK_FILE}" << EOF
⚠️ [agents-harness-teams] Task ${TASK_ID} is NOT yet complete.

You attempted to end the session, but the completion signal has not been written.

Required before you can finish:
- ${CRITERIA}

MANDATORY NEXT STEPS:
1. Verify each success criterion is actually met
2. Fix anything that's not done
3. Write the completion signal:
   echo '{"task_id":"${TASK_ID}","status":"done","summary":"<one line>","artifacts":[],"timestamp":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}' > ${EVENTS_DIR}/${TASK_ID}_complete.json
4. Continue your work

Do NOT end the session until all criteria are verified.
EOF

echo "[harness-stop-hook] ❌ Task ${TASK_ID} incomplete. Blocking exit. Feedback written to ${FEEDBACK_FILE}."

# Exit 1 = tell Claude Code to continue (ralph-wiggum pattern)
# The feedback file content will be injected back to Claude
cat "${FEEDBACK_FILE}"
exit 1
