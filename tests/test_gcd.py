# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""End-to-end test: examples/gcd.infl.

Subtractive Euclidean GCD via `mientras`. Demonstrates conditional
dispatch (Si la a es mayor que la b) inside a Mientras loop body with
variable-to-variable comparison.
"""
from __future__ import annotations

from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "gcd.infl"


def test_gcd_48_18() -> None:
    """gcd(48, 18) = 6."""
    assert inflexion.run_file(EXAMPLE).strip() == "6"


def test_gcd_via_run_source() -> None:
    """gcd(100, 75) = 25 — via inline source."""
    src = (
        "La a está en 100.\n"
        "La b está en 75.\n"
        "Mientras la a no esté en la b, "
        "si la a es mayor que la b, "
        "hacé que la a esté en la a menos la b; "
        "sino, hacé que la b esté en la b menos la a.\n"
        "Decí la a.\n"
    )
    assert inflexion.run_source(src).strip() == "25"


def test_gcd_coprime() -> None:
    """gcd(17, 13) = 1 (coprime)."""
    src = (
        "La a está en 17.\n"
        "La b está en 13.\n"
        "Mientras la a no esté en la b, "
        "si la a es mayor que la b, "
        "hacé que la a esté en la a menos la b; "
        "sino, hacé que la b esté en la b menos la a.\n"
        "Decí la a.\n"
    )
    assert inflexion.run_source(src).strip() == "1"
