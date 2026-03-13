# Quickstart Example — Build a simple web app with 3 agents in parallel

This example shows `agents-harness-teams` running 3 Claude Code workers in parallel
to build a simple FastAPI + Next.js todo app.

## Step 1: Install

```bash
pip install agents-harness-teams
```

## Step 2: Create your Phase doc

```bash
cat > PHASE-1.md << 'EOF'
# Phase 1 — Todo App MVP

## Task 1.1: Backend setup
Create a FastAPI app in backend/ with a single GET /todos and POST /todos endpoint.
Success criteria:
- backend/main.py exists
- GET /todos returns 200 with empty list
- POST /todos accepts {"title": string} and returns 201

## Task 1.2: Frontend setup  [parallel with 1.1]
Create a Next.js 14 app in frontend/ with a single page showing a list of todos.
Success criteria:
- frontend/ directory exists
- npm run dev starts on localhost:3000
- Page renders "Todo List" heading

## Task 1.3: Integration test  [depends on 1.1, 1.2]
Write an integration test that POST to backend, then checks frontend renders the todo.
Success criteria:
- tests/test_integration.py exists
- pytest passes
EOF
```

## Step 3: Initialize and run

```bash
# Initialize project from Phase doc
harness init \
  --goal "Build a simple todo web app with FastAPI backend and Next.js frontend" \
  --phase-doc PHASE-1.md

# Start the harness (spawns workers, monitors progress)
harness run

# In another terminal: watch progress
harness status
```

## What happens

```
T=0s    harness init reads PHASE-1.md → creates 3 tasks in SQLite
T=1s    harness run → Orchestrator reads dependency graph
        task_1_1: no deps → spawn Worker A (sonnet)
        task_1_2: no deps → spawn Worker B (sonnet) [parallel!]
        task_1_3: depends on 1.1 + 1.2 → blocked

T=5min  Worker A writes heartbeat
T=5min  Worker B writes heartbeat

T=12min Worker A finishes backend
        writes .harness/events/task_1_1_complete.json
        Watchdog reacts in <1s → verifies → marks task_1_1 done

T=18min Worker B finishes frontend
        writes .harness/events/task_1_2_complete.json
        Watchdog → marks task_1_2 done
        Orchestrator: both deps done → spawn Worker C for task_1_3

T=25min Worker C finishes integration test
        All tasks done → Phase 1 Complete!
        
✅ Notification: "Phase 1 done! 3 tasks completed in 25 minutes."
```

## vs. Single Agent (old way)

| | Single Agent | agents-harness-teams |
|--|--|--|
| Task 1.1 | 12 min | 12 min |
| Task 1.2 | 18 min (sequential after 1.1) | 18 min (parallel with 1.1) |
| Task 1.3 | 7 min | 7 min |
| **Total** | **37 min** | **25 min** |
| Context pollution | Accumulates all 3 tasks | Each task is isolated |
| If 1.1 hangs | You find out manually | Watchdog respawns after 30min |
