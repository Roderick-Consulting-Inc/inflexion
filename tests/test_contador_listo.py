# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 3a end-to-end tests: subjunctive deferred bindings (`Cuando … decí …`)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "contador-listo.infl"


def test_contador_listo_run_file() -> None:
    """Programmatic API: the deferred binding fires on the matching mutation."""
    assert inflexion.run_file(EXAMPLE) == "listo\n"


def test_contador_listo_run_source() -> None:
    """Source-string API: same result as the file."""
    source = (
        'El contador está en 0.\n'
        'Cuando el contador esté en 5, decí "listo".\n'
        "Hacé que el contador esté en 5.\n"
    )
    assert inflexion.run_source(source) == "listo\n"


def test_contador_listo_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/contador-listo.infl` prints `listo\\n`."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "listo\n"
    assert result.returncode == 0


def test_cuando_does_not_fire_when_trigger_unmet() -> None:
    """A deferred binding stays silent if the trigger value is never reached."""
    source = (
        'El contador está en 0.\n'
        'Cuando el contador esté en 5, decí "listo".\n'
        "Hacé que el contador esté en 4.\n"
    )
    assert inflexion.run_source(source) == ""


def test_multiple_cuando_clauses_fire_independently() -> None:
    """Two observers on the same name, with different triggers, fire independently."""
    source = (
        'El contador está en 0.\n'
        'Cuando el contador esté en 3, decí "tres".\n'
        'Cuando el contador esté en 5, decí "cinco".\n'
        "Hacé que el contador esté en 3.\n"
        "Hacé que el contador esté en 5.\n"
    )
    assert inflexion.run_source(source) == "tres\ncinco\n"


def test_cuando_action_can_read_binding() -> None:
    """The deferred action may be `Decí el <noun>` (reads the cell at fire time)."""
    source = (
        "El contador está en 0.\n"
        "Cuando el contador esté en 7, decí el contador.\n"
        "Hacé que el contador esté en 7.\n"
    )
    assert inflexion.run_source(source) == "7\n"


def test_cuando_is_one_shot() -> None:
    """An observer fires exactly once; a re-mutation to the same value does not refire."""
    source = (
        'El contador está en 0.\n'
        'Cuando el contador esté en 1, decí "uno".\n'
        "Hacé que el contador esté en 1.\n"
        "Hacé que el contador esté en 2.\n"
        "Hacé que el contador esté en 1.\n"
    )
    assert inflexion.run_source(source) == "uno\n"
