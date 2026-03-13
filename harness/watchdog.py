"""
Watchdog Daemon — monitors workers, detects hangs, triggers respawn.

Detection mechanism:
- Completion: FSEvents on .harness/events/ (file creation, NOT polling)
  → ralph-wiggum Stop Hook writes flag file → Watchdog reacts in <1s
- Hang: checks .harness/heartbeats/{task_id}.txt modification time
  → if >30 minutes old → worker declared hung → kill + respawn

Inspired by:
- ralph-wiggum (Stop Hook flag file pattern)
- Paperclip (heartbeat scheduler)
- everything-claude-code (Verification Loop)
"""
import os
import json
import signal
import logging
from datetime import datetime, timedelta
from pathlib import Path
from threading import Timer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

logger = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT_MINUTES = 30
HEARTBEAT_CHECK_INTERVAL_SECONDS = 300  # 5 minutes
EVENTS_DIR = Path(".harness/events")
HEARTBEATS_DIR = Path(".harness/heartbeats")


class HarnessEventHandler(FileSystemEventHandler):
    """Reacts to flag files written by Claude Code Workers via Stop Hook."""

    def __init__(self, orchestrator_callback):
        self.on_task_event = orchestrator_callback

    def on_created(self, event):
        if isinstance(event, FileCreatedEvent) and event.src_path.endswith(".json"):
            path = Path(event.src_path)
            try:
                payload = json.loads(path.read_text())
                task_id = payload.get("task_id")
                status = payload.get("status")

                if not task_id:
                    return

                if "_complete" in path.name:
                    logger.info(f"[Watchdog] Task complete signal: {task_id}")
                    self.on_task_event("TASK_COMPLETE", task_id, payload)

                elif "_blocked" in path.name:
                    logger.warning(f"[Watchdog] Task blocked: {task_id}")
                    self.on_task_event("TASK_BLOCKED", task_id, payload)

                elif "_failed" in path.name:
                    logger.error(f"[Watchdog] Task failed: {task_id}")
                    self.on_task_event("TASK_FAILED", task_id, payload)

            except Exception as e:
                logger.error(f"[Watchdog] Error parsing event file {path}: {e}")


class WatchdogDaemon:
    """
    Runs as a background daemon.
    Monitors .harness/events/ for completion signals.
    Checks heartbeats every 5 minutes.
    """

    def __init__(self, harness_dir: Path, orchestrator):
        self.harness_dir = harness_dir
        self.orchestrator = orchestrator
        self.observer = Observer()
        self._heartbeat_timer = None

    def start(self):
        """Start the daemon."""
        EVENTS_DIR.mkdir(parents=True, exist_ok=True)
        HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)

        # Start FSEvents listener
        handler = HarnessEventHandler(self._on_task_event)
        self.observer.schedule(handler, str(EVENTS_DIR), recursive=False)
        self.observer.start()
        logger.info("[Watchdog] FSEvents listener started on .harness/events/")

        # Start heartbeat checker
        self._schedule_heartbeat_check()
        logger.info("[Watchdog] Heartbeat checker started (30min timeout)")

    def stop(self):
        self.observer.stop()
        self.observer.join()
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
        logger.info("[Watchdog] Stopped.")

    def _on_task_event(self, event_type: str, task_id: str, payload: dict):
        """Dispatch task events to Orchestrator."""
        if event_type == "TASK_COMPLETE":
            # Verify success criteria before marking done
            if self._verify_task(task_id, payload):
                self.orchestrator.on_task_done(task_id, payload)
            else:
                logger.warning(f"[Watchdog] {task_id} claimed complete but verification failed. Retrying.")
                self.orchestrator.on_task_verification_failed(task_id)

        elif event_type == "TASK_BLOCKED":
            self.orchestrator.on_task_blocked(task_id, payload)

        elif event_type == "TASK_FAILED":
            self.orchestrator.on_task_failed(task_id, payload)

    def _verify_task(self, task_id: str, payload: dict) -> bool:
        """
        Verify that success_criteria are actually met.
        Delegates to Verifier (Haiku model for speed/cost).
        TODO: implement Verifier
        """
        # For now, trust the Worker's payload
        return payload.get("status") == "done"

    def _schedule_heartbeat_check(self):
        """Schedule next heartbeat check."""
        self._heartbeat_timer = Timer(
            HEARTBEAT_CHECK_INTERVAL_SECONDS, 
            self._check_heartbeats
        )
        self._heartbeat_timer.daemon = True
        self._heartbeat_timer.start()

    def _check_heartbeats(self):
        """Check all active workers for heartbeat timeout."""
        now = datetime.utcnow()
        timeout = now - timedelta(minutes=HEARTBEAT_TIMEOUT_MINUTES)

        running_workers = self.orchestrator.get_running_workers()
        for worker in running_workers:
            heartbeat_file = HEARTBEATS_DIR / f"{worker.task_id}.txt"

            if not heartbeat_file.exists():
                # No heartbeat file at all — check spawn time
                if worker.spawned_at < timeout:
                    logger.warning(f"[Watchdog] Worker {worker.id} (task: {worker.task_id}) — no heartbeat, spawned >{HEARTBEAT_TIMEOUT_MINUTES}min ago. Killing.")
                    self._kill_worker(worker)
            else:
                mtime = datetime.utcfromtimestamp(heartbeat_file.stat().st_mtime)
                if mtime < timeout:
                    logger.warning(f"[Watchdog] Worker {worker.id} (task: {worker.task_id}) — heartbeat stale ({HEARTBEAT_TIMEOUT_MINUTES}min). Killing.")
                    self._kill_worker(worker)

        # Schedule next check
        self._schedule_heartbeat_check()

    def _kill_worker(self, worker):
        """Kill a hung worker and notify Orchestrator to respawn."""
        if worker.pid:
            try:
                os.kill(worker.pid, signal.SIGTERM)
                logger.info(f"[Watchdog] Killed worker PID {worker.pid}")
            except ProcessLookupError:
                pass  # Already dead
        self.orchestrator.on_worker_hung(worker.task_id, worker.id)
