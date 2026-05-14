# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 7 end-to-end tests: examples/sieve.infl.

The sieve program uses a 1-indexed criba list (indices 0–50, index 0
intentionally 0) and manually sieves multiples of 2, 3, and 5 with
Mientras loops, then zeroes index 49 (= 7²) explicitly — the only prime-
square ≤ 50 not covered by those three sweeps.  It then walks i = 2..50
and prints every index whose criba cell is still 1.

Expected primes ≤ 50: [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "sieve.infl"

PRIMES_TO_50 = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]
EXPECTED_OUTPUT = "".join(f"{p}\n" for p in PRIMES_TO_50)

# Composites ≤ 50 that should NOT appear in the output.
COMPOSITES_TO_50 = [
    n for n in range(2, 51)
    if n not in PRIMES_TO_50
]


def test_sieve_run_file() -> None:
    """Programmatic API: sieve.infl produces exactly 15 output lines."""
    output = inflexion.run_file(EXAMPLE)
    assert len(output.splitlines()) == 15


def test_sieve_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/sieve.infl`."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 15


def test_sieve_exact_output() -> None:
    """Full output matches the canonical 15-prime sequence exactly."""
    assert inflexion.run_file(EXAMPLE) == EXPECTED_OUTPUT


def test_sieve_first_prime_is_2() -> None:
    """First output line is 2 (smallest prime)."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    assert lines[0] == "2"


def test_sieve_last_prime_is_47() -> None:
    """Last output line is 47 (largest prime ≤ 50)."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    assert lines[-1] == "47"


def test_sieve_contains_all_primes_to_50() -> None:
    """Every prime ≤ 50 appears in the output."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    numbers = [int(ln) for ln in lines]
    for p in PRIMES_TO_50:
        assert p in numbers, f"prime {p} missing from output"


def test_sieve_excludes_composites() -> None:
    """No composite number ≤ 50 appears in the output."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    numbers = set(int(ln) for ln in lines)
    for c in COMPOSITES_TO_50:
        assert c not in numbers, f"composite {c} incorrectly included"


def test_sieve_excludes_1() -> None:
    """1 does not appear: index 1 is initialised to 1 but the print loop starts at i=2."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    assert "1" not in lines


def test_sieve_output_is_integers_not_floats() -> None:
    """All output lines parse as integers (no decimal point)."""
    for line in inflexion.run_file(EXAMPLE).splitlines():
        assert "." not in line, f"float output detected: {line!r}"
        int(line)  # raises ValueError if not a valid integer string


def test_sieve_49_excluded() -> None:
    """49 (= 7²) is correctly excluded — the program zeroes it explicitly."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    assert "49" not in lines
