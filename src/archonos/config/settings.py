"""Local settings helpers for ArchonOS."""

from __future__ import annotations

from pathlib import Path

from archonos.core.constants import APP_DIR, DB_NAME


def project_root(path: str | Path | None = None) -> Path:
    """Return the project root used for local ArchonOS state."""
    return Path(path or Path.cwd()).resolve()


def app_dir(path: str | Path | None = None) -> Path:
    """Return the .archonos directory for a project."""
    return project_root(path) / APP_DIR


def database_path(path: str | Path | None = None) -> Path:
    """Return the SQLite database path for a project."""
    return app_dir(path) / DB_NAME
