# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 7 end-to-end tests: Fibonacci programs.

Covers examples/fibonacci-iterativo.infl (Phase 7a) and, once committed,
examples/fibonacci-recursivo.infl (Phase 7b).

Sequential-not-atomic invariant (iterativo)
-------------------------------------------
The iterativo program relies on the Phase 7a *y-que* sequential mutation
semantics.  In the single statement::

    hacé que el b esté en el a más el b
        y que el a esté en el b menos el a
        y que el i esté en el i más 1.

mutations are applied left-to-right, each RHS seeing already-updated LHS
values.  Starting from (a, b) = (F(k), F(k+1)):

  1. b ← a + b  =  F(k) + F(k+1) = F(k+2)          (new b)
  2. a ← b - a  =  F(k+2) − F(k) = F(k+1)          (new a, using new b)

After each iteration j the invariant (a, b) = (F(j+1), F(j+2)) holds.
After 10 iterations starting from (F(0), F(1)) = (0, 1), a = F(10) = 55.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
ITERATIVO = REPO_ROOT / "examples" / "fibonacci-iterativo.infl"

# ---------------------------------------------------------------------------
# fibonacci-iterativo tests
# ---------------------------------------------------------------------------

EXPECTED_FIB10 = "55\n"


def test_fibonacci_iterativo_run_file() -> None:
    """Programmatic API: fibonacci-iterativo.infl prints F(10) = 55."""
    assert inflexion.run_file(ITERATIVO) == EXPECTED_FIB10


def test_fibonacci_iterativo_run_source() -> None:
    """Source-string API: same 10-iteration program via inline source."""
    source = (
        "El a está en 0.\n"
        "El b está en 1.\n"
        "El i está en 0.\n"
        "Mientras el i no esté en 10, hacé que el b esté en el a más el b "
        "y que el a esté en el b menos el a y que el i esté en el i más 1.\n"
        "Decí el a.\n"
    )
    assert inflexion.run_source(source) == EXPECTED_FIB10


def test_fibonacci_iterativo_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/fibonacci-iterativo.infl`."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(ITERATIVO)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == EXPECTED_FIB10
    assert result.returncode == 0


def test_fibonacci_iterativo_integer_not_float() -> None:
    """F(10) must render as the integer 55, not the float 55.0."""
    result = inflexion.run_file(ITERATIVO)
    assert "." not in result, f"Expected integer output, got: {result!r}"
    assert result.strip() == "55"


def test_fibonacci_iterativo_zero_iterations() -> None:
    """With loop bound 0 (i starts at 0, terminates immediately) a stays 0 = F(0)."""
    source = (
        "El a está en 0.\n"
        "El b está en 1.\n"
        "El i está en 0.\n"
        "Mientras el i no esté en 0, hacé que el b esté en el a más el b "
        "y que el a esté en el b menos el a y que el i esté en el i más 1.\n"
        "Decí el a.\n"
    )
    assert inflexion.run_source(source) == "0\n"


def test_fibonacci_iterativo_one_iteration() -> None:
    """One iteration: (a, b) = (F(0), F(1)) → (F(1), F(2)) = (1, 1); a = 1."""
    source = (
        "El a está en 0.\n"
        "El b está en 1.\n"
        "El i está en 0.\n"
        "Mientras el i no esté en 1, hacé que el b esté en el a más el b "
        "y que el a esté en el b menos el a y que el i esté en el i más 1.\n"
        "Decí el a.\n"
    )
    assert inflexion.run_source(source) == "1\n"


def test_fibonacci_iterativo_two_iterations() -> None:
    """Two iterations: a = F(2) = 1."""
    source = (
        "El a está en 0.\n"
        "El b está en 1.\n"
        "El i está en 0.\n"
        "Mientras el i no esté en 2, hacé que el b esté en el a más el b "
        "y que el a esté en el b menos el a y que el i esté en el i más 1.\n"
        "Decí el a.\n"
    )
    assert inflexion.run_source(source) == "1\n"


def test_fibonacci_iterativo_sequential_swap_produces_fib6() -> None:
    """Six iterations: a = F(6) = 8.  Validates the swap invariant mid-sequence."""
    source = (
        "El a está en 0.\n"
        "El b está en 1.\n"
        "El i está en 0.\n"
        "Mientras el i no esté en 6, hacé que el b esté en el a más el b "
        "y que el a esté en el b menos el a y que el i esté en el i más 1.\n"
        "Decí el a.\n"
    )
    assert inflexion.run_source(source) == "8\n"


# ---------------------------------------------------------------------------
# fibonacci-recursivo tests (Phase 7b)
# ---------------------------------------------------------------------------

RECURSIVO = REPO_ROOT / "examples" / "fibonacci-recursivo.infl"

# Shared inline recursive definition used by base-case tests below.
_FIB_DEF = (
    "La función fib, que toma un n, es "
    "si el n es 0, entonces 0; "
    "sino, si el n es 1, entonces 1; "
    "sino, fib (el n menos 1) más fib (el n menos 2).\n"
)


def test_fibonacci_recursivo_run_file() -> None:
    """Programmatic API: fibonacci-recursivo.infl prints F(10) = 55."""
    assert inflexion.run_file(RECURSIVO) == EXPECTED_FIB10


def test_fibonacci_recursivo_run_source() -> None:
    """Source-string API: same recursive definition via inline source."""
    source = _FIB_DEF + "El resultado es fib 10.\nDecí el resultado.\n"
    assert inflexion.run_source(source) == EXPECTED_FIB10


def test_fibonacci_recursivo_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/fibonacci-recursivo.infl`."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(RECURSIVO)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == EXPECTED_FIB10
    assert result.returncode == 0


def test_fibonacci_recursivo_integer_not_float() -> None:
    """F(10) must render as integer 55, not float 55.0."""
    result = inflexion.run_file(RECURSIVO)
    assert "." not in result, f"Expected integer output, got: {result!r}"
    assert result.strip() == "55"


def test_fibonacci_recursivo_base_case_zero() -> None:
    """fib(0) = 0 — first base case of the recursive definition."""
    source = _FIB_DEF + "El resultado es fib 0.\nDecí el resultado.\n"
    assert inflexion.run_source(source) == "0\n"


def test_fibonacci_recursivo_base_case_one() -> None:
    """fib(1) = 1 — second base case of the recursive definition."""
    source = _FIB_DEF + "El resultado es fib 1.\nDecí el resultado.\n"
    assert inflexion.run_source(source) == "1\n"


def test_fibonacci_recursivo_fib2() -> None:
    """fib(2) = fib(1) + fib(0) = 1 — first non-trivial recursive call."""
    source = _FIB_DEF + "El resultado es fib 2.\nDecí el resultado.\n"
    assert inflexion.run_source(source) == "1\n"


def test_fibonacci_recursivo_fib6() -> None:
    """fib(6) = 8 — agrees with the iterativo spot-check at six steps."""
    source = _FIB_DEF + "El resultado es fib 6.\nDecí el resultado.\n"
    assert inflexion.run_source(source) == "8\n"


def test_fibonacci_iterativo_and_recursivo_agree() -> None:
    """Both variants produce the same value for F(10)."""
    assert inflexion.run_file(ITERATIVO) == inflexion.run_file(RECURSIVO)
