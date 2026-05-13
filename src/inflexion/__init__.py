# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión interpreter — Phase 1 vertical slice.

Public API surface (Phase 1):
    - run_source(source: str) -> str: parse + interpret an Inflexión source string,
      returning captured stdout.
    - run_file(path: str | Path) -> str: same, reading from a `.infl` file.
"""
from __future__ import annotations

from pathlib import Path

from .interpreter import Environment, run as _run_program
from .lexer import lex
from .parser import parse

__version__ = "0.0.2"

__all__ = ["run_source", "run_file", "__version__"]


def run_source(source: str) -> str:
    """Parse and execute Inflexión source text, returning captured stdout."""
    tokens, strings = lex(source)
    program = parse(tokens, strings)
    return _run_program(program, Environment())


def run_file(path: str | Path) -> str:
    """Parse and execute an Inflexión `.infl` file, returning captured stdout."""
    text = Path(path).read_text(encoding="utf-8")
    return run_source(text)
