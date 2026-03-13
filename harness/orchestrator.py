"""
Orchestrator Brain — dependency analysis, task scheduling, worker lifecycle.

Responsibilities:
- Read pending tasks from SQLite
- Analyze dependency graph (which tasks can run in parallel now)
- Trigger Worker Spawner for ready tasks
- Handle task completion / failure / blocking events from Watchdog
- Decide next steps (continue, retry, escalate to user)

Inspired by: Paperclip Orchestration Service + Anthropic Harness Executor
"""
import logging
from typing import Optional
from .state import get_session_factory
from .models import Task, Worker, TaskStatus, WorkerStatus
from .spawner import WorkerSpawner
from .context_builder import build_worker_context

logger = logging.getLogger(__name__)


class OrchestratorBrain:
    """
    The Conductor's decision-making core.
    Does NOT execute tasks directly — only spawns Workers and makes decisions.
    """

    def __init__(self, project_id: str, db_path=None):
        self.project_id = project_id
        self.session_factory = get_session_factory(db_path) if db_path else get_session_factory()
        self.spawner = WorkerSpawner()

    def tick(self):
        """
        Main orchestration loop tick.
        Called on startup and after each task completion event.
        """
        with self.session_factory() as db:
            ready_tasks = self._get_ready_tasks(db)
            logger.info(f"[Orchestrator] {len(ready_tasks)} tasks ready to run")

            for task in ready_tasks:
                self._spawn_worker_for_task(db, task)

    def _get_ready_tasks(self, db) -> list[Task]:
        """
        Return tasks whose status is 'pending' and all dependencies are 'done'.
        These tasks can be spawned immediately (potentially in parallel).
        """
        import json
        pending = db.query(Task).filter(Task.status == TaskStatus.pending).all()
        ready = []

        for task in pending:
            deps = json.loads(task.dependencies or "[]")
            if not deps:
                ready.append(task)
                continue

            # Check all dependencies are done
            done_task_ids = {
                t.id for t in db.query(Task).filter(
                    Task.id.in_(deps), Task.status == TaskStatus.done
                ).all()
            }
            if set(deps).issubset(done_task_ids):
                ready.append(task)

        return ready

    def _spawn_worker_for_task(self, db, task: Task):
        """Build context and spawn a Worker for the given task."""
        from .models import Project, Phase

        phase = db.get(Phase, task.phase_id)
        project = db.get(Project, phase.project_id)
        completed_tasks = db.query(Task).filter(
            Task.phase_id == task.phase_id,
            Task.status == TaskStatus.done
        ).all()

        context = build_worker_context(project, phase, task, completed_tasks)

        worker_id = self.spawner.spawn(task.id, context)
        task.status = TaskStatus.running
        db.commit()
        logger.info(f"[Orchestrator] Spawned worker {worker_id} for task {task.id}")

    # ──────────────────────────────────────────────────────────────
    # Event handlers (called by Watchdog)
    # ──────────────────────────────────────────────────────────────

    def on_task_done(self, task_id: str, payload: dict):
        """Called when Watchdog verifies a task is complete."""
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if task:
                task.status = TaskStatus.done
                task.result_summary = payload.get("summary", "")
                db.commit()
                logger.info(f"[Orchestrator] Task {task_id} marked done.")
                self.tick()  # Check if new tasks are now unblocked

    def on_task_verification_failed(self, task_id: str):
        """Called when Worker claimed done but verification failed."""
        logger.warning(f"[Orchestrator] Task {task_id} failed verification — worker re-notified by Stop Hook.")

    def on_task_blocked(self, task_id: str, payload: dict):
        """Called when Worker signals it's blocked."""
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if task:
                task.status = TaskStatus.blocked
                db.commit()
        logger.warning(f"[Orchestrator] Task {task_id} blocked: {payload.get('reason')}")

    def on_task_failed(self, task_id: str, payload: dict):
        """Called when Worker explicitly fails."""
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if task:
                task.retry_count += 1
                if task.retry_count < task.max_retries:
                    task.status = TaskStatus.pending  # Re-queue for retry
                    logger.warning(f"[Orchestrator] Task {task_id} failed (retry {task.retry_count}/{task.max_retries})")
                    self.tick()
                else:
                    task.status = TaskStatus.failed
                    logger.error(f"[Orchestrator] Task {task_id} FATAL: max retries ({task.max_retries}) exhausted")
                    self._notify_user_escalation(task_id)
                db.commit()

    def on_worker_hung(self, task_id: str, worker_id: str):
        """Called when Watchdog kills a hung worker."""
        logger.warning(f"[Orchestrator] Worker {worker_id} for task {task_id} was hung — respawning.")
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if task:
                task.status = TaskStatus.pending
                task.retry_count += 1
                db.commit()
        self.tick()

    def get_running_workers(self) -> list[Worker]:
        """Called by Watchdog to get active workers for heartbeat checking."""
        with self.session_factory() as db:
            return db.query(Worker).filter(Worker.status == WorkerStatus.running).all()

    def _notify_user_escalation(self, task_id: str):
        """Escalate to user when max retries exhausted."""
        from .notifier import notify
        notify(f"⛔ Task {task_id} failed {3} times. Human intervention required.")
