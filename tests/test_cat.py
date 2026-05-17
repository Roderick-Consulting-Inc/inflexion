# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""End-to-end test: examples/cat.infl.

A cat program — reads a line from stdin and writes it to stdout. The
shortest non-trivial Inflexión program that exercises stdin + decí.
"""
from __future__ import annotations

from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "cat.infl"
SOURCE = EXAMPLE.read_text(encoding="utf-8")


def test_cat_simple_line() -> None:
    """A line of text is echoed verbatim plus the newline from `decí`."""
    assert inflexion.run_source(SOURCE, stdin="hola mundo") == "hola mundo\n"


def test_cat_empty_line() -> None:
    """An empty stdin produces just the trailing newline from decí."""
    assert inflexion.run_source(SOURCE, stdin="") == "\n"


def test_cat_unicode() -> None:
    """Unicode text passes through unchanged."""
    assert inflexion.run_source(SOURCE, stdin="¿Cómo estás?") == "¿Cómo estás?\n"
