"""
Context Builder — constructs the Goal Ancestry Chain JSON for each Worker.

This is the core of the "telephone game" fix.
Instead of passing a long MD document, every Worker receives a structured
JSON with the complete project→phase→task ancestry + precise success criteria.

Inspired by: Paperclip's Goal Ancestry Chain
"""
import json
from dataclasses import dataclass
from typing import Optional
from .models import Project, Phase, Task


@dataclass
class WorkerContext:
    """Complete context payload injected into every Claude Code worker."""
    task_id: str
    task_name: str
    project_goal: str
    project_tech_context: str
    phase_objective: str
    phase_prerequisites_done: list[str]
    task_description: str
    success_criteria: list[str]
    context_snapshot: dict
    previous_tasks_summary: list[dict]
    model_tier: str
    harness_version: str = "0.1.0"

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_dict(self) -> dict:
        return {
            "harness_version": self.harness_version,
            "task_context": {
                "task_id": self.task_id,
                "task_name": self.task_name,
                "ancestry": {
                    "project": {
                        "goal": self.project_goal,
                        "tech_context": self.project_tech_context,
                    },
                    "phase": {
                        "objective": self.phase_objective,
                        "prerequisites_done": self.phase_prerequisites_done,
                    },
                    "task": {
                        "description": self.task_description,
                        "success_criteria": self.success_criteria,
                        "context_snapshot": self.context_snapshot,
                        "previous_tasks_summary": self.previous_tasks_summary,
                        "model_tier": self.model_tier,
                    }
                },
                "worker_instructions": (
                    f"You are a Worker Agent executing task '{self.task_id}'.\n"
                    f"Write heartbeat every 5 min to: .harness/heartbeats/{self.task_id}.txt\n"
                    f"Write completion to: .harness/events/{self.task_id}_complete.json\n"
                    f"See WORKER-CONTRACT.md for full spec."
                ),
            }
        }

    def to_worker_prompt(self) -> str:
        """Generate the injection prompt for the Claude Code worker."""
        criteria_list = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(self.success_criteria))
        prev_tasks = "\n".join(
            f"  - [{t['task_id']}] {t['summary']}" 
            for t in self.previous_tasks_summary
        ) or "  (none — this is the first task)"

        return f"""
You are a Worker Agent for the agents-harness-teams system.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK: {self.task_name} [{self.task_id}]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[PROJECT GOAL]
{self.project_goal}

[PHASE OBJECTIVE]
{self.phase_objective}

[YOUR SPECIFIC TASK]
{self.task_description}

[COMPLETED CONTEXT]
{prev_tasks}

[SUCCESS CRITERIA — ALL must be true before you finish]
{criteria_list}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY WORKER PROTOCOL:
1. Every 5 minutes: echo $(date -u) > .harness/heartbeats/{self.task_id}.txt
2. When ALL success criteria are met, write:
   .harness/events/{self.task_id}_complete.json
   Format: {{"task_id": "{self.task_id}", "status": "done", "summary": "...", "artifacts": [...], "timestamp": "..."}}
3. Do NOT mark yourself done until every criterion is verified.
4. If blocked, write: .harness/events/{self.task_id}_blocked.json
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()


def build_worker_context(
    project: Project,
    phase: Phase,
    task: Task,
    completed_tasks_in_phase: list[Task],
) -> WorkerContext:
    """
    Build the complete WorkerContext for a task.
    Called by the Orchestrator before spawning a Worker.
    """
    criteria = json.loads(task.success_criteria)
    dependencies = json.loads(task.dependencies or "[]")

    # Build summary of completed tasks (prevent context pollution — only summaries, not full context)
    prev_summaries = [
        {"task_id": t.id, "summary": t.result_summary or "completed"}
        for t in completed_tasks_in_phase
        if t.id in dependencies and t.result_summary
    ]

    # Context snapshot (from task definition)
    context_snapshot = {}  # TODO: parse from task.description or separate field

    return WorkerContext(
        task_id=task.id,
        task_name=task.name,
        project_goal=project.goal,
        project_tech_context=project.tech_context or "",
        phase_objective=phase.objective or phase.name,
        phase_prerequisites_done=[
            f"Phase {p.order_idx - 1}: {p.name}" 
            for p in project.phases 
            if p.order_idx < phase.order_idx and p.status == "done"
        ],
        task_description=task.description,
        success_criteria=criteria,
        context_snapshot=context_snapshot,
        previous_tasks_summary=prev_summaries,
        model_tier=task.model_tier or "sonnet",
    )
