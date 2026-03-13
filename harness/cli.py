"""
harness CLI — main entry point for agents-harness-teams.

Commands:
  harness init    — Initialize a project (parse Phase MD, create SQLite DB)
  harness run     — Execute the 10-step phase cycle
  harness status  — Show task/phase status table
  harness daemon  — Manage the watchdog daemon
"""
import asyncio
import json
import os
import signal
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

app = typer.Typer(
    name="harness",
    help="Universal multi-agent harness for Claude Code and OpenClaw.",
    no_args_is_help=True,
)
console = Console()

HARNESS_DIR = Path(".harness")


# ──────────────────────────────────────────────────────────────────────────────
# harness init
# ──────────────────────────────────────────────────────────────────────────────

@app.command()
def init(
    goal: str = typer.Option(..., "--goal", "-g", help="High-level project goal"),
    phase_doc: Optional[Path] = typer.Option(None, "--phase-doc", help="Path to Phase MD file with Task Cards"),
    context: Optional[str] = typer.Option(None, "--context", help="Tech stack / constraints"),
    project_dir: Path = typer.Option(Path("."), "--dir", help="Project directory (default: current)"),
    project_name: Optional[str] = typer.Option(None, "--name", help="Project name (default: derived from goal)"),
):
    """
    Initialize a new harness project.
    Parses goal + optional phase doc into a SQLite Task tree.
    """
    import hashlib
    from .state import init_db
    from .models import Project, Phase, Task, ProjectStatus

    console.print("\n[bold green]⚙️  Initializing harness project...[/bold green]")

    # ── 1. Create .harness/ directory ─────────────────────────────────────────
    harness_path = project_dir / ".harness"
    harness_path.mkdir(parents=True, exist_ok=True)

    events_dir = harness_path / "events"
    workers_dir = harness_path / "workers"
    heartbeats_dir = harness_path / "heartbeats"
    sessions_dir = harness_path / "sessions"
    for d in [events_dir, workers_dir, heartbeats_dir, sessions_dir]:
        d.mkdir(exist_ok=True)

    console.print(f"  ✓ Created [cyan].harness/[/cyan] directory structure")

    # ── 2. Initialize SQLite DB ────────────────────────────────────────────────
    db_path = harness_path / "state.db"
    engine = init_db(db_path)
    console.print(f"  ✓ Initialized SQLite: [cyan].harness/state.db[/cyan]")

    # ── 3. Create project record ──────────────────────────────────────────────
    from .state import get_session_factory
    session_factory = get_session_factory(db_path)

    proj_name = project_name or goal[:40].replace(" ", "-").lower()
    proj_id = f"proj_{hashlib.md5(goal.encode()).hexdigest()[:8]}"

    loaded_tasks = []

    with session_factory() as db:
        # Check if project already exists
        from .models import Project
        existing = db.query(Project).filter(Project.id == proj_id).first()
        if existing:
            console.print(f"  ⚠  Project already initialized: [yellow]{proj_id}[/yellow]")
            proj_id_final = existing.id
        else:
            project = Project(
                id=proj_id,
                name=proj_name,
                goal=goal,
                tech_context=context or "",
                status=ProjectStatus.active,
            )
            db.add(project)
            db.commit()
            proj_id_final = proj_id
            console.print(f"  ✓ Created project: [cyan]{proj_name}[/cyan] (id: {proj_id})")

        # ── 4. Parse phase doc if provided ────────────────────────────────────
        if phase_doc:
            if not phase_doc.exists():
                console.print(f"[bold red]✗ Phase doc not found:[/bold red] {phase_doc}")
                raise typer.Exit(1)

            from .task_parser import parse_phase_md
            tasks = parse_phase_md(str(phase_doc))

            if not tasks:
                console.print(f"  [yellow]⚠  No task cards found in {phase_doc}[/yellow]")
            else:
                # Derive phase info from filename or first task ID
                phase_num = tasks[0].id.split(".")[0] if tasks else "1"
                phase_id = f"phase_{phase_num}"

                from .models import Phase
                existing_phase = db.query(Phase).filter(Phase.id == phase_id).first()
                if not existing_phase:
                    phase = Phase(
                        id=phase_id,
                        project_id=proj_id_final,
                        name=f"Phase {phase_num}",
                        objective=f"Tasks from {phase_doc.name}",
                        order_idx=int(phase_num),
                    )
                    db.add(phase)
                    db.commit()

                from .models import Task
                for i, tc in enumerate(tasks):
                    task_db_id = f"task_{tc.id.replace('.', '_')}"
                    existing_task = db.query(Task).filter(Task.id == task_db_id).first()
                    if not existing_task:
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
                        loaded_tasks.append(tc)

                db.commit()
                console.print(f"  ✓ Loaded [bold]{len(loaded_tasks)}[/bold] tasks from [cyan]{phase_doc.name}[/cyan]")

    # ── 5. Write .harness/project.json (Goal Ancestry root) ───────────────────
    project_json = {
        "schema": "goal-ancestry-v1",
        "project_id": proj_id_final,
        "name": proj_name,
        "goal": goal,
        "tech_context": context or "",
        "initialized_at": datetime.utcnow().isoformat(),
        "phase_doc": str(phase_doc) if phase_doc else None,
    }
    (harness_path / "project.json").write_text(
        json.dumps(project_json, indent=2)
    )
    console.print(f"  ✓ Wrote [cyan].harness/project.json[/cyan]")

    # ── 6. Print summary table ─────────────────────────────────────────────────
    console.print()
    console.print("[bold green]✅ Project initialized[/bold green]")
    console.print()

    if loaded_tasks:
        table = Table(title=f"Tasks loaded from {phase_doc.name if phase_doc else 'none'}")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="white")
        table.add_column("Model", style="magenta")
        table.add_column("Depends", style="yellow")
        table.add_column("Criteria", style="green")

        for tc in loaded_tasks:
            dep_str = ", ".join(tc.depends) if tc.depends else "none"
            table.add_row(
                tc.id,
                tc.name,
                tc.model,
                dep_str,
                str(len(tc.success_criteria)),
            )
        console.print(table)
        console.print()

    console.print(f"  Goal: [italic]{goal}[/italic]")
    console.print(f"  Project ID: [cyan]{proj_id_final}[/cyan]")
    console.print()
    console.print("  Next step: [bold]harness run[/bold]")


# ──────────────────────────────────────────────────────────────────────────────
# harness run
# ──────────────────────────────────────────────────────────────────────────────

@app.command()
def run(
    phase: Optional[str] = typer.Option(None, "--phase", help="Run specific phase (e.g. phase_1)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would run without spawning workers"),
    master_doc: Optional[Path] = typer.Option(None, "--master-doc", help="Path to master project document"),
    fleet: Optional[str] = typer.Option(None, "--fleet", help="Madness Army fleet IPs: IP1:59000,IP2:59000"),
):
    """
    Start the 10-step phase cycle: logic check → human approval → spawn workers → report.
    """
    from .state import get_session_factory
    from .models import Project, Phase, PhaseStatus
    from .phase_cycle import PhaseCycle

    harness_json = HARNESS_DIR / "project.json"
    if not harness_json.exists():
        console.print("[bold red]✗ No harness project found.[/bold red]")
        console.print("  Run [bold]harness init --goal 'your goal'[/bold] first.")
        raise typer.Exit(1)

    project_data = json.loads(harness_json.read_text())
    project_id = project_data["project_id"]
    db_path = HARNESS_DIR / "state.db"
    session_factory = get_session_factory(db_path)

    # Load project from SQLite
    with session_factory() as db:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            console.print(f"[bold red]✗ Project {project_id} not found in DB.[/bold red]")
            raise typer.Exit(1)

        phases = project.phases
        if not phases:
            console.print("[bold red]✗ No phases found. Run harness init --phase-doc first.[/bold red]")
            raise typer.Exit(1)

        # Select target phase
        if phase:
            target_phase = next((p for p in phases if p.id == phase), None)
            if not target_phase:
                console.print(f"[bold red]✗ Phase '{phase}' not found.[/bold red]")
                raise typer.Exit(1)
        else:
            # Default: first non-done phase
            target_phase = next(
                (p for p in phases if p.status != PhaseStatus.done),
                None
            )
            if not target_phase:
                console.print("[bold green]✅ All phases already complete![/bold green]")
                raise typer.Exit(0)

        target_phase_id = target_phase.id

    if dry_run:
        console.print("[bold yellow]🔍 DRY RUN MODE — no workers will be spawned[/bold yellow]")

    console.print(f"\n[bold green]🚀 Running phase cycle: {target_phase_id}[/bold green]")

    # Handle Madness Army fleet
    if fleet:
        from .integrations.madness_army import MadnessArmyRelay
        relay_urls = [
            f"http://{addr}" if not addr.startswith("http") else addr
            for addr in fleet.split(",")
        ]
        console.print(f"  Fleet mode: {len(relay_urls)} machine(s) in Madness Army")
        # In full implementation, pass relay to PhaseCycle
        console.print(f"  Fleet URLs: {relay_urls}")

    # Create PhaseCycle and run
    cycle = PhaseCycle(
        project_id=project_id,
        db_path=db_path,
        dry_run=dry_run,
        master_doc=str(master_doc) if master_doc else None,
    )

    asyncio.run(cycle.run_phase(target_phase_id))


# ──────────────────────────────────────────────────────────────────────────────
# harness status
# ──────────────────────────────────────────────────────────────────────────────

@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full details"),
):
    """
    Show current project status: tasks, phases, workers, progress.
    """
    from .state import get_session_factory
    from .models import Project, Phase, Task, TaskStatus, PhaseStatus

    harness_json = HARNESS_DIR / "project.json"
    if not harness_json.exists():
        console.print("[bold red]✗ No harness project found.[/bold red]")
        console.print("  Run [bold]harness init --goal 'your goal'[/bold] first.")
        raise typer.Exit(1)

    project_data = json.loads(harness_json.read_text())
    project_id = project_data["project_id"]
    db_path = HARNESS_DIR / "state.db"
    session_factory = get_session_factory(db_path)

    with session_factory() as db:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            console.print(f"[bold red]✗ Project {project_id} not found in DB.[/bold red]")
            raise typer.Exit(1)

        console.print(f"\n[bold]Project:[/bold] {project.name}")
        console.print(f"[bold]Goal:[/bold]    {project.goal[:80]}{'...' if len(project.goal) > 80 else ''}")
        console.print(f"[bold]Status:[/bold]  {project.status.value}")
        console.print()

        for phase in project.phases:
            tasks = phase.tasks
            total = len(tasks)
            done = sum(1 for t in tasks if t.status == TaskStatus.done)
            failed = sum(1 for t in tasks if t.status == TaskStatus.failed)
            running = sum(1 for t in tasks if t.status == TaskStatus.running)

            # Phase header with progress bar
            progress_pct = (done / total * 100) if total > 0 else 0
            bar_filled = int(progress_pct / 5)  # 20-char bar
            bar = "█" * bar_filled + "░" * (20 - bar_filled)

            phase_color = {
                "pending": "yellow",
                "active": "green",
                "done": "bright_green",
                "failed": "red",
            }.get(phase.status.value, "white")

            console.print(
                f"[bold {phase_color}]Phase {phase.order_idx}: {phase.name}[/bold {phase_color}] "
                f"[{phase.status.value}]  [{bar}] {done}/{total} tasks  "
                f"(running: {running}, failed: {failed})"
            )

            if not tasks:
                console.print("  [italic dim]No tasks loaded[/italic dim]\n")
                continue

            # Task table
            table = Table(show_header=True, header_style="bold", padding=(0, 1))
            table.add_column("Task ID", style="cyan", no_wrap=True, width=14)
            table.add_column("Name", style="white", width=32)
            table.add_column("Status", style="bold", width=10)
            table.add_column("Model", style="magenta", width=8)
            table.add_column("Depends", style="yellow", width=16)
            table.add_column("Worker", style="green", width=10)
            table.add_column("Duration", style="dim", width=10)

            for task in tasks:
                status_color = {
                    "pending": "yellow",
                    "running": "green",
                    "done": "bright_green",
                    "failed": "red",
                    "blocked": "dim",
                }.get(task.status.value, "white")

                # Calculate duration
                duration = ""
                if task.started_at and task.completed_at:
                    delta = task.completed_at - task.started_at
                    mins = int(delta.total_seconds() // 60)
                    secs = int(delta.total_seconds() % 60)
                    duration = f"{mins}m{secs:02d}s"
                elif task.started_at:
                    delta = datetime.utcnow() - task.started_at
                    mins = int(delta.total_seconds() // 60)
                    duration = f"{mins}m (running)"

                # Worker ID from last worker
                worker_str = ""
                if task.workers:
                    last_worker = sorted(task.workers, key=lambda w: w.spawned_at)[-1]
                    worker_str = last_worker.id[:8]

                deps = json.loads(task.dependencies or "[]")
                dep_str = ", ".join(deps) if deps else "none"

                table.add_row(
                    task.id,
                    task.name[:30] + ("…" if len(task.name) > 30 else ""),
                    f"[{status_color}]{task.status.value}[/{status_color}]",
                    task.model_tier or "sonnet",
                    dep_str[:14],
                    worker_str,
                    duration,
                )

            console.print(table)
            console.print()

        # Summary line
        all_tasks = [t for p in project.phases for t in p.tasks]
        total_all = len(all_tasks)
        done_all = sum(1 for t in all_tasks if t.status == TaskStatus.done)
        failed_all = sum(1 for t in all_tasks if t.status == TaskStatus.failed)

        if total_all > 0:
            console.print(
                f"[bold]Total:[/bold] {done_all}/{total_all} done, "
                f"{failed_all} failed"
            )


# ──────────────────────────────────────────────────────────────────────────────
# harness daemon
# ──────────────────────────────────────────────────────────────────────────────

@app.command()
def daemon(
    action: str = typer.Argument("start", help="start | stop | status"),
):
    """
    Manage the Watchdog daemon (monitors workers, detects hangs).
    """
    pid_file = HARNESS_DIR / "daemon.pid"

    if action == "start":
        console.print("[bold green]Starting Watchdog daemon...[/bold green]")

        if pid_file.exists():
            old_pid = int(pid_file.read_text().strip())
            try:
                os.kill(old_pid, 0)  # Check if process exists
                console.print(f"  [yellow]⚠  Daemon already running (PID {old_pid})[/yellow]")
                raise typer.Exit(0)
            except (ProcessLookupError, PermissionError):
                # Stale PID file
                pid_file.unlink()

        # Write current PID (this process)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))

        console.print(f"  PID: {os.getpid()} written to [cyan].harness/daemon.pid[/cyan]")
        console.print()
        console.print(
            "  [dim]Watchdog daemon not yet implemented (coming v0.2)[/dim]"
        )
        console.print(
            "  [dim]In v0.2: will monitor worker heartbeats and respawn hung workers.[/dim]"
        )

    elif action == "stop":
        console.print("[bold red]Stopping Watchdog daemon...[/bold red]")
        if not pid_file.exists():
            console.print("  [yellow]No daemon PID file found — daemon not running[/yellow]")
            raise typer.Exit(0)

        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            pid_file.unlink()
            console.print(f"  ✓ Sent SIGTERM to PID {pid}")
        except ProcessLookupError:
            console.print(f"  [yellow]Process {pid} not found — removing stale PID file[/yellow]")
            pid_file.unlink()
        except PermissionError:
            console.print(f"  [red]Permission denied to kill PID {pid}[/red]")

    elif action == "status":
        console.print("[bold blue]Watchdog daemon status[/bold blue]")
        if not pid_file.exists():
            console.print("  Status: [yellow]NOT RUNNING[/yellow] (no PID file)")
        else:
            pid = int(pid_file.read_text().strip())
            try:
                os.kill(pid, 0)
                console.print(f"  Status: [green]RUNNING[/green] (PID {pid})")
            except (ProcessLookupError, PermissionError):
                console.print(f"  Status: [yellow]STALE[/yellow] (PID {pid} not found — stale PID file)")

    else:
        console.print(f"[bold red]Unknown action: {action}[/bold red]")
        console.print("  Valid actions: start | stop | status")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
