"""
State — SQLite database initialization and session management.
Zero external dependencies: uses Python's built-in sqlite3 via SQLAlchemy.
"""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base

HARNESS_DIR = Path(".harness")
DB_PATH = HARNESS_DIR / "state.db"


def get_engine(db_path: Path = DB_PATH):
    """Create SQLAlchemy engine for the local SQLite state database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def init_db(db_path: Path = DB_PATH):
    """Initialize the database schema."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine


def get_session_factory(db_path: Path = DB_PATH):
    """Get a session factory for database operations."""
    engine = get_engine(db_path)
    return sessionmaker(bind=engine)
