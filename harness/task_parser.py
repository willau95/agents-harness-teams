"""
Task Card Parser — parses Phase MD files into TaskCard objects.

Supports the standard Task Card format:

    ## Task N.M: Task Name
    **depends:** none  (or comma-separated task IDs)
    **model:** sonnet  (or opus)
    Description text here.
    **success_criteria:**
    - criterion 1
    - criterion 2

Parse rules:
- Task block starts at `## Task N.M: <name>`
- `**depends:**` — `none` or comma-separated task IDs
- `**model:**` — `opus` or `sonnet`
- Description = text between model line and **success_criteria:**
- Success criteria = bullet list after **success_criteria:**
- Task ends at next `## Task` or end of file
"""
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TaskCard:
    """Represents a single parsed Task Card from a Phase MD file."""
    id: str                          # e.g. "1.1", "2.3"
    name: str                        # Human-readable task name
    depends: list[str]               # List of dependency task IDs, empty if none
    model: str                       # "opus" or "sonnet"
    description: str                 # Task description text
    success_criteria: list[str]      # List of measurable criteria


# Matches the opening line of a Task Card block
TASK_HEADER_RE = re.compile(r'^## Task (\d+\.\d+):\s*(.+)$', re.MULTILINE)
# Matches **depends:** line
DEPENDS_RE = re.compile(r'^\*\*depends:\*\*\s*(.+)$', re.MULTILINE)
# Matches **model:** line
MODEL_RE = re.compile(r'^\*\*model:\*\*\s*(\w+)$', re.MULTILINE)
# Matches success_criteria header
CRITERIA_HEADER_RE = re.compile(r'^\*\*success_criteria:\*\*', re.MULTILINE)
# Matches individual criteria bullet
CRITERIA_BULLET_RE = re.compile(r'^-\s+(.+)$', re.MULTILINE)


def _parse_task_block(task_id: str, name: str, block: str) -> TaskCard:
    """Parse a single task block into a TaskCard."""

    # Parse depends
    depends_match = DEPENDS_RE.search(block)
    if depends_match:
        raw_depends = depends_match.group(1).strip()
        if raw_depends.lower() == "none":
            depends = []
        else:
            depends = [d.strip() for d in raw_depends.split(",") if d.strip()]
    else:
        depends = []

    # Parse model
    model_match = MODEL_RE.search(block)
    model = model_match.group(1).strip().lower() if model_match else "sonnet"
    if model not in ("opus", "sonnet"):
        model = "sonnet"

    # Parse success_criteria
    criteria_header = CRITERIA_HEADER_RE.search(block)
    if criteria_header:
        criteria_section = block[criteria_header.end():]
        success_criteria = CRITERIA_BULLET_RE.findall(criteria_section)
    else:
        success_criteria = []

    # Parse description: text between **model:** line and **success_criteria:**
    description = ""
    model_match2 = MODEL_RE.search(block)
    if model_match2:
        after_model = block[model_match2.end():]
        # Remove from **success_criteria:** onward
        criteria_pos = CRITERIA_HEADER_RE.search(after_model)
        if criteria_pos:
            description = after_model[:criteria_pos.start()].strip()
        else:
            description = after_model.strip()

    return TaskCard(
        id=task_id,
        name=name.strip(),
        depends=depends,
        model=model,
        description=description,
        success_criteria=success_criteria,
    )


def parse_phase_md(filepath: str) -> list[TaskCard]:
    """
    Parse a Phase Markdown file into a list of TaskCard objects.

    Args:
        filepath: Path to the Phase MD file (e.g. PHASE-1.md)

    Returns:
        List of TaskCard objects in document order.
    """
    content = Path(filepath).read_text(encoding="utf-8")
    tasks: list[TaskCard] = []

    # Find all task header positions
    headers = list(TASK_HEADER_RE.finditer(content))
    if not headers:
        return tasks

    for i, header in enumerate(headers):
        task_id = header.group(1)
        name = header.group(2)

        # Block is from end of this header line to start of next header (or EOF)
        block_start = header.end()
        block_end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        block = content[block_start:block_end]

        task = _parse_task_block(task_id, name, block)
        tasks.append(task)

    return tasks
