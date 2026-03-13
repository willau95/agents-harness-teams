"""
harness CLI — main entry point
"""
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="harness",
    help="Universal multi-agent harness for Claude Code and OpenClaw.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def init(
    goal: str = typer.Option(..., "--goal", "-g", help="High-level project goal"),
    phase_doc: Optional[Path] = typer.Option(None, "--phase-doc", help="Path to Phase MD file with Task Cards"),
    context: Optional[str] = typer.Option(None, "--context", help="Tech stack / constraints"),
    project_dir: Path = typer.Option(Path("."), "--dir", help="Project directory (default: current)"),
):
    """
    Initialize a new harness project.
    Parses goal + phase doc into a SQLite Task tree.
    """
    console.print(f"[bold green]⚙️  Initializing harness...[/bold green]")
    console.print(f"Goal: {goal}")

    # TODO: implement
    # 1. Create .harness/ directory
    # 2. Initialize SQLite state.db
    # 3. If phase_doc provided: parse Task Cards → create Phase + Task rows
    # 4. Else: use Initializer (Opus) to decompose goal into tasks
    # 5. Generate .harness/project.json (Goal Ancestry root)
    console.print("[yellow]⚠️  Not yet implemented — coming in v0.1[/yellow]")


@app.command()
def run(
    phase: Optional[str] = typer.Option(None, "--phase", help="Run specific phase only"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would run without spawning workers"),
):
    """
    Start the harness: spawn workers, run tasks, monitor progress.
    """
    console.print("[bold green]🚀 Starting harness...[/bold green]")
    # TODO: implement
    # 1. Start Watchdog daemon
    # 2. Load Orchestrator Brain
    # 3. Read pending tasks from SQLite
    # 4. Spawn workers for ready tasks
    console.print("[yellow]⚠️  Not yet implemented — coming in v0.1[/yellow]")


@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """
    Show current project status: tasks, workers, progress.
    """
    # TODO: implement
    table = Table(title="Harness Status")
    table.add_column("Task", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("Worker", style="green")
    table.add_column("Duration")
    console.print("[yellow]⚠️  Not yet implemented — coming in v0.1[/yellow]")
    console.print(table)


@app.command()
def daemon(
    action: str = typer.Argument("start", help="start | stop | status"),
):
    """
    Manage the Watchdog daemon (monitors workers, detects hangs).
    """
    if action == "start":
        console.print("[bold green]Starting Watchdog daemon...[/bold green]")
        # TODO: fork daemon process, write PID to .harness/daemon.pid
    elif action == "stop":
        console.print("[bold red]Stopping Watchdog daemon...[/bold red]")
    elif action == "status":
        console.print("[bold blue]Watchdog daemon status[/bold blue]")
    console.print("[yellow]⚠️  Not yet implemented — coming in v0.1[/yellow]")


if __name__ == "__main__":
    app()
