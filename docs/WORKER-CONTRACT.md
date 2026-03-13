# WORKER-CONTRACT.md
> **Every Claude Code Worker spawned by agents-harness-teams MUST follow this contract.**
> Violating the contract = Watchdog will kill and respawn you.

---

## The Contract in One Paragraph

You are a Worker Agent. You receive a task with explicit success criteria. You do the work. You write a heartbeat every 5 minutes. When ALL success criteria are met, you write a completion signal. You do NOT end your session until the completion signal is written.

---

## 1. What You Receive (Input)

You receive a `context.json` injected as your initial prompt. It contains:

```json
{
  "harness_version": "0.1.0",
  "task_context": {
    "task_id": "task_1_1",
    "task_name": "Next.js project initialization",
    "ancestry": {
      "project": {
        "goal": "Build LLaChat Platform — AI Agent's LinkedIn",
        "tech_context": "Next.js 14, Tailwind CSS, FastAPI backend"
      },
      "phase": {
        "objective": "Build Phase 1 Frontend MVP",
        "prerequisites_done": ["Phase 0: Backend deployed at llachat-backend-production.up.railway.app"]
      },
      "task": {
        "description": "Initialize Next.js 14 App Router in frontend/ directory...",
        "success_criteria": [
          "frontend/ directory exists",
          "next.config.js has appDir: true",
          "npm run dev starts on localhost:3000 with HTTP 200"
        ],
        "model_tier": "sonnet"
      }
    },
    "worker_instructions": "..."
  }
}
```

---

## 2. What You Must Do (Mandatory Protocol)

### 2.1 Heartbeat (every 5 minutes)
```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .harness/heartbeats/task_1_1.txt
```
If you don't write this, Watchdog will kill you after 30 minutes.

### 2.2 Completion Signal (when ALL criteria are met)
```bash
cat > .harness/events/task_1_1_complete.json << 'EOF'
{
  "task_id": "task_1_1",
  "status": "done",
  "summary": "Initialized Next.js 14 App Router in frontend/, Tailwind CSS configured, dev server verified on localhost:3000",
  "artifacts": [
    "frontend/package.json",
    "frontend/next.config.js",
    "frontend/tailwind.config.js",
    "frontend/src/app/page.tsx"
  ],
  "timestamp": "2026-03-13T12:00:00Z"
}
EOF
```

### 2.3 Blocked Signal (if you cannot proceed)
```bash
cat > .harness/events/task_1_1_blocked.json << 'EOF'
{
  "task_id": "task_1_1",
  "status": "blocked",
  "reason": "Cannot proceed: task_1_0 (Redis fix) must complete first",
  "timestamp": "2026-03-13T12:00:00Z"
}
EOF
```

---

## 3. What You Must NOT Do

- ❌ Do NOT end the session before writing completion signal
- ❌ Do NOT write completion signal unless ALL success_criteria are actually met
- ❌ Do NOT modify files outside the declared `artifacts` scope unless necessary
- ❌ Do NOT spawn sub-agents without notifying Orchestrator via event file

---

## 4. Success Criteria Verification Checklist

Before writing your completion signal, verify each criterion:

1. Read each criterion from your `context.json`
2. Verify it's actually true (run tests, check files exist, make HTTP calls if needed)
3. Only after ALL pass → write completion signal

**Example verification for Task 1.1:**
```bash
# Check 1: frontend/ exists
ls frontend/ || echo "FAIL: frontend/ missing"

# Check 2: next.config.js correct
grep -q "appDir: true" frontend/next.config.js || echo "FAIL: appDir not set"

# Check 3: dev server starts
cd frontend && npm run dev &
sleep 5
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 | grep -q 200 || echo "FAIL: dev server not 200"
```

---

## 5. File Structure Contract

```
.harness/
├── current_task.txt          ← your task_id (written by Spawner, you read it)
├── workers/
│   └── task_1_1/
│       ├── context.json      ← your input (Goal Ancestry Chain)
│       └── stop_hook_feedback.txt  ← written by Stop Hook if you try to exit early
├── heartbeats/
│   └── task_1_1.txt         ← you write this every 5 min
└── events/
    ├── task_1_1_complete.json   ← you write this when done ✅
    ├── task_1_1_blocked.json    ← you write this if blocked ⚠️
    └── task_1_1_failed.json     ← you write this if truly failed ❌
```

---

## 6. Summary (tldr for Claude)

```
1. Read context.json → understand your task
2. Every 5 min: echo timestamp > .harness/heartbeats/task_1_1.txt
3. Do the work
4. Verify ALL success_criteria are actually true
5. Write .harness/events/task_1_1_complete.json
6. Only then: end session
```
