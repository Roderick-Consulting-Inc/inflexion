# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión interpreter — top-level package.

Public API (stable since Phase 1):
    - run_source(source: str, *, stdin: str = "") -> str: parse + interpret
      an Inflexión source string, returning captured stdout.  The optional
      keyword-only `stdin` argument supplies the text that `Escuchá` reads
      from (Phase 7c); newlines separate lines.
    - run_file(path: str | Path, *, stdin: str = "") -> str: same, from file.

The phase history is documented in each module's docstring; v0.0.7
corresponds to Phase 6 (diminutive scaling + aspect-marked lazy),
which closes the six-mapping curriculum of paper §3. Phase 7 (control
flow, recursion, string/list ops, stdin) is in-progress.
"""
from __future__ import annotations

from pathlib import Path

from .interpreter import Environment, run as _run_program
from .lexer import lex
from .parser import parse

__version__ = "0.0.12"

__all__ = ["run_source", "run_file", "__version__"]


def run_source(source: str, *, stdin: str = "") -> str:
    """Parse and execute Inflexión source text, returning captured stdout.

    Parameters
    ----------
    source:
        Inflexión source text.
    stdin:
        Optional stdin content for `Escuchá` reads (Phase 7c). Each
        line of `stdin` is consumed in order by successive `Escuchá`
        statements. Passing an empty string (the default) means stdin is
        empty; an `Escuchá` on an empty buffer returns the empty string.
    """
    tokens, strings = lex(source)
    program = parse(tokens, strings)
    env = Environment(stdin_lines=stdin.splitlines())
    return _run_program(program, env)


def run_file(path: str | Path, *, stdin: str = "") -> str:
    """Parse and execute an Inflexión `.infl` file, returning captured stdout."""
    text = Path(path).read_text(encoding="utf-8")
    return run_source(text, stdin=stdin)
