# The Ten-Step Development Flow

The universal methodology enforced by `agents-harness-teams` for every Phase of every project.

---

## Overview

```
Step 1:  RECALL          — Load project context
Step 2:  READ MASTER DOC — Load project documentation  
Step 3:  EXTRACT CONTEXT — Pull Phase-specific requirements
Step 4:  WRITE TASK CARDS— Planner generates PHASE-N.md
Step 5:  LOGIC CHECK ← GATE (must PASS)
Step 6:  FIX ISSUES      — Reviser applies fixes (if Step 5 failed)
Step 7:  HUMAN APPROVAL ← GATE (human must type "approve")
Step 8:  DEVELOPMENT     — Workers run in parallel
Step 9:  VALIDATE+REPORT — Validator + Reporter
Step 10: NEXT PHASE      — Trigger Phase N+1
```

**Two HARD GATES:** Steps 5 and 7. Workers cannot spawn until both pass.

---

## Step-by-Step Reference

### Step 1: RECALL
**Agent:** Orchestrator | **Model:** sonnet | **Gate:** No

The Orchestrator loads all relevant context before taking any action:
- Project goal and constraints
- Completed tasks from previous phases
- Any stored patterns or lessons learned

This prevents the Orchestrator from making decisions without full context.

---

### Step 2: READ MASTER DOC
**Agent:** Orchestrator | **Model:** sonnet | **Gate:** No

If a Master Document exists (e.g., `MASTER.md`, architecture spec), the Orchestrator reads
the relevant Phase section. This ensures that task generation is grounded in the overall
project spec, not just the goal statement alone.

---

### Step 3: EXTRACT PHASE CONTENT
**Agent:** Orchestrator | **Model:** sonnet | **Gate:** No

The Orchestrator extracts Phase-specific requirements and constraints from the Master Doc
and builds a Phase context object: what this Phase must deliver, what it can rely on from
previous phases, and what the next phase will need.

---

### Step 4: WRITE TASK CARDS (施工图)
**Agent:** Planner | **Model:** opus | **Gate:** No

The Planner Agent (Opus) generates a `PHASE-N.md` file containing precise Task Cards.

**Every Task Card must have:**
- Unique ID (e.g., `1.1`, `1.2`)
- Explicit dependencies (`none` or task IDs)
- Model assignment (`opus` for architecture, `sonnet` for execution)
- Description of what to do
- Measurable `success_criteria`

If `--phase-doc` was provided to `harness init`, this step is skipped (tasks already exist).

---

### Step 5: DEEP LOGIC CHECK ← GATE
**Agent:** Logic Checker | **Model:** opus | **Gate:** **YES — must PASS**

The Logic Checker Agent (Opus) verifies the Phase plan for:
1. Contradictions with the Master Document
2. Circular or missing dependencies
3. Unmeasurable success criteria (`"works correctly"` = FAIL)
4. Missing prerequisites from previous phases
5. Scope creep (tasks outside declared Phase scope)
6. Technical impossibilities

**Output:** `LOGIC-CHECK-N.md` with `VERDICT: PASS | FAIL` and detailed issues list.

**Why this gate exists:** Planning errors are cheap to fix before workers spawn. After workers
start, fixing a fundamentally flawed plan is expensive and causes cascading failures.

---

### Step 6: FIX ISSUES
**Agent:** Reviser | **Model:** sonnet | **Gate:** No (only runs if Step 5 FAIL)

The Reviser Agent reads `LOGIC-CHECK-N.md` and applies each suggested fix to `PHASE-N.md`.

Rules:
- Only modify flagged tasks
- Do not add new tasks
- Do not change ordering unless fixing a dependency issue

After Step 6, the flow loops back to Step 5 for re-check (maximum 3 cycles).

---

### Step 7: HUMAN APPROVAL ← GATE
**Agent:** None | **Model:** None | **Gate:** **YES — human must approve**

The harness prints the task summary and waits for the human to type `approve`.

```
  Tasks to be executed (3 total):
    • task_1_1 — Initialize project (model: sonnet)
    • task_1_2 — Create API (model: sonnet) [depends: 1.1]
    • task_1_3 — Write tests (model: sonnet) [depends: 1.2]

  Type 'approve' and press Enter to proceed:
  >
```

**Why this gate exists:** Humans must remain in the loop before computation-heavy work begins.
This is the last checkpoint before workers spawn. After approval, the plan is locked.

---

### Step 8: DEVELOPMENT
**Agent:** Workers | **Model:** sonnet | **Gate:** No

For each Task Card in `PHASE-N.md`:
- A Worker Agent (Sonnet) is spawned in an isolated session
- Workers run in **parallel** (respecting dependency order)
- Each Worker reads `context.json` from `.harness/workers/{task_id}/`
- Workers write heartbeats every 5 minutes
- Workers write completion signals when all criteria are verified

Workers cannot spawn until Steps 5 AND 7 have passed.

---

### Step 9: POST-DEV CHECK + REPORT
**Agent:** Validator + Reporter | **Model:** sonnet | **Gate:** No

Two sub-agents run in sequence:

**Validator:** Verifies that all `success_criteria` are actually met — empirically.
- Runs commands, checks files, makes HTTP calls
- Outputs `VALIDATION-N.md` with PASS/FAIL per criterion

**Reporter:** Writes `REPORT-N.md` documenting:
- What was built
- What passed / failed
- Duration, workers spawned, retries
- What Phase N+1 can rely on

---

### Step 10: NEXT PHASE
**Agent:** Orchestrator | **Model:** sonnet | **Gate:** No

The Orchestrator reads `REPORT-N.md`:
- If all tasks passed → trigger Step 1 of Phase N+1
- If some tasks failed → loop back to Step 6 for failed tasks
- If project has no more phases → mark project COMPLETE

---

## Implementation

The 10-step flow is implemented in `harness/phase_cycle.py` as the `PhaseCycle` class.

```python
from harness.phase_cycle import PhaseCycle

cycle = PhaseCycle(project_id="proj_abc123", dry_run=False)
await cycle.run_phase("phase_1")
```

Or via the CLI:

```bash
harness run               # Run next pending phase
harness run --phase phase_1  # Run specific phase
harness run --dry-run     # Preview without spawning workers
```

---

## FAQ

**Q: Can I skip the human approval gate?**  
A: No. This is a non-negotiable safety mechanism. In `--dry-run` mode it auto-approves for testing.

**Q: What if the Logic Check keeps failing?**  
A: After 3 fix cycles, the harness halts and asks for manual intervention. Review `LOGIC-CHECK-N.md`.

**Q: Can workers run on remote machines?**  
A: Yes — use Madness Army integration: `harness run --fleet "IP1:59000,IP2:59000"`. See `docs/MADNESS-ARMY-INTEGRATION.md`.
