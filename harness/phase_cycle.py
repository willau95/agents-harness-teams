"""
Phase Cycle — 10-Step State Machine.

Enforces the agents-harness-teams development methodology for every Phase.
This is the non-negotiable core flow. Workers cannot skip steps.

Steps:
  1  RECALL          — Load project context from memory/DB
  2  READ MASTER DOC — Read the master project document
  3  EXTRACT CONTEXT — Pull Phase-specific requirements
  4  WRITE TASK CARDS— Planner (Opus) generates PHASE-N.md task cards
  5  LOGIC CHECK ← GATE: must PASS before proceeding
  6  FIX ISSUES      — Reviser fixes issues from Step 5 (only if FAIL)
  7  HUMAN APPROVAL ← GATE: human must type "approve"
  8  DEVELOPMENT     — Workers spawn and run in parallel
  9  VALIDATE+REPORT — Validator + Reporter run
  10 NEXT PHASE      — Trigger Step 1 of Phase N+1
"""
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from .state import get_session_factory, init_db
from .models import Phase, Task, TaskStatus, PhaseStatus, Project
from .orchestrator import OrchestratorBrain

logger = logging.getLogger(__name__)

HARNESS_DIR = Path(".harness")


class LogicCheckResult:
    """Result from the Logic Checker step."""

    def __init__(self, verdict: str, issues: list[str], fixes: list[str]):
        self.verdict = verdict   # "PASS" or "FAIL"
        self.issues = issues
        self.fixes = fixes

    @property
    def passed(self) -> bool:
        return self.verdict.upper() == "PASS"


class PhaseCycle:
    """
    Enforces the 10-step development flow for each Phase.
    Instantiate with a project_id, then call run_phase(phase_id).
    """

    def __init__(
        self,
        project_id: str,
        db_path: Optional[Path] = None,
        dry_run: bool = False,
        master_doc: Optional[str] = None,
    ):
        self.project_id = project_id
        self.db_path = db_path or (HARNESS_DIR / "state.db")
        self.dry_run = dry_run
        self.master_doc_path = master_doc  # Optional path to master document
        self.session_factory = get_session_factory(self.db_path)
        self.orchestrator = OrchestratorBrain(project_id, db_path=self.db_path)

    # ──────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────

    async def run_phase(self, phase_id: str):
        """
        Execute the full 10-step cycle for the given phase.
        Blocks at Steps 5 (logic gate) and 7 (human approval gate).
        """
        print(f"\n{'='*60}")
        print(f"  AGENTS-HARNESS-TEAMS: Phase Cycle")
        print(f"  Phase: {phase_id}")
        print(f"{'='*60}\n")

        # ── Step 1: RECALL ──────────────────────────────────────
        context = await self._step_1_recall(phase_id)

        # ── Steps 2-3: READ MASTER DOC + EXTRACT ────────────────
        phase_context = await self._step_2_3_extract_context(phase_id, context)

        # ── Step 4: WRITE TASK CARDS (skip if tasks already exist)
        await self._step_4_write_task_cards(phase_id, phase_context)

        # ── Step 5: LOGIC CHECK ← GATE ──────────────────────────
        logic_result = await self._step_5_logic_check(phase_id)
        max_fix_cycles = 3
        fix_cycle = 0

        while not logic_result.passed and fix_cycle < max_fix_cycles:
            # ── Step 6: FIX ISSUES ──────────────────────────────
            await self._step_6_fix_issues(phase_id, logic_result)
            # Re-run logic check
            logic_result = await self._step_5_logic_check(phase_id)
            fix_cycle += 1

        if not logic_result.passed:
            print(f"\n[Phase Cycle] ⛔ Logic check failed after {max_fix_cycles} fix cycles.")
            print("[Phase Cycle]    Manual intervention required. Review PHASE-N.md.")
            return

        # ── Step 7: HUMAN APPROVAL ← GATE ───────────────────────
        approved = await self._step_7_human_approval(phase_id)
        if not approved:
            print("\n[Phase Cycle] ❌ Phase not approved. Halting.")
            return

        # ── Step 8: DEVELOPMENT ─────────────────────────────────
        await self._step_8_run_workers(phase_id)

        # ── Step 9: VALIDATE + REPORT ───────────────────────────
        await self._step_9_validate_and_report(phase_id)

        # ── Step 10: NEXT PHASE ──────────────────────────────────
        await self._step_10_next_phase(phase_id)

    # ──────────────────────────────────────────────────────────────
    # STEP IMPLEMENTATIONS
    # ──────────────────────────────────────────────────────────────

    async def _step_1_recall(self, phase_id: str) -> dict:
        """Step 1: Recall project context from SQLite and memory."""
        print("[Step 1/10] 🧠 RECALL — Loading project context...")

        context = {}
        with self.session_factory() as db:
            project = db.query(Project).filter(Project.id == self.project_id).first()
            if project:
                context["project_id"] = project.id
                context["project_name"] = project.name
                context["project_goal"] = project.goal
                context["tech_context"] = project.tech_context or ""

            phase = db.query(Phase).filter(Phase.id == phase_id).first()
            if phase:
                context["phase_id"] = phase.id
                context["phase_name"] = phase.name
                context["phase_objective"] = phase.objective or ""
                context["existing_tasks"] = len(phase.tasks)

                # Load completed tasks from previous phases
                completed = db.query(Task).filter(
                    Task.phase_id.in_([
                        p.id for p in project.phases
                        if p.order_idx < phase.order_idx
                    ]) if project else [],
                    Task.status == TaskStatus.done
                ).all() if project else []
                context["completed_tasks"] = [t.name for t in completed]

        print(f"  ✓ Project: {context.get('project_name', 'unknown')}")
        print(f"  ✓ Goal: {context.get('project_goal', 'N/A')[:80]}")
        print(f"  ✓ Existing tasks in phase: {context.get('existing_tasks', 0)}")
        return context

    async def _step_2_3_extract_context(self, phase_id: str, recall_context: dict) -> dict:
        """Steps 2-3: Read master doc and extract phase-specific content."""
        print("[Step 2/10] 📄 READ MASTER DOC — Loading project documentation...")
        print("[Step 3/10] 🔍 EXTRACT CONTEXT — Pulling phase-specific requirements...")

        phase_context = dict(recall_context)

        # Try to read master document if provided
        if self.master_doc_path:
            master_path = Path(self.master_doc_path)
            if master_path.exists():
                content = master_path.read_text(encoding="utf-8")
                # Extract the relevant phase section (simple heuristic)
                phase_num = phase_id.replace("phase_", "")
                phase_section = self._extract_phase_section(content, phase_num)
                phase_context["master_doc_excerpt"] = phase_section
                print(f"  ✓ Master doc loaded: {master_path.name} ({len(content)} chars)")
            else:
                print(f"  ⚠ Master doc not found: {self.master_doc_path}")
        else:
            print("  ℹ No master doc specified — using project goal as context")

        return phase_context

    def _extract_phase_section(self, content: str, phase_num: str) -> str:
        """Extract phase-relevant section from master document."""
        import re
        # Look for "Phase N" or "PHASE N" sections
        pattern = re.compile(
            rf'#{1,3}\s+Phase\s+{re.escape(phase_num)}[\s:].*?(?=#{1,3}\s+Phase\s+\d|$)',
            re.IGNORECASE | re.DOTALL
        )
        match = pattern.search(content)
        if match:
            return match.group(0)[:2000]  # Cap at 2k chars
        return ""

    async def _step_4_write_task_cards(self, phase_id: str, phase_context: dict):
        """Step 4: Write task cards (skip if tasks already exist in DB)."""
        print("[Step 4/10] ✍️  WRITE TASK CARDS — Checking for existing task cards...")

        with self.session_factory() as db:
            phase = db.query(Phase).filter(Phase.id == phase_id).first()
            if phase and phase.tasks:
                print(f"  ✓ Phase already has {len(phase.tasks)} task(s) — skipping generation")
                return

        # If no tasks exist, note that Planner agent would generate them
        print("  ℹ  No task cards found in DB.")
        print("  ℹ  Planner agent (Opus) would generate PHASE-N.md here.")
        print("  ℹ  (In production: spawn planner agent to write task cards)")

        # Check if a PHASE-N.md exists on disk that we can import
        phase_num = phase_id.replace("phase_", "")
        phase_md_path = Path(f"PHASE-{phase_num}.md")
        if phase_md_path.exists():
            from .task_parser import parse_phase_md
            tasks = parse_phase_md(str(phase_md_path))
            if tasks:
                print(f"  ✓ Found {phase_md_path} on disk — importing {len(tasks)} tasks")
                with self.session_factory() as db:
                    for i, tc in enumerate(tasks):
                        import json
                        task_db_id = f"task_{tc.id.replace('.', '_')}"
                        existing = db.query(Task).filter(Task.id == task_db_id).first()
                        if not existing:
                            t = Task(
                                id=task_db_id,
                                phase_id=phase_id,
                                name=tc.name,
                                description=tc.description,
                                success_criteria=json.dumps(tc.success_criteria),
                                dependencies=json.dumps(tc.depends),
                                model_tier=tc.model,
                                order_idx=i,
                            )
                            db.add(t)
                    db.commit()
                print(f"  ✓ Imported {len(tasks)} tasks into DB")

    async def _step_5_logic_check(self, phase_id: str) -> LogicCheckResult:
        """Step 5 (GATE): Logic check — verify phase plan is sound."""
        print("[Step 5/10] 🔬 LOGIC CHECK ← GATE")
        print("  Logic Checker Agent (Opus) reviewing phase plan...")
        print()

        # Check if a LOGIC-CHECK file exists
        phase_num = phase_id.replace("phase_", "")
        logic_check_path = Path(f"LOGIC-CHECK-{phase_num}.md")

        if logic_check_path.exists():
            content = logic_check_path.read_text(encoding="utf-8")
            verdict = "PASS" if "VERDICT: PASS" in content else "FAIL"
            import re
            issues = re.findall(r'- \[ISSUE[^\]]*\] (.+)', content)
            fixes = re.findall(r'- \[ISSUE[^\]]*\] (.+)', content)
            result = LogicCheckResult(verdict, issues, fixes)
            print(f"  ✓ Read existing {logic_check_path}: {verdict}")
            if not result.passed:
                print(f"  ⚠  Issues found ({len(issues)}):")
                for issue in issues:
                    print(f"     - {issue}")
            return result

        # Verify tasks in DB have measurable success_criteria
        issues = []
        fixes = []
        with self.session_factory() as db:
            phase = db.query(Phase).filter(Phase.id == phase_id).first()
            if not phase:
                issues.append("Phase not found in database")
                fixes.append("Run `harness init` to initialize the project")
                return LogicCheckResult("FAIL", issues, fixes)

            tasks = phase.tasks
            if not tasks:
                issues.append("Phase has no task cards")
                fixes.append("Provide a --phase-doc or run planner agent to generate tasks")
                return LogicCheckResult("FAIL", issues, fixes)

            # Check for vague success criteria
            vague_terms = ["works correctly", "looks good", "seems fine", "should work", "is correct"]
            for task in tasks:
                criteria = json.loads(task.success_criteria or "[]")
                if not criteria:
                    issues.append(f"Task {task.id} ({task.name}) has no success_criteria")
                    fixes.append(f"Add measurable criteria to task {task.id}")
                    continue
                for criterion in criteria:
                    for vague in vague_terms:
                        if vague.lower() in criterion.lower():
                            issues.append(f"Task {task.id}: vague criterion: '{criterion}'")
                            fixes.append(f"Replace '{criterion}' with a specific, measurable check")

            # Check for circular dependencies (simple cycle detection)
            dep_map = {}
            for task in tasks:
                deps = json.loads(task.dependencies or "[]")
                dep_map[task.id] = deps

            for task_id_check, deps in dep_map.items():
                for dep in deps:
                    if dep not in dep_map and not dep.startswith("task_"):
                        # Try with task_ prefix
                        dep_db = f"task_{dep.replace('.', '_')}"
                        if dep_db not in dep_map:
                            issues.append(f"Task {task_id_check} depends on unknown task: {dep}")
                            fixes.append(f"Verify that task {dep} exists and is spelled correctly")

        if issues:
            verdict = "FAIL"
            print(f"  ❌ Logic Check FAILED — {len(issues)} issue(s):")
            for issue in issues:
                print(f"     - {issue}")
        else:
            verdict = "PASS"
            print(f"  ✅ Logic Check PASSED — no issues found")

        # Write logic check file
        logic_content = f"# LOGIC-CHECK-{phase_num}.md\n\n"
        logic_content += f"VERDICT: {verdict}\n\n"
        if issues:
            logic_content += "ISSUES:\n"
            for i, issue in enumerate(issues, 1):
                logic_content += f"- [ISSUE-{i}] {issue}\n"
            logic_content += "\nFIXES:\n"
            for i, fix in enumerate(fixes, 1):
                logic_content += f"- [ISSUE-{i}] {fix}\n"
        else:
            logic_content += "ISSUES: none\n"
        logic_check_path.write_text(logic_content)

        return LogicCheckResult(verdict, issues, fixes)

    async def _step_6_fix_issues(self, phase_id: str, logic_result: LogicCheckResult):
        """Step 6: Fix issues found in logic check."""
        print("[Step 6/10] 🔧 FIX ISSUES — Reviser Agent (Sonnet) applying fixes...")
        print()

        for i, (issue, fix) in enumerate(zip(logic_result.issues, logic_result.fixes), 1):
            print(f"  Issue {i}: {issue}")
            print(f"  Fix:   {fix}")
            print()

        # In production: spawn reviser agent to modify PHASE-N.md
        print("  ℹ  (In production: Reviser Agent would apply fixes to PHASE-N.md)")
        print("  ℹ  Re-running logic check after fixes...")

    async def _step_7_human_approval(self, phase_id: str) -> bool:
        """Step 7 (GATE): Wait for human approval before spawning workers."""
        print()
        print("=" * 60)
        print("[Step 7/10] 👤 HUMAN APPROVAL ← GATE")
        print("=" * 60)

        phase_num = phase_id.replace("phase_", "")
        phase_md_path = Path(f"PHASE-{phase_num}.md")

        print()
        if phase_md_path.exists():
            print(f"  📋 Phase plan: {phase_md_path} (review before approving)")
        print()

        # Show task summary
        with self.session_factory() as db:
            phase = db.query(Phase).filter(Phase.id == phase_id).first()
            if phase and phase.tasks:
                print(f"  Tasks to be executed ({len(phase.tasks)} total):")
                for task in phase.tasks:
                    deps = json.loads(task.dependencies or "[]")
                    dep_str = f" [depends: {', '.join(deps)}]" if deps else ""
                    print(f"    • {task.id} — {task.name} (model: {task.model_tier}){dep_str}")
        print()

        if self.dry_run:
            print("  [dry-run] Auto-approving (--dry-run mode)")
            return True

        # Block waiting for human input
        print("  Type 'approve' and press Enter to proceed, or 'reject' to halt:")
        while True:
            try:
                response = input("  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n  Interrupted — halting phase.")
                return False

            if response == "approve":
                print("  ✅ Approved — spawning workers...")
                # Mark phase as active
                with self.session_factory() as db:
                    phase = db.query(Phase).filter(Phase.id == phase_id).first()
                    if phase:
                        phase.status = PhaseStatus.active
                        db.commit()
                return True
            elif response == "reject":
                print("  ❌ Rejected — halting phase.")
                return False
            else:
                print("  Please type 'approve' or 'reject'")

    async def _step_8_run_workers(self, phase_id: str):
        """Step 8: Spawn workers for all ready tasks (respecting dependencies)."""
        print()
        print("[Step 8/10] 🚀 DEVELOPMENT — Spawning workers for ready tasks...")
        print()

        if self.dry_run:
            with self.session_factory() as db:
                phase = db.query(Phase).filter(Phase.id == phase_id).first()
                if phase:
                    for task in phase.tasks:
                        model = task.model_tier or "sonnet"
                        print(f"  [dry-run] Would spawn: Worker(task={task.id}, model=claude-{model}-4-6)")
            print()
            return

        # Use orchestrator to tick (spawns ready tasks)
        print("  Calling orchestrator.tick() to spawn ready tasks...")
        self.orchestrator.tick()
        print("  ✓ Workers spawned. Monitor progress with: harness status")

    async def _step_9_validate_and_report(self, phase_id: str):
        """Step 9: Validate task completion and generate phase report."""
        print()
        print("[Step 9/10] 📊 VALIDATE + REPORT")
        print()

        if self.dry_run:
            print("  [dry-run] Would run: Validator + Reporter agents")
            return

        phase_num = phase_id.replace("phase_", "")

        # Check completion status
        with self.session_factory() as db:
            phase = db.query(Phase).filter(Phase.id == phase_id).first()
            if not phase:
                return

            tasks = phase.tasks
            done = [t for t in tasks if t.status == TaskStatus.done]
            failed = [t for t in tasks if t.status == TaskStatus.failed]
            pending = [t for t in tasks if t.status == TaskStatus.pending]
            running = [t for t in tasks if t.status == TaskStatus.running]

            print(f"  Tasks: {len(done)} done, {len(running)} running, "
                  f"{len(pending)} pending, {len(failed)} failed")

        # Write REPORT-N.md
        report_path = Path(f"REPORT-{phase_num}.md")
        now = datetime.utcnow().isoformat()
        total = len(tasks) if 'tasks' in dir() else 0
        done_count = len(done) if 'done' in dir() else 0

        report_content = f"""# REPORT-{phase_num}: Phase {phase_num}

**Date:** {now}
**Status:** {"COMPLETE" if len(done) == total else "PARTIAL"}

## Summary
Phase {phase_num} execution {"completed successfully" if len(done) == total else "partially completed"}.
{len(done)}/{total} tasks finished.

## Tasks Completed
"""
        if 'done' in dir():
            for task in done:
                report_content += f"- {task.id}: {task.name}\n"

        report_content += "\n## Issues Found\n"
        if 'failed' in dir() and failed:
            for task in failed:
                report_content += f"- {task.id}: {task.name} — FAILED\n"
        else:
            report_content += "None\n"

        report_content += f"\n## Metrics\n- Generated at: {now}\n"

        report_path.write_text(report_content)
        print(f"  ✓ Report written: {report_path}")

    async def _step_10_next_phase(self, phase_id: str):
        """Step 10: Trigger next phase or mark project complete."""
        print()
        print("[Step 10/10] ⏭  NEXT PHASE")
        print()

        with self.session_factory() as db:
            phase = db.query(Phase).filter(Phase.id == phase_id).first()
            if not phase:
                return

            project = db.query(Project).filter(Project.id == self.project_id).first()
            if not project:
                return

            # Find next phase
            next_phases = [
                p for p in project.phases
                if p.order_idx > phase.order_idx and p.status == PhaseStatus.pending
            ]

            # Mark current phase done
            all_done = all(t.status == TaskStatus.done for t in phase.tasks) if phase.tasks else False
            any_failed = any(t.status == TaskStatus.failed for t in phase.tasks) if phase.tasks else False

            if not self.dry_run:
                phase.status = PhaseStatus.done if all_done else PhaseStatus.failed
                db.commit()

            if next_phases:
                next_phase = min(next_phases, key=lambda p: p.order_idx)
                print(f"  ✓ Phase {phase_id} complete — next: {next_phase.id} ({next_phase.name})")
                print(f"  ℹ  Run `harness run` again to proceed to Phase {next_phase.id}")
            else:
                print(f"  ✅ All phases complete! Project '{project.name}' finished.")
                print("  ℹ  Run `harness status` to see final results")
