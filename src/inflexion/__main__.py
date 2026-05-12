# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión CLI entry point.

Usage:
    python -m inflexion run <file.infl>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, run_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="inflexion",
        description="Inflexión interpreter — Phase 1 vertical slice.",
    )
    parser.add_argument("--version", action="version", version=f"inflexion {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    run_cmd = sub.add_parser("run", help="Run an Inflexión .infl source file.")
    run_cmd.add_argument("path", type=Path, help="Path to the .infl file to execute.")

    args = parser.parse_args(argv)

    if args.command == "run":
        output = run_file(args.path)
        sys.stdout.write(output)
        return 0

    parser.error(f"Unknown command: {args.command!r}")
    return 2  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
