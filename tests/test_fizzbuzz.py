# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 7 end-to-end tests: examples/fizzbuzz.infl.

The program uses a single Mientras sentence with nested Si dispatch to
print the canonical FizzBuzz sequence from 1 to 100.  Priority order is
FizzBuzz (÷15) → Fizz (÷3) → Buzz (÷5) → integer, which is the correct
cascade.  The loop body ends with a y-que mutation (`y que el i esté en
el i más 1`) — a Phase 7a multi-clause mientras construct.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "fizzbuzz.infl"


def _canonical_fizzbuzz(n: int) -> str:
    """Return the canonical FizzBuzz label for integer n (1-indexed)."""
    if n % 15 == 0:
        return "FizzBuzz"
    if n % 3 == 0:
        return "Fizz"
    if n % 5 == 0:
        return "Buzz"
    return str(n)


CANONICAL_100 = [_canonical_fizzbuzz(n) for n in range(1, 101)]


def test_fizzbuzz_run_file() -> None:
    """Programmatic API: fizzbuzz.infl produces exactly 100 output lines."""
    output = inflexion.run_file(EXAMPLE)
    lines = output.splitlines()
    assert len(lines) == 100


def test_fizzbuzz_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/fizzbuzz.infl`."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 100


def test_fizzbuzz_first_20_lines() -> None:
    """First 20 output lines match the canonical FizzBuzz pattern exactly."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    assert lines[:20] == CANONICAL_100[:20]


def test_fizzbuzz_full_100_lines() -> None:
    """All 100 output lines match the canonical pattern."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    assert lines == CANONICAL_100


def test_fizzbuzz_line_3_fizz() -> None:
    """Line 3 (n=3, ÷3) → 'Fizz'."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    assert lines[2] == "Fizz"


def test_fizzbuzz_line_5_buzz() -> None:
    """Line 5 (n=5, ÷5) → 'Buzz'."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    assert lines[4] == "Buzz"


def test_fizzbuzz_line_15_fizzbuzz() -> None:
    """Line 15 (n=15, ÷3 and ÷5) → 'FizzBuzz' (priority: ÷15 first)."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    assert lines[14] == "FizzBuzz"


def test_fizzbuzz_line_30_fizzbuzz() -> None:
    """Line 30 (n=30, ÷15) → 'FizzBuzz'."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    assert lines[29] == "FizzBuzz"


def test_fizzbuzz_line_100_buzz() -> None:
    """Line 100 (n=100, ÷5 but not ÷3) → 'Buzz'."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    assert lines[99] == "Buzz"


def test_fizzbuzz_no_fizzbuzz_at_non_multiples_of_15() -> None:
    """'FizzBuzz' appears only at multiples of 15 (lines 15, 30, 45, 60, 75, 90)."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    fizzbuzz_positions = [i + 1 for i, line in enumerate(lines) if line == "FizzBuzz"]
    assert fizzbuzz_positions == [15, 30, 45, 60, 75, 90]


def test_fizzbuzz_no_composites_labelled_fizz() -> None:
    """'Fizz' never appears at a position that is NOT a multiple of 3."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    for i, line in enumerate(lines):
        n = i + 1
        if line == "Fizz":
            assert n % 3 == 0, f"n={n} labelled Fizz but not divisible by 3"
            assert n % 5 != 0, f"n={n} labelled Fizz but should be FizzBuzz"
