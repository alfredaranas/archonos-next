"""ArchonOS CLI Kernel."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from archonos.config.settings import app_dir, database_path
from archonos.core.constants import REQUIRED_DIRECTORIES
from archonos.core.version import __version__
from archonos.storage.sqlite import database_ok, initialize_database, table_count


def command_init(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    state_dir = app_dir(root)

    for directory in REQUIRED_DIRECTORIES:
        (state_dir / directory).mkdir(parents=True, exist_ok=True)

    initialize_database(database_path(root))

    print(f"ArchonOS initialized: {state_dir}")
    print(f"Database: {database_path(root)}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    db_path = database_path(root)
    db_status = "ready" if db_path.exists() and database_ok(db_path) else "missing"

    print(f"Version: {__version__}")
    print(f"Database Status: {db_status}")

    if db_status == "ready":
        print(f"Knowledge Count: {table_count(db_path, 'documents')}")
        print(f"Memory Count: {table_count(db_path, 'memories')}")
        print(f"Workflow Count: {table_count(db_path, 'workflows')}")
    else:
        print("Knowledge Count: 0")
        print("Memory Count: 0")
        print("Workflow Count: 0")

    return 0 if db_status == "ready" else 1


def command_healthcheck(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    state_dir = app_dir(root)
    db_path = database_path(root)

    checks = {
        "Filesystem": state_dir.exists() and all((state_dir / d).exists() for d in REQUIRED_DIRECTORIES),
        "Database": db_path.exists() and database_ok(db_path),
        "Configuration": (state_dir / "config").exists(),
        "Environment": sys.version_info >= (3, 11) and os.access(root, os.W_OK),
    }

    for name, ok in checks.items():
        print(f"{name}: {'ok' if ok else 'fail'}")

    return 0 if all(checks.values()) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archonos", description="ArchonOS Next CLI Kernel")
    parser.add_argument("--version", action="version", version=f"archonos {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize local ArchonOS project state")
    init_parser.add_argument("--path", default=".", help="Project path to initialize")
    init_parser.set_defaults(func=command_init)

    status_parser = subparsers.add_parser("status", help="Display local ArchonOS status")
    status_parser.add_argument("--path", default=".", help="Project path to inspect")
    status_parser.set_defaults(func=command_status)

    health_parser = subparsers.add_parser("healthcheck", help="Verify local ArchonOS environment")
    health_parser.add_argument("--path", default=".", help="Project path to inspect")
    health_parser.set_defaults(func=command_healthcheck)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
