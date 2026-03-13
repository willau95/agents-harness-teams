# agents-harness-teams — Full Implementation Specification
**Version:** 1.0 FINAL  
**Date:** 2026-03-13  
**Status:** Ready for implementation — THIS IS THE SINGLE SOURCE OF TRUTH

---

## 0. What You Are Building

`agents-harness-teams` is a **universal, open-source, pip-installable CLI** that gives Claude Code and OpenClaw users a professional multi-agent harness.

Install in seconds:
```bash
pip install agents-harness-teams
harness init --goal "Build my project" --phase-doc PHASE-1.md
harness run
```

**Core promise:** You set the goal. Harness runs the team. You review results.

---

## 1. Non-Negotiable Constraints

1. **Models: ONLY `claude-opus-4-6` and `claude-sonnet-4-6`** — no Haiku, no other models
2. **Zero external dependencies** — SQLite only (Python built-in), no Redis, no PostgreSQL
3. **Task Card format: Markdown** (B-option) — standard format, regex parseable, no LLM for parsing
4. **10-step flow is the Orchestrator's state machine** — not optional, hardcoded into the flow
5. **ECC skills/hooks MUST be imported** — not referenced, actually included in the repo

---

## 2. Model Configuration (REPLACE existing spawner.py MODEL_MAP)

```python
MODEL_MAP = {
    "opus": "claude-opus-4-6",     # Planning, architecture, logic-check, reporting
    "sonnet": "claude-sonnet-4-6", # All development/execution tasks
}

# Role → Model assignment
ROLE_MODELS = {
    "initializer": "opus",    # Parses goal, generates Phase/Task tree
    "planner": "opus",        # Writes施工图 Task Cards (Step 4)
    "logic_checker": "opus",  # Deep logic check (Step 5)
    "reviser": "sonnet",      # Fixes issues found in logic check (Step 6)
    "worker": "sonnet",       # All development execution (Step 8)
    "validator": "sonnet",    # Post-dev check (Step 9)
    "reporter": "sonnet",     # REPORT-N.md generation (Step 9)
    "orchestrator": "sonnet", # Dependency analysis, decision making
}
```

---

## 3. The 10-Step Flow (Core State Machine)

This is the SOUL of the harness. Every project, every phase, every task follows this cycle.
The Orchestrator enforces it. Workers cannot skip steps.

```
┌─────────────────────────────────────────────────────────────┐
│                   10-STEP PHASE CYCLE                        │
│                   (runs for EVERY Phase)                     │
└─────────────────────────────────────────────────────────────┘

Step 1: RECALL
  memory_recall("project context", "phase N", "previous results")
  → Orchestrator loads all relevant memories before proceeding

Step 2: READ MASTER DOC
  Read the Master Document (LLACHAT-DEV-MASTER.md or equivalent)
  → Extract the section relevant to current Phase

Step 3: EXTRACT PHASE CONTENT
  Pull Phase-specific requirements, constraints, references
  → Build Phase context object

Step 4: WRITE 施工图 (Task Cards)
  PLANNER Agent (Opus) generates a Phase MD with Task Cards
  Each Task Card MUST have: description + success_criteria + dependencies + model
  → Output: PHASE-N.md written to disk

Step 5: DEEP LOGIC CHECK  ← GATE: Cannot proceed without passing
  LOGIC_CHECKER Agent (Opus) verifies:
  - No contradictions with Master Doc
  - No internal dependency conflicts  
  - All success_criteria are measurable
  - No missing prerequisites
  → Outputs: LOGIC-CHECK-N.md with PASS/FAIL + issues list

Step 6: FIX ISSUES (only if Step 5 found issues)
  REVISER Agent (Sonnet) fixes all issues found in Step 5
  → Updates PHASE-N.md

Step 7: HUMAN APPROVAL ← GATE: Human must confirm before workers spawn
  Harness outputs: "Phase N plan ready. Review PHASE-N.md and type 'approve' to proceed."
  Waits for human input.
  → On approval: Phase N locked, no more changes

Step 8: DEVELOPMENT (parallel workers)
  For each Task Card in PHASE-N.md:
    → WORKER Agent (Sonnet) spawned with Goal Ancestry Chain
    → Workers run in parallel (respecting dependencies)
    → Each Worker writes heartbeat every 5min
    → Each Worker writes completion signal when ALL criteria met

Step 9: POST-DEV CHECK + REPORT
  VALIDATOR Agent (Sonnet): verifies all success_criteria actually pass
  REPORTER Agent (Sonnet): writes REPORT-N.md
  → REPORT-N.md contains: what was built, what passed, what failed, metrics

Step 10: NEXT PHASE
  Orchestrator reads REPORT-N.md
  → If all passed: trigger Step 1 of Phase N+1
  → If failures: back to Step 6 for the failed tasks
  → Human notified of Phase completion
```

**State machine implementation in `harness/phase_cycle.py`**

---

## 4. Task Card Format (Standard Markdown)

Every Phase MD must use this EXACT format for Task Cards. Regex parseable, human readable.

```markdown
## Task 1.1: Next.js Project Initialization

**depends:** none
**model:** sonnet

Initialize Next.js 14 App Router in frontend/ directory with Tailwind CSS v3.

**success_criteria:**
- frontend/ directory exists
- next.config.js contains `appDir: true`
- tailwind.config.js content includes `src/**/*.{ts,tsx}`
- `npm run dev` starts successfully on localhost:3000 returning HTTP 200
```

**Parser rules:**
- Task starts at `## Task N.M: <name>`
- `**depends:**` — comma-separated task IDs, or `none`
- `**model:**` — `opus` or `sonnet`
- Description = text between frontmatter and `**success_criteria:**`
- Success criteria = bullet list after `**success_criteria:**`
- Task ends at next `## Task` or end of file

**Implement in `harness/task_parser.py`**

---

## 5. everything-claude-code Integration

### 5.1 Clone and import ECC

```bash
# In the coding agent, run this to get ECC files:
git clone --depth 1 https://github.com/affaan-m/everything-claude-code /tmp/ecc-source
```

### 5.2 What to import (be selective)

From ECC, copy to `agents-harness-teams/`:

**Hooks (to `plugins/hooks/`):**
- `.claude/hooks/session-start.sh` → auto-loads context at session start
- `.claude/hooks/session-stop.sh` → auto-saves context + writes session summary
- Merge with our existing `stop-hook.sh` (don't replace, merge the features)

**Skills (to `skills/`):**
- `skills/verification-loop.md` → enforces check before marking done
- `skills/continuous-learning.md` → extracts patterns from sessions
- `skills/strategic-compact.md` → compresses context, prevents pollution
- `skills/iterative-retrieval.md` → progressive context loading
- `skills/autonomous-loops.md` → self-running loop patterns

**Agent definitions (to `agents/`):**
Copy any agent MD files from `.agents/skills/` that match these roles:
- planner, architect, code-reviewer, tdd-guide, doc-updater, security-reviewer

If ECC doesn't have exact matches, CREATE these agents based on the ECC pattern.

### 5.3 Harness-native agents (always create these)

Create `agents/` directory with these 6 agent definition files:

**`agents/planner.md`** (Opus)
```
You are the Harness Planner Agent.
Your job: given a project goal and master document, produce a Phase施工图 (PHASE-N.md)
with precise Task Cards in the standard harness format.
Rules:
- Every task must have measurable success_criteria (no vague terms)
- Dependencies must be explicit (no implicit ordering)
- Model must be opus for architecture/planning tasks, sonnet for execution tasks
- Maximum 15 tasks per phase
Output: PHASE-N.md in the standard Task Card format
```

**`agents/logic-checker.md`** (Opus)
```
You are the Harness Logic Checker Agent.
Your job: perform Step 5 of the 10-step flow — deep logic check on a Phase MD.
Check for:
1. Contradictions with the Master Document
2. Internal dependency conflicts (circular deps, missing deps)
3. Unmeasurable success_criteria ("works correctly" is NOT measurable)
4. Missing prerequisites (does Phase N depend on something Phase N-1 didn't deliver?)
5. Scope creep (tasks outside declared Phase scope)
6. Technical impossibilities

Output: LOGIC-CHECK-N.md with:
- VERDICT: PASS or FAIL
- ISSUES: list of specific problems found
- FIXES: suggested corrections for each issue
```

**`agents/coder.md`** (Sonnet)
```
You are a Harness Worker Agent executing a specific development task.
You operate under the agents-harness-teams Harness system.
Rules:
- Read your task context from context.json
- Write heartbeat every 5 minutes: echo $(date -u) > .harness/heartbeats/{task_id}.txt
- Write completion ONLY when ALL success_criteria are verified
- Completion signal: .harness/events/{task_id}_complete.json
- See WORKER-CONTRACT.md for full spec
```

**`agents/reviewer.md`** (Sonnet)
```
You are the Harness Reviewer Agent (Step 9 - Validator).
Your job: verify that all success_criteria for completed tasks are actually met.
For each task:
1. Read the success_criteria from PHASE-N.md
2. Verify each criterion (run commands, check files, make HTTP calls)
3. Output: VALIDATION-N.md with PASS/FAIL per criterion
Do not assume — verify empirically.
```

**`agents/reporter.md`** (Sonnet)
```
You are the Harness Reporter Agent (Step 9 - Reporter).
Your job: write REPORT-N.md after Phase N completes.
Template:
# REPORT-N: Phase N — [Phase Name]
## Summary: [one paragraph]
## Tasks Completed: [list with artifacts]
## Tests Passed: [list]
## Issues Found: [list, empty if none]
## Next Phase Prerequisites: [what Phase N+1 can now rely on]
## Metrics: duration, workers spawned, retries
```

**`agents/reviser.md`** (Sonnet)
```
You are the Harness Reviser Agent (Step 6).
Your job: fix issues identified in the Logic Check (LOGIC-CHECK-N.md).
Read LOGIC-CHECK-N.md → Fix each ISSUE in PHASE-N.md → Save updated PHASE-N.md.
Do not change tasks that were not flagged. Do not add new tasks.
```

---

## 6. Full Project Structure (Final)

```
agents-harness-teams/
├── README.md                         ← already exists, keep
├── pyproject.toml                    ← already exists, update
├── IMPLEMENTATION-SPEC.md            ← this file
│
├── harness/
│   ├── __init__.py
│   ├── cli.py                        ← IMPLEMENT: init/run/status/daemon
│   ├── models.py                     ← already done
│   ├── state.py                      ← already done
│   ├── context_builder.py            ← already done
│   ├── orchestrator.py               ← already done, ADD phase_cycle integration
│   ├── spawner.py                    ← UPDATE: remove haiku, 2 models only
│   ├── watchdog.py                   ← already done
│   ├── notifier.py                   ← already done
│   ├── task_parser.py                ← CREATE: parse Task Cards from MD
│   └── phase_cycle.py               ← CREATE: 10-step state machine
│
├── agents/                           ← CREATE ALL 6
│   ├── planner.md
│   ├── logic-checker.md
│   ├── coder.md
│   ├── reviewer.md
│   ├── reporter.md
│   └── reviser.md
│
├── skills/                           ← IMPORT FROM ECC + CREATE
│   ├── verification-loop.md          ← from ECC
│   ├── continuous-learning.md        ← from ECC
│   ├── strategic-compact.md          ← from ECC
│   ├── iterative-retrieval.md        ← from ECC
│   ├── autonomous-loops.md           ← from ECC
│   └── ten-step-flow.md              ← CREATE: documents the 10-step cycle
│
├── plugins/
│   └── claude-code/
│       ├── harness-stop-hook/        ← already done
│       │   ├── plugin.json
│       │   └── stop-hook.sh
│       └── harness-hooks/            ← CREATE: ECC-style session hooks
│           ├── plugin.json
│           ├── session-start.sh      ← from ECC: auto-load context
│           └── session-stop.sh       ← from ECC: auto-save + summary
│
├── templates/
│   ├── phase.md                      ← CREATE: template for writing Phase MDs
│   └── task-card.md                  ← CREATE: template for a single Task Card
│
├── examples/
│   └── quickstart/
│       └── README.md                 ← already exists
│
└── docs/
    ├── ARCHITECTURE.md               ← already exists
    ├── WORKER-CONTRACT.md            ← already exists
    ├── TEN-STEP-FLOW.md             ← CREATE: full documentation of 10 steps
    ├── MADNESS-ARMY-INTEGRATION.md  ← CREATE: how to use with agent-matrix-deploy
    └── EXTENDING.md                  ← CREATE: how to add new agent types
```

---

## 7. CLI Implementation (harness/cli.py)

### `harness init`

```python
@app.command()
def init(goal, phase_doc, context, project_dir):
    # 1. Create .harness/ directory
    # 2. Init SQLite (state.py)
    # 3. If phase_doc provided: parse Task Cards (task_parser.py) → create Phase + Task rows
    # 4. Else: spawn PLANNER agent (Opus) to decompose goal into tasks
    # 5. Write .harness/project.json (Goal Ancestry root)
    # 6. Print summary table (Rich)
```

### `harness run`

```python
@app.command()
def run(phase, dry_run):
    # 1. Start Watchdog daemon
    # 2. Load OrchestratorBrain
    # 3. Execute 10-step phase cycle (phase_cycle.py)
    #    → Steps 1-4 automatic
    #    → Step 5 logic check
    #    → Step 7 wait for human approval (stdin prompt)
    #    → Steps 8-9 worker execution
    # 4. Print live status (Rich Live)
```

### `harness status`

```python
@app.command()
def status(verbose):
    # Read SQLite → print Rich table:
    # Project | Phase | Task | Status | Worker | Duration | Retries
```

---

## 8. task_parser.py — Parse Phase MD to Task Cards

```python
import re
from dataclasses import dataclass

TASK_PATTERN = re.compile(
    r'^## Task (\d+\.\d+): (.+?)$'
    r'.*?\*\*depends:\*\* (.+?)$'
    r'.*?\*\*model:\*\* (.+?)$'
    r'(.*?)'
    r'\*\*success_criteria:\*\*\s*\n((?:- .+\n?)+)',
    re.MULTILINE | re.DOTALL
)

def parse_phase_md(filepath: str) -> list[TaskCard]:
    """Parse a Phase MD file into TaskCard objects."""
    content = Path(filepath).read_text()
    tasks = []
    # ... implementation
    return tasks
```

---

## 9. phase_cycle.py — 10-Step State Machine

```python
class PhaseCycle:
    """
    Enforces the 10-step development flow for each Phase.
    This is the non-negotiable core of agents-harness-teams.
    """
    
    async def run_phase(self, phase_id: str):
        phase = self.db.get_phase(phase_id)
        
        # Step 1: Recall
        await self.step_recall(phase)
        
        # Step 2-3: Read master doc + extract
        context = await self.step_extract_context(phase)
        
        # Step 4: Write施工图 (skip if phase_doc already provided)
        if not phase.tasks:
            await self.step_write_task_cards(phase, context)
        
        # Step 5: Logic check ← GATE
        logic_result = await self.step_logic_check(phase)
        
        # Step 6: Fix if needed
        if logic_result.verdict == "FAIL":
            await self.step_fix_issues(phase, logic_result)
            logic_result = await self.step_logic_check(phase)  # Re-check
        
        # Step 7: Human approval ← GATE
        await self.step_await_human_approval(phase)
        
        # Step 8: Development (parallel workers)
        await self.step_run_workers(phase)
        
        # Step 9: Post-dev check + report
        await self.step_validate_and_report(phase)
        
        # Step 10: Trigger next phase
        await self.step_trigger_next_phase(phase)
```

---

## 10. Madness Army Integration Layer

Create `harness/integrations/madness_army.py`:

```python
class MadnessArmyRelay:
    """
    Integrates with Madness Army's relay daemon (port 59000).
    Allows distributing tasks to remote machines in the fleet.
    No Redis needed — uses existing relay HTTP API.
    """
    
    def __init__(self, relay_urls: list[str]):
        # e.g. ["http://192.168.1.2:59000", "http://192.168.1.3:59000"]
        self.relays = relay_urls
    
    async def dispatch_task(self, task_id: str, context: dict, target_machine: str):
        """POST task to a remote machine's relay /blueprint/dispatch endpoint."""
        # Implementation
    
    async def check_worker_status(self, machine_url: str, task_id: str) -> dict:
        """GET worker status from remote machine's relay."""
        # Implementation
    
    async def get_available_machine(self) -> str:
        """Find the least loaded machine in the fleet."""
        # Check each relay's /system/stats endpoint
        # Return URL of machine with most capacity
```

Usage:
```bash
# Single machine (default)
harness run

# Madness Army fleet
harness run --fleet "192.168.1.2:59000,192.168.1.3:59000,192.168.1.4:59000"
```

Create `docs/MADNESS-ARMY-INTEGRATION.md` with:
- Prerequisites (relay running on each machine)
- How task distribution works
- How to add new machines to the fleet
- Monitoring the fleet during a run

---

## 11. skills/ten-step-flow.md

Create this skill file:

```markdown
# Skill: Ten-Step Development Flow

## Purpose
The universal development methodology used by agents-harness-teams.
Applies to ALL phases of ANY project.

## The 10 Steps

| Step | Name | Agent | Model | Gate? |
|------|------|-------|-------|-------|
| 1 | Memory Recall | Orchestrator | sonnet | No |
| 2 | Read Master Doc | Orchestrator | sonnet | No |
| 3 | Extract Phase Content | Orchestrator | sonnet | No |
| 4 | Write 施工图 (Task Cards) | Planner | opus | No |
| 5 | Deep Logic Check | Logic Checker | opus | YES — must PASS |
| 6 | Fix Issues | Reviser | sonnet | No (only if Step 5 failed) |
| 7 | Human Approval | — | — | YES — human must approve |
| 8 | Development | Workers | sonnet | No |
| 9 | Post-Dev Check + Report | Validator + Reporter | sonnet | No |
| 10 | Next Phase | Orchestrator | sonnet | No |

## Usage
This flow is enforced by phase_cycle.py. Workers cannot be spawned until Steps 5 and 7 pass.
```

---

## 12. Testing

After implementation, verify end-to-end:

```bash
cd /tmp/test-harness-project
mkdir test-project && cd test-project

cat > PHASE-1.md << 'EOF'
## Task 1.1: Create hello world

**depends:** none
**model:** sonnet

Create a Python file hello.py that prints "Hello from agents-harness-teams!"

**success_criteria:**
- hello.py exists in current directory
- `python hello.py` outputs "Hello from agents-harness-teams!"
EOF

harness init --goal "Test harness end-to-end" --phase-doc PHASE-1.md
harness status
harness run --dry-run
```

Expected output:
```
✅ Project initialized
✅ 1 task loaded from PHASE-1.md
✅ Dependency graph built
[dry-run] Would spawn: Worker(task_1_1, model=claude-sonnet-4-6)
```

---

## 13. Commit Message

When done, use:
```
feat: full implementation v0.1.0

- 10-step flow state machine (phase_cycle.py)
- Task Card MD parser (task_parser.py)  
- 6 harness agents (planner/logic-checker/coder/reviewer/reporter/reviser)
- 5 skills imported from ECC + 1 harness-native (ten-step-flow)
- ECC session hooks (session-start.sh / session-stop.sh)
- Model config: claude-opus-4-6 + claude-sonnet-4-6 only
- Madness Army relay integration layer
- CLI: init/run/status/daemon fully implemented
- End-to-end test passing
```

Push to: https://github.com/willau95/agents-harness-teams (branch: main)
