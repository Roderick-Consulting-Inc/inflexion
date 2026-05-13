# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 2 end-to-end tests: estar bindings, mutation, and `Decí` with NP."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import inflexion
from inflexion.interpreter import InflexionRuntimeError

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "contador.infl"


def test_contador_run_file() -> None:
    """Programmatic API: the contador example prints `1\\n`."""
    assert inflexion.run_file(EXAMPLE) == "1\n"


def test_contador_run_source() -> None:
    """Source-string API: same result as the file."""
    source = (
        "El contador está en 0.\n"
        "Hacé que el contador esté en 1.\n"
        "Decí el contador.\n"
    )
    assert inflexion.run_source(source) == "1\n"


def test_contador_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/contador.infl` prints `1\\n`."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "1\n"
    assert result.returncode == 0


def test_mutation_of_ser_binding_raises() -> None:
    """Mutating a *ser* (immutable) binding is a runtime error."""
    source = "El total es 100.\nHacé que el total esté en 200.\n"
    with pytest.raises(InflexionRuntimeError, match="immutable"):
        inflexion.run_source(source)


def test_estar_multi_mutation() -> None:
    """A mutable binding accepts repeated mutation and reads the latest value."""
    source = (
        "El contador está en 0.\n"
        "Hacé que el contador esté en 5.\n"
        "Hacé que el contador esté en 7.\n"
        "Decí el contador.\n"
    )
    assert inflexion.run_source(source) == "7\n"
