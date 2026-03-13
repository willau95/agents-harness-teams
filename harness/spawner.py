"""
Worker Spawner — launches isolated Claude Code sessions for each task.

Session Isolation principle (Maestro-inspired):
- Each task gets a FRESH Claude Code session
- Context pollution impossible: previous task's "fix Redis" memory cannot bleed into next task
- Only the Goal Ancestry Chain JSON is injected — precisely scoped

Model Tiering:
- opus (claude-opus-4-6): architecture / planning / logic-check tasks (high quality)
- sonnet (claude-sonnet-4-6): all development / execution tasks (balanced quality/cost)
"""
import os
import json
import uuid
import subprocess
import logging
from pathlib import Path
from .context_builder import WorkerContext
from .models import Worker, WorkerStatus

logger = logging.getLogger(__name__)

HARNESS_DIR = Path(".harness")

MODEL_MAP = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
}

ROLE_MODELS = {
    "initializer": "opus",    # Parses goal, generates Phase/Task tree
    "planner": "opus",        # Writes Task Cards (Step 4)
    "logic_checker": "opus",  # Deep logic check (Step 5)
    "reviser": "sonnet",      # Fixes issues found in logic check (Step 6)
    "worker": "sonnet",       # All development execution (Step 8)
    "validator": "sonnet",    # Post-dev check (Step 9)
    "reporter": "sonnet",     # REPORT-N.md generation (Step 9)
    "orchestrator": "sonnet", # Dependency analysis, decision making
}


class WorkerSpawner:
    """
    Spawns Claude Code workers for individual tasks.
    Each worker is a fresh, isolated subprocess.
    """

    def spawn(self, task_id: str, context: WorkerContext) -> str:
        """
        Spawn a Claude Code worker for the given task.
        Returns the worker_id.
        """
        worker_id = str(uuid.uuid4())[:8]

        # Prepare worker directory
        worker_dir = HARNESS_DIR / "workers" / task_id
        worker_dir.mkdir(parents=True, exist_ok=True)

        # Write context JSON
        context_file = worker_dir / "context.json"
        context_file.write_text(context.to_json())

        # Write current task marker (for Stop Hook)
        (HARNESS_DIR / "current_task.txt").write_text(task_id)

        # Build Claude Code command
        model = MODEL_MAP.get(context.model_tier, MODEL_MAP["sonnet"])
        worker_prompt = context.to_worker_prompt()

        # Write prompt to file (avoid shell injection)
        prompt_file = worker_dir / "prompt.txt"
        prompt_file.write_text(worker_prompt)

        cmd = [
            "claude",
            "--model", model,
            "--print",           # Non-interactive mode
            "--stop-hook", str(Path(__file__).parent.parent / "plugins/claude-code/harness-stop-hook/stop-hook.sh"),
            "-p", worker_prompt,
        ]

        logger.info(f"[Spawner] Launching worker {worker_id} for task {task_id} (model: {model})")

        # Spawn as background process
        proc = subprocess.Popen(
            cmd,
            stdout=open(worker_dir / "stdout.log", "w"),
            stderr=open(worker_dir / "stderr.log", "w"),
            cwd=str(Path.cwd()),
        )

        # Record in worker log
        worker_log = worker_dir / "worker.json"
        worker_log.write_text(json.dumps({
            "worker_id": worker_id,
            "task_id": task_id,
            "pid": proc.pid,
            "model": model,
            "status": "running",
            "spawned_at": __import__("datetime").datetime.utcnow().isoformat(),
        }, indent=2))

        logger.info(f"[Spawner] Worker {worker_id} PID={proc.pid} started for task {task_id}")
        return worker_id
