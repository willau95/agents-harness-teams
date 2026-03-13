"""
Madness Army Relay Integration.
Distributes tasks to remote machines in the Madness Army fleet
via their relay daemon (port 59000, Express.js).
No Redis needed — uses existing relay HTTP API.

Usage:
    harness run --fleet "192.168.1.2:59000,192.168.1.3:59000"

The relay daemon on each machine exposes:
  POST /blueprint/dispatch     — Receive a task to execute
  GET  /blueprint/status/{id}  — Check task status
  GET  /system/stats           — Get machine load/capacity
  GET  /health                 — Health check
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)

# Default timeout for relay HTTP calls (seconds)
RELAY_TIMEOUT = 10.0
HEALTH_TIMEOUT = 3.0


@dataclass
class MachineStatus:
    """Status of a single machine in the Madness Army fleet."""
    url: str
    online: bool
    active_tasks: int
    available: bool
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    model: str = ""


@dataclass
class DispatchResult:
    """Result of dispatching a task to a remote machine."""
    success: bool
    machine_url: str
    task_id: str
    remote_job_id: str = ""
    error: str = ""


class MadnessArmyRelay:
    """
    Integrates with Madness Army's relay daemon (port 59000, Express.js).

    Allows distributing agents-harness-teams tasks to remote machines
    in the Madness Army fleet. Uses the existing relay HTTP API —
    no Redis, no extra infrastructure needed.

    Each machine must be running the relay daemon:
        # On each remote machine:
        cd ~/madness-army && npm start
        # Relay listens on port 59000

    Usage:
        relay = MadnessArmyRelay(["http://192.168.1.2:59000"])
        machine = await relay.get_available_machine()
        await relay.dispatch_task(machine, "task_1_1", context)
    """

    def __init__(self, relay_urls: list[str]):
        """
        Initialize with a list of relay URLs.

        Args:
            relay_urls: List of relay base URLs, e.g.
                        ["http://192.168.1.2:59000", "http://192.168.1.3:59000"]
        """
        # Normalize URLs (ensure http:// prefix)
        self.relays = [
            url if url.startswith("http") else f"http://{url}"
            for url in relay_urls
        ]
        logger.info(f"[MadnessArmy] Initialized with {len(self.relays)} relay(s): {self.relays}")

    async def get_available_machine(self) -> Optional[str]:
        """
        Find the least-loaded available machine in the fleet.

        Pings each relay's /health and /system/stats endpoints,
        then returns the URL of the machine with fewest active tasks.

        Returns:
            URL of the best available machine, or None if all are offline.
        """
        if not HTTPX_AVAILABLE:
            logger.warning("[MadnessArmy] httpx not installed — cannot query fleet")
            return self.relays[0] if self.relays else None

        fleet_status = await self.get_fleet_status()
        available = [m for m in fleet_status if m.online and m.available]

        if not available:
            logger.warning("[MadnessArmy] No available machines in fleet")
            return None

        # Sort by active_tasks ascending (least loaded first)
        best = sorted(available, key=lambda m: (m.active_tasks, m.cpu_percent))[0]
        logger.info(f"[MadnessArmy] Best machine: {best.url} (active_tasks={best.active_tasks})")
        return best.url

    async def dispatch_task(
        self,
        machine_url: str,
        task_id: str,
        context: dict,
    ) -> bool:
        """
        POST a task to a remote machine's relay /blueprint/dispatch endpoint.

        The relay will spawn a Claude Code worker on the remote machine
        using the provided context.

        Args:
            machine_url: Base URL of the target relay (e.g. "http://192.168.1.2:59000")
            task_id:     Unique task identifier (e.g. "task_1_1")
            context:     Task context dict (serialized from WorkerContext)

        Returns:
            True if dispatch succeeded, False otherwise.
        """
        if not HTTPX_AVAILABLE:
            logger.warning("[MadnessArmy] httpx not installed — dispatch skipped")
            return False

        payload = {
            "task_id": task_id,
            "context": context,
            "source": "agents-harness-teams",
        }

        async with httpx.AsyncClient(timeout=RELAY_TIMEOUT) as client:
            try:
                url = f"{machine_url}/blueprint/dispatch"
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                logger.info(
                    f"[MadnessArmy] Task {task_id} dispatched to {machine_url}: "
                    f"job_id={result.get('job_id', 'N/A')}"
                )
                return True
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"[MadnessArmy] Dispatch failed for {task_id} on {machine_url}: "
                    f"HTTP {e.response.status_code}"
                )
                return False
            except httpx.RequestError as e:
                logger.error(f"[MadnessArmy] Network error dispatching to {machine_url}: {e}")
                return False

    async def check_task_status(self, machine_url: str, task_id: str) -> dict:
        """
        GET task status from a remote machine's relay.

        Returns:
            Dict with keys: task_id, status, progress, artifacts, error
            Returns empty dict on failure.
        """
        if not HTTPX_AVAILABLE:
            return {}

        async with httpx.AsyncClient(timeout=RELAY_TIMEOUT) as client:
            try:
                url = f"{machine_url}/blueprint/status/{task_id}"
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                logger.warning(f"[MadnessArmy] Status check failed for {task_id} on {machine_url}: {e}")
                return {}

    async def get_fleet_status(self) -> list[MachineStatus]:
        """
        Get the status of all machines in the fleet.

        Queries /health and /system/stats on each relay concurrently.

        Returns:
            List of MachineStatus objects (one per relay URL).
        """
        if not HTTPX_AVAILABLE:
            # Return placeholder statuses
            return [
                MachineStatus(url=url, online=False, active_tasks=0, available=False)
                for url in self.relays
            ]

        tasks = [self._probe_machine(url) for url in self.relays]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        statuses = []
        for url, result in zip(self.relays, results):
            if isinstance(result, Exception):
                logger.warning(f"[MadnessArmy] Machine {url} probe failed: {result}")
                statuses.append(
                    MachineStatus(url=url, online=False, active_tasks=0, available=False)
                )
            else:
                statuses.append(result)

        return statuses

    async def _probe_machine(self, url: str) -> MachineStatus:
        """Probe a single machine for health and stats."""
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
            # Health check
            try:
                health_resp = await client.get(f"{url}/health")
                online = health_resp.status_code == 200
            except httpx.RequestError:
                return MachineStatus(url=url, online=False, active_tasks=0, available=False)

            if not online:
                return MachineStatus(url=url, online=False, active_tasks=0, available=False)

            # Stats
            try:
                stats_resp = await client.get(f"{url}/system/stats")
                stats = stats_resp.json() if stats_resp.status_code == 200 else {}
            except (httpx.RequestError, Exception):
                stats = {}

            active_tasks = stats.get("active_tasks", 0)
            cpu = stats.get("cpu_percent", 0.0)
            mem = stats.get("memory_percent", 0.0)
            max_tasks = stats.get("max_concurrent_tasks", 4)

            return MachineStatus(
                url=url,
                online=True,
                active_tasks=active_tasks,
                available=(active_tasks < max_tasks and cpu < 90),
                cpu_percent=cpu,
                memory_percent=mem,
                model=stats.get("model", ""),
            )

    def format_fleet_table(self, statuses: list[MachineStatus]) -> str:
        """Format fleet status as a human-readable table."""
        lines = ["Fleet Status:", "─" * 70]
        lines.append(
            f"{'URL':<35} {'Online':<8} {'Tasks':<8} {'CPU%':<8} {'Avail':<8}"
        )
        lines.append("─" * 70)
        for m in statuses:
            online_str = "✓" if m.online else "✗"
            avail_str = "yes" if m.available else "no"
            lines.append(
                f"{m.url:<35} {online_str:<8} {m.active_tasks:<8} "
                f"{m.cpu_percent:<8.1f} {avail_str:<8}"
            )
        lines.append("─" * 70)
        return "\n".join(lines)
