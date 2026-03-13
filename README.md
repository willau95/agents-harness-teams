# agents-harness-teams

> **Universal multi-agent harness for Claude Code and OpenClaw — install in seconds, run forever.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Status: Early Development](https://img.shields.io/badge/status-early%20development-orange.svg)]()

---

## The Problem

You're running Claude Code or OpenClaw to build something complex. You've seen these failures:

| Problem | What Happens |
|---------|-------------|
| **Linear Execution** | One agent does everything sequentially — slow, context blows up |
| **Silent Hangs** | Agent stops mid-task, no notification, you find out hours later |
| **"Telephone Game" Handoff** | Subagents only see the MD you passed, miss crucial context, produce broken output |
| **Context Pollution** | After 3 sessions, agent remembers "fix Redis bug" not "build LLaChat" |
| **No Recovery** | One failure = you restart everything manually |

## The Solution

`agents-harness-teams` wraps your existing Claude Code / OpenClaw setup with a **Conductor Layer** that:

1. **Decomposes** your goal into a Phase → Task tree with explicit success criteria
2. **Spawns** isolated Claude Code workers (fresh context per task, no pollution)
3. **Passes** a structured Goal Ancestry Chain to every worker (not just an MD)
4. **Watches** workers for hangs, auto-respawns on timeout
5. **Verifies** task completion against defined criteria before moving on
6. **Notifies** you only when a Phase completes (or something fails after 3 retries)

```
You set the goal. Harness runs the team. You review the results.
```

---

## Quick Start

```bash
pip install agents-harness-teams

# Initialize a project
cd your-project
harness init --goal "Build the frontend for MyApp: Landing Page + Dashboard" \
             --phase-doc PHASE-1.md

# Start the team
harness run

# Check progress
harness status
```

---

## Architecture Overview

```
User Goal
   │
   ▼
[Initializer]        ← Parses goal + phase doc → builds Task tree in SQLite
   │
   ▼
[Orchestrator]       ← Reads pending tasks, analyzes dependencies
   │
   ├──── spawn ────► [Worker: Task 1] ← fresh Claude Code session
   ├──── spawn ────► [Worker: Task 2]   each gets Goal Ancestry Chain
   └──── spawn ────► [Worker: Task 3]   (project → phase → task → criteria)
                          │
                          │ writes completion flag
                          ▼
[Watchdog Daemon]    ← detects completion via FSEvents (not polling!)
   │                   verifies success criteria
   │                   respawns on timeout (30min)
   └──── notify ──► You (when phase is done or 3 retries exhausted)
```

**State Storage:** SQLite (`.harness/state.db`) — zero external dependencies.  
**Worker Listener:** Local daemon — no Redis/cloud required for single-machine use.

---

## What's Borrowed (Not Reinvented)

| Concept | Source | How We Use It |
|---------|--------|---------------|
| Initializer/Executor split | [Anthropic Harness Blog](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | Init once, workers per task |
| Goal Ancestry Chain | [Paperclip](https://github.com/paperclipai/paperclip) | Full project→phase→task chain in every worker |
| Atomic task checkout | Paperclip | SQLite lock prevents duplicate worker pickup |
| Session Isolation | [Maestro](https://github.com/RunMaestro/Maestro) | Fresh Claude Code session per task |
| Stop Hook feedback loop | [ralph-wiggum](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum) | Hook intercepts stop, verifies, injects feedback if incomplete |
| Model tiering | [wshobson/agents](https://github.com/wshobson/agents) | Opus for planning, Sonnet for execution, Haiku for verification |
| Verification Loop | [everything-claude-code](https://github.com/affaan-m/everything-claude-code) | success_criteria auto-checked before task marked done |

---

## Status

🚧 **Early Development** — Architecture finalized, implementation in progress.

- [ ] v0.1 MVP: Sequential execution + Stop Hook + Watchdog
- [ ] v0.2: Parallel workers + dependency graph
- [ ] v0.3: OpenClaw Skill + Claude Code Plugin packaging
- [ ] v0.5: Multi-machine via Redis pub/sub

---

## Project Structure

```
agents-harness-teams/
├── harness/
│   ├── cli.py              # harness init / run / status / daemon
│   ├── initializer.py      # Parse goal → Task tree
│   ├── orchestrator.py     # Dependency analysis + worker spawning
│   ├── watchdog.py         # FSEvents listener + heartbeat + respawn
│   ├── verifier.py         # success_criteria validation
│   ├── state.py            # SQLite ORM
│   ├── models.py           # Project / Phase / Task / Worker
│   └── context_builder.py  # Goal Ancestry Chain JSON builder
├── plugins/
│   └── claude-code/
│       └── harness-stop-hook/  # Claude Code Stop Hook plugin
├── templates/
│   ├── project.md          # Fill in your project goal
│   └── task.md             # Task Card template
├── examples/
│   └── quickstart/
└── docs/
    ├── ARCHITECTURE.md
    └── WORKER-CONTRACT.md  # Worker interface spec
```

---

## Worker Contract

Every Claude Code worker receives a structured JSON context and must:

1. Write heartbeat to `.harness/heartbeats/{task_id}.txt` every 5 minutes
2. Write completion result to `.harness/events/{task_id}_complete.json` when done
3. Never declare completion unless all `success_criteria` are verifiably met

See [docs/WORKER-CONTRACT.md](docs/WORKER-CONTRACT.md) for full spec.

---

## Philosophy

> **The agent does the work. The harness ensures the work gets done.**

Single agents fail on long tasks not because they're incapable, but because they lack infrastructure:
- No way to hand off state between sessions
- No external verification of completion
- No recovery when something silently dies

`agents-harness-teams` provides that infrastructure, as a thin, installable layer over whatever agent you already use.

---

## Contributing

Architecture is documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).  
We're actively looking for contributors who use Claude Code or OpenClaw for complex projects.

---

## License

MIT — use it, fork it, build on it.
