"""
Notifier — sends user notifications when phases complete or escalation needed.
Supports: terminal output, OpenClaw system event, macOS notification.
"""
import os
import subprocess
import logging

logger = logging.getLogger(__name__)


def notify(message: str, level: str = "info"):
    """
    Send a notification to the user.
    Tries OpenClaw system event first, falls back to terminal print.
    """
    print(f"\n{'✅' if level == 'info' else '⚠️' if level == 'warning' else '⛔'} [agents-harness-teams] {message}\n")

    # Try OpenClaw notification (if openclaw is in PATH)
    _try_openclaw_notify(message, level)

    # Try macOS notification center
    _try_macos_notify(message, level)


def _try_openclaw_notify(message: str, level: str):
    """Send via openclaw system event if available."""
    try:
        result = subprocess.run(
            ["openclaw", "system", "event", "--text", message, "--mode", "now"],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            logger.debug("[Notifier] OpenClaw notification sent.")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _try_macos_notify(message: str, level: str):
    """Send macOS notification if on macOS."""
    if os.uname().sysname != "Darwin":
        return
    try:
        title = "agents-harness-teams"
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            capture_output=True, timeout=3
        )
    except Exception:
        pass
