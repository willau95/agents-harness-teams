"""
Database models for agents-harness-teams.
State stored in SQLite (.harness/state.db) — zero external dependencies.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class ProjectStatus(str, Enum):
    active = "active"
    paused = "paused"
    done = "done"


class PhaseStatus(str, Enum):
    pending = "pending"
    active = "active"
    done = "done"
    failed = "failed"


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    blocked = "blocked"  # waiting on dependency


class WorkerStatus(str, Enum):
    spawning = "spawning"
    running = "running"
    done = "done"
    hung = "hung"
    killed = "killed"


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True)          # e.g. "proj_llachat"
    name = Column(String, nullable=False)
    goal = Column(Text, nullable=False)             # High-level user goal
    tech_context = Column(Text)                     # Tech stack, constraints
    status = Column(SAEnum(ProjectStatus), default=ProjectStatus.active)
    created_at = Column(DateTime, default=datetime.utcnow)

    phases = relationship("Phase", back_populates="project", order_by="Phase.order_idx")


class Phase(Base):
    __tablename__ = "phases"

    id = Column(String, primary_key=True)           # e.g. "phase_1"
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    objective = Column(Text)
    order_idx = Column(Integer, nullable=False)
    status = Column(SAEnum(PhaseStatus), default=PhaseStatus.pending)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    project = relationship("Project", back_populates="phases")
    tasks = relationship("Task", back_populates="phase", order_by="Task.order_idx")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)           # e.g. "task_1_1"
    phase_id = Column(String, ForeignKey("phases.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    success_criteria = Column(Text, nullable=False) # JSON array of criteria strings
    dependencies = Column(Text)                     # JSON array of task_ids
    model_tier = Column(String, default="sonnet")   # opus / sonnet / haiku
    order_idx = Column(Integer, nullable=False)
    status = Column(SAEnum(TaskStatus), default=TaskStatus.pending)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    result_summary = Column(Text)
    artifacts = Column(Text)                        # JSON array of file paths
    worker_session_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    phase = relationship("Phase", back_populates="tasks")
    workers = relationship("Worker", back_populates="task")


class Worker(Base):
    __tablename__ = "workers"

    id = Column(String, primary_key=True)           # UUID
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    session_id = Column(String)                     # Claude Code session ID
    pid = Column(Integer)                           # Process ID
    status = Column(SAEnum(WorkerStatus), default=WorkerStatus.spawning)
    last_heartbeat_at = Column(DateTime)
    spawned_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    task = relationship("Task", back_populates="workers")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, ForeignKey("tasks.id"))
    worker_id = Column(String, ForeignKey("workers.id"))
    event_type = Column(String, nullable=False)     # TASK_STARTED / TASK_COMPLETE / TASK_FAILED / WORKER_HUNG / WORKER_RESPAWNED
    payload = Column(Text)                          # JSON
    created_at = Column(DateTime, default=datetime.utcnow)
