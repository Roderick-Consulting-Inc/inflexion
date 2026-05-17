# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""End-to-end test: examples/truth-machine.infl.

A truth machine — reads an integer from stdin; if 0, prints "0" and
halts; otherwise prints "1" until the runtime's 100,000-iteration
mientras safety cap fires. The classical truth machine is supposed to
loop forever; Inflexión's runtime declines to honour that, on the
ground that unbounded iteration is rarely what a Spanish-prose program
is asking for. The wiki entry documents this distinction.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import inflexion
from inflexion.interpreter import InflexionRuntimeError

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "truth-machine.infl"
SOURCE = EXAMPLE.read_text(encoding="utf-8")


def test_truth_machine_zero_halts() -> None:
    """Input '0' prints '0' and halts (no loop)."""
    assert inflexion.run_source(SOURCE, stdin="0") == "0\n"


def test_truth_machine_nonzero_hits_safety_cap() -> None:
    """Input '1' loops; the runtime's 100k-iteration cap fires.

    The classical truth machine loops forever; Inflexión's runtime
    instead caps mientras iteration at 100,000 and raises a runtime
    error. This is a documented limitation, not a bug — the wiki entry
    notes it under "Computational class".
    """
    with pytest.raises(InflexionRuntimeError, match="safety cap"):
        inflexion.run_source(SOURCE, stdin="1")
