#!/usr/bin/env bash
# session-start.sh — Harness Session Start Hook
# Auto-loads task context at the beginning of a Claude Code session.
# Part of agents-harness-teams ECC-style session hooks.

set -euo pipefail

HARNESS_DIR=".harness"
CURRENT_TASK_FILE="${HARNESS_DIR}/current_task.txt"

echo "╔══════════════════════════════════════════╗"
echo "║   agents-harness-teams: Session Start     ║"
echo "╚══════════════════════════════════════════╝"

# Create heartbeats directory if it doesn't exist
mkdir -p "${HARNESS_DIR}/heartbeats"

# Check if we're inside a harness project
if [ ! -f "${HARNESS_DIR}/project.json" ]; then
    echo "[harness] No harness project found in current directory."
    echo "[harness] Run: harness init --goal 'your goal' --phase-doc PHASE-1.md"
    exit 0
fi

# Load project info
PROJECT_GOAL=$(python3 -c "import json; d=json.load(open('${HARNESS_DIR}/project.json')); print(d.get('goal','N/A'))" 2>/dev/null || echo "N/A")
echo "[harness] Project goal: ${PROJECT_GOAL:0:80}"

# Check if there's a current task
if [ ! -f "${CURRENT_TASK_FILE}" ]; then
    echo "[harness] No active task. Waiting for harness run to assign one."
    exit 0
fi

TASK_ID=$(cat "${CURRENT_TASK_FILE}" | tr -d '[:space:]')
echo "[harness] Active task: ${TASK_ID}"

# Load context.json for this task
CONTEXT_FILE="${HARNESS_DIR}/workers/${TASK_ID}/context.json"

if [ ! -f "${CONTEXT_FILE}" ]; then
    echo "[harness] Warning: No context.json found at ${CONTEXT_FILE}"
    exit 0
fi

# Print context summary
echo ""
echo "── Task Context ────────────────────────────"
python3 - "${CONTEXT_FILE}" <<'PYEOF'
import json, sys

path = sys.argv[1]
with open(path) as f:
    ctx = json.load(f)

print(f"  Task:     {ctx.get('task_id', 'unknown')}")
print(f"  Name:     {ctx.get('task_name', 'N/A')}")
print(f"  Model:    {ctx.get('model_tier', 'sonnet')}")

goal = ctx.get('goal', ctx.get('task_description', 'N/A'))
print(f"  Goal:     {str(goal)[:100]}")

criteria = ctx.get('success_criteria', [])
if isinstance(criteria, str):
    import json as j
    try:
        criteria = j.loads(criteria)
    except Exception:
        criteria = [criteria]
print(f"  Criteria: {len(criteria)} items")
for i, c in enumerate(criteria[:3], 1):
    print(f"    {i}. {str(c)[:80]}")
if len(criteria) > 3:
    print(f"    ... and {len(criteria) - 3} more")
PYEOF

echo "────────────────────────────────────────────"
echo ""
echo "[harness] Heartbeat dir: ${HARNESS_DIR}/heartbeats/"
echo "[harness] Write heartbeat: echo \$(date -u) > ${HARNESS_DIR}/heartbeats/${TASK_ID}.txt"
echo "[harness] Write completion: .harness/events/${TASK_ID}_complete.json"
echo ""
