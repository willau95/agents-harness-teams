"""
Tests for harness/task_parser.py

Run with: pytest tests/test_task_parser.py -v
"""
import tempfile
import os
import pytest
from harness.task_parser import parse_phase_md, TaskCard

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def write_temp_md(content: str) -> str:
    """Write content to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Test Case 1: Single task with no dependencies
# ──────────────────────────────────────────────────────────────────────────────

SINGLE_TASK_MD = """\
# Phase 1: Hello World

**Project:** Test
**Objective:** Say hello

---

## Task 1.1: Create hello.py

**depends:** none
**model:** sonnet

Create a Python file hello.py that prints "Hello, World!".

**success_criteria:**
- hello.py exists in the project root
- `python hello.py` outputs "Hello, World!"
"""


def test_parse_single_task():
    path = write_temp_md(SINGLE_TASK_MD)
    try:
        tasks = parse_phase_md(path)

        assert len(tasks) == 1
        task = tasks[0]

        assert task.id == "1.1"
        assert task.name == "Create hello.py"
        assert task.depends == []
        assert task.model == "sonnet"
        assert "hello.py" in task.description
        assert len(task.success_criteria) == 2
        assert "hello.py exists in the project root" in task.success_criteria[0]
        assert 'python hello.py' in task.success_criteria[1]
    finally:
        os.unlink(path)


# ──────────────────────────────────────────────────────────────────────────────
# Test Case 2: Multiple tasks with dependencies
# ──────────────────────────────────────────────────────────────────────────────

MULTI_TASK_MD = """\
# Phase 2: API Setup

---

## Task 2.1: Initialize project

**depends:** none
**model:** opus

Set up the project directory and virtual environment.

**success_criteria:**
- Directory `src/` exists
- `pyproject.toml` exists

---

## Task 2.2: Install dependencies

**depends:** 2.1
**model:** sonnet

Install required Python packages.

**success_criteria:**
- `pip install -e .` exits with code 0
- `import fastapi` works in Python REPL

---

## Task 2.3: Create main.py

**depends:** 2.1, 2.2
**model:** sonnet

Create the FastAPI application entry point.

**success_criteria:**
- `src/main.py` exists
- `uvicorn src.main:app` starts without errors
- HTTP GET / returns status 200
"""


def test_parse_multiple_tasks_with_dependencies():
    path = write_temp_md(MULTI_TASK_MD)
    try:
        tasks = parse_phase_md(path)

        assert len(tasks) == 3

        # Task 2.1
        t1 = tasks[0]
        assert t1.id == "2.1"
        assert t1.name == "Initialize project"
        assert t1.depends == []
        assert t1.model == "opus"
        assert len(t1.success_criteria) == 2

        # Task 2.2
        t2 = tasks[1]
        assert t2.id == "2.2"
        assert t2.depends == ["2.1"]
        assert t2.model == "sonnet"

        # Task 2.3 — multiple dependencies
        t3 = tasks[2]
        assert t3.id == "2.3"
        assert t3.depends == ["2.1", "2.2"]
        assert len(t3.success_criteria) == 3
    finally:
        os.unlink(path)


# ──────────────────────────────────────────────────────────────────────────────
# Test Case 3: Edge cases — empty file, unknown model, missing criteria
# ──────────────────────────────────────────────────────────────────────────────

EDGE_CASE_MD = """\
# Phase 3: Edge Cases

## Task 3.1: Task with unknown model

**depends:** none
**model:** gpt-4

Some description here.

**success_criteria:**
- At least one criterion

## Task 3.2: Task with no success_criteria section

**depends:** 3.1
**model:** sonnet

A task missing the success criteria block entirely.

## Task 3.3: Task with many depends

**depends:** 3.1, 3.2
**model:** opus

A task depending on two previous tasks.

**success_criteria:**
- File output.txt exists
"""

EMPTY_MD = """\
# Phase 4: No tasks here

Just some text with no task cards.
"""


def test_parse_edge_cases():
    # Test unknown model defaults to sonnet
    path = write_temp_md(EDGE_CASE_MD)
    try:
        tasks = parse_phase_md(path)
        assert len(tasks) == 3

        # Unknown model should default to sonnet
        assert tasks[0].model == "sonnet"

        # Missing success_criteria → empty list
        assert tasks[1].success_criteria == []

        # Multiple depends parsed correctly
        assert tasks[2].depends == ["3.1", "3.2"]
        assert tasks[2].model == "opus"
        assert len(tasks[2].success_criteria) == 1
    finally:
        os.unlink(path)

    # Test empty file (no task cards)
    path2 = write_temp_md(EMPTY_MD)
    try:
        tasks2 = parse_phase_md(path2)
        assert tasks2 == []
    finally:
        os.unlink(path2)
