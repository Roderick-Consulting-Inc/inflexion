# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""End-to-end test: examples/calculadora.infl.

A reverse-Polish-notation (RPN) calculator written in Inflexión.
Demonstrates a small DSL interpreter: tokenization (via char-by-char
scan), stack-based evaluation, dispatch on character (+, -, *, /),
single-digit operands.
"""
from __future__ import annotations

from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "calculadora.infl"


# Read the example once so we can vary only the source string.
EXAMPLE_TEXT = EXAMPLE.read_text(encoding="utf-8")


def _run_rpn(expression: str) -> str:
    """Run calculadora.infl with a different fuente string."""
    lines = EXAMPLE_TEXT.splitlines(keepends=True)
    lines[0] = f'La fuente es "{expression}".\n'
    return inflexion.run_source("".join(lines))


def test_canonical_expression() -> None:
    """5 1 2 + 4 * + 3 - = 5 + (1+2)*4 - 3 = 14."""
    assert inflexion.run_file(EXAMPLE).strip() == "14"


def test_addition() -> None:
    """3 4 + = 7."""
    assert _run_rpn("3 4 +").strip() == "7"


def test_subtraction() -> None:
    """9 4 - = 5."""
    assert _run_rpn("9 4 -").strip() == "5"


def test_multiplication() -> None:
    """6 7 * = 42."""
    assert _run_rpn("6 7 *").strip() == "42"


def test_division() -> None:
    """8 2 / = 4.0 (entre returns float)."""
    assert _run_rpn("8 2 /").strip() == "4.0"


def test_left_associative_chain() -> None:
    """9 5 - 2 - = (9-5)-2 = 2."""
    assert _run_rpn("9 5 - 2 -").strip() == "2"


def test_mixed_ops() -> None:
    """2 3 + 4 * = (2+3)*4 = 20."""
    assert _run_rpn("2 3 + 4 *").strip() == "20"
