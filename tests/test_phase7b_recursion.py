# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 7b tests: recursive function calls with parenthesised arguments.

Covers:
    - Factorial (recursive, base-case via si-entonces-sino expression)
    - Fibonacci (double recursion)
    - Late binding: the function sees itself from within its own body
"""
from __future__ import annotations

import inflexion


# ---------------------------------------------------------------------------
# Factorial
# ---------------------------------------------------------------------------

_FACT_DEF = (
    "La función fact, que toma un n, es "
    "si el n es 0, entonces 1; sino, el n por fact (el n menos 1).\n"
)


def test_factorial_0() -> None:
    """fact(0) = 1 (base case)."""
    src = _FACT_DEF + "El resultado es fact 0.\nDecí el resultado.\n"
    assert inflexion.run_source(src) == "1\n"


def test_factorial_1() -> None:
    """fact(1) = 1."""
    src = _FACT_DEF + "El resultado es fact 1.\nDecí el resultado.\n"
    assert inflexion.run_source(src) == "1\n"


def test_factorial_5() -> None:
    """fact(5) = 120."""
    src = _FACT_DEF + "El resultado es fact 5.\nDecí el resultado.\n"
    assert inflexion.run_source(src) == "120\n"


def test_factorial_10() -> None:
    """fact(10) = 3628800."""
    src = _FACT_DEF + "El resultado es fact 10.\nDecí el resultado.\n"
    assert inflexion.run_source(src) == "3628800\n"


# ---------------------------------------------------------------------------
# Fibonacci
# ---------------------------------------------------------------------------

_FIB_DEF = (
    "La función fib, que toma un n, es "
    "si el n es 0, entonces 0; sino, "
    "si el n es 1, entonces 1; sino, "
    "fib (el n menos 1) más fib (el n menos 2).\n"
)


def test_fibonacci_0() -> None:
    """fib(0) = 0."""
    src = _FIB_DEF + "El r es fib 0.\nDecí el r.\n"
    assert inflexion.run_source(src) == "0\n"


def test_fibonacci_1() -> None:
    """fib(1) = 1."""
    src = _FIB_DEF + "El r es fib 1.\nDecí el r.\n"
    assert inflexion.run_source(src) == "1\n"


def test_fibonacci_5() -> None:
    """fib(5) = 5."""
    src = _FIB_DEF + "El r es fib 5.\nDecí el r.\n"
    assert inflexion.run_source(src) == "5\n"


def test_fibonacci_10() -> None:
    """fib(10) = 55."""
    src = _FIB_DEF + "El r es fib 10.\nDecí el r.\n"
    assert inflexion.run_source(src) == "55\n"


# ---------------------------------------------------------------------------
# Parenthesised arg in arithmetic context
# ---------------------------------------------------------------------------


def test_paren_arg_arithmetic() -> None:
    """(el n menos 1) inside a call works with arithmetic."""
    src = (
        _FACT_DEF
        + "El n es 4.\n"
        "El r es fact (el n menos 1).\n"
        "Decí el r.\n"
    )
    # fact(3) = 6
    assert inflexion.run_source(src) == "6\n"


def test_paren_grouping_standalone() -> None:
    """(expr) grouping in plain arithmetic works without a function call."""
    src = (
        "El a es 3.\n"
        "El b es 2.\n"
        "El r es el a por (el a más el b).\n"
        "Decí el r.\n"
    )
    # 3 * (3 + 2) = 15
    assert inflexion.run_source(src) == "15\n"
