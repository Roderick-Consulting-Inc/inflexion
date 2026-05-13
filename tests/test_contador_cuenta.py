# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 3b end-to-end tests: arithmetic + `mientras` + negated condition."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import inflexion
from inflexion.interpreter import (
    MAX_MIENTRAS_ITERATIONS,
    InflexionRuntimeError,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "contador-cuenta.infl"


def test_contador_cuenta_run_file() -> None:
    """Programmatic API: the counter loops down to 0 and prints `0`."""
    assert inflexion.run_file(EXAMPLE) == "0\n"


def test_contador_cuenta_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/contador-cuenta.infl` prints `0\\n`."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "0\n"
    assert result.returncode == 0


def test_arithmetic_in_decir() -> None:
    """`Decí el total más 3` evaluates and prints the arithmetic result."""
    source = "El total es 5.\nDecí el total más 3.\n"
    assert inflexion.run_source(source) == "8\n"


def test_arithmetic_menos_with_literal_left() -> None:
    """`menos` with a literal on the left and a binding on the right also works."""
    source = "El delta es 2.\nEl total está en 10.\nDecí el total menos el delta.\n"
    assert inflexion.run_source(source) == "8\n"


def test_arithmetic_in_estar_binding() -> None:
    """Arithmetic may appear on the right of an estar binding."""
    source = (
        "El base es 4.\n"
        "El total está en el base más 6.\n"
        "Decí el total.\n"
    )
    assert inflexion.run_source(source) == "10\n"


def test_mientras_runaway_raises_safety_cap() -> None:
    """A `Mientras` whose condition can never become false hits the safety cap."""
    # Counter starts at 1 and increments — never reaches 0, would loop forever.
    source = (
        "El contador está en 1.\n"
        "Mientras el contador no esté en 0, hacé que el contador esté en "
        "el contador más 1.\n"
    )
    with pytest.raises(InflexionRuntimeError, match="safety cap"):
        inflexion.run_source(source)


def test_mientras_safety_cap_value() -> None:
    """The safety cap is the documented MAX_MIENTRAS_ITERATIONS (100_000)."""
    assert MAX_MIENTRAS_ITERATIONS == 100_000


def test_mientras_fires_cuando_mid_loop() -> None:
    """A `Cuando` observer fires when the loop variable transits the trigger."""
    # Counter ticks down 5 → 0. The Cuando on 2 should fire exactly once
    # as the loop crosses 2, *before* the loop terminates at 0.
    source = (
        "El contador está en 5.\n"
        'Cuando el contador esté en 2, decí "dos".\n'
        "Mientras el contador no esté en 0, hacé que el contador esté en "
        "el contador menos 1.\n"
        "Decí el contador.\n"
    )
    assert inflexion.run_source(source) == "dos\n0\n"
