# Architecture — agents-harness-teams

> Full design document: see [AGENTS-HARNESS-TEAMS-DESIGN.md](../design/AGENTS-HARNESS-TEAMS-DESIGN.md) (internal, not in repo)

---

## Core Principles

1. **Zero external dependencies** — SQLite only, no Redis/PostgreSQL required
2. **Works with existing tools** — wraps Claude Code / OpenClaw, doesn't replace them
3. **Event-driven, not heartbeat** — FSEvents on flag files, not 5-second polling
4. **Goal Ancestry Chain** — every Worker knows the full project→phase→task context
5. **Session isolation** — each task gets a fresh Claude Code session (no context pollution)

---

## System Overview

```
User Input (Goal)
        │
        ▼
 [Initializer]        ← One-time: parses Goal → SQLite Task tree
        │
        ▼
 [Orchestrator]       ← Reads pending tasks, analyzes dependencies
        │
   ┌────┴─────┐
   ▼          ▼
[Worker 1] [Worker 2] ← Parallel Claude Code sessions, isolated context
   │          │          each has: task_id + Goal Ancestry Chain + criteria
   │          │
   └────┬─────┘
        │ flag files written to .harness/events/
        ▼
 [Watchdog Daemon]    ← FSEvents listener, heartbeat monitor, respawner
        │
        ▼
 [User Notification]  ← Only when Phase done or max retries hit
```

---

## State Machine

```
Task States:
  pending → running → done
  pending → blocked     (dependency not met)
  running → hung        (30min no heartbeat)
  running → failed      (Worker wrote failed.json)
  hung → pending        (Watchdog respawns, retry_count++)
  failed → pending      (if retry_count < max_retries)
  failed → FATAL        (retry_count >= max_retries, notify user)
```

---

## Key Design Decisions

### Q1: Task State → SQLite
- Zero external deps: bundled with Python 3
- Portable: `.harness/state.db` travels with the project
- Upgradeable: SQLAlchemy ORM, swap PostgreSQL URL for multi-machine

### Q2: Worker Listener → Local Daemon
- Runs on same machine as Claude Code
- Uses `watchdog` library (Python) for FSEvents — reacts in <50ms
- No polling, no Redis, no cloud
- Optional Redis pub/sub upgrade for multi-machine (v0.5)

---

## What's Borrowed

| Pattern | Source |
|---------|--------|
| Initializer/Executor split | [Anthropic Harness Blog](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) |
| Goal Ancestry Chain | [Paperclip](https://github.com/paperclipai/paperclip) |
| Session Isolation | [Maestro](https://github.com/RunMaestro/Maestro) |
| Stop Hook feedback loop | [ralph-wiggum](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum) |
| Model tiering | [wshobson/agents](https://github.com/wshobson/agents) |
| Verification Loop | [everything-claude-code](https://github.com/affaan-m/everything-claude-code) |
