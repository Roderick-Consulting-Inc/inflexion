# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""End-to-end test: examples/pi.infl.

Pi via the Leibniz series: π/4 = 1 - 1/3 + 1/5 - 1/7 + ...
Demonstrates the `entre` division operator, float arithmetic, signed
accumulator, and a long mientras-driven summation.

The Leibniz series converges slowly — 10,000 terms gives ~4 decimal
digits of accuracy. Test allows generous tolerance.
"""
from __future__ import annotations

import math
from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "pi.infl"


def test_pi_leibniz_converges() -> None:
    """10,000 Leibniz terms gives π to about 4 decimal places."""
    output = inflexion.run_file(EXAMPLE)
    approx = float(output.strip())
    assert abs(approx - math.pi) < 1e-3, f"Expected ~π, got {approx}"


def test_pi_leibniz_first_few_terms_smaller_run() -> None:
    """Smaller run (100 terms) gives a worse but still bounded approximation."""
    src = (
        "La pi está en 0.0.\n"
        "La k está en 0.\n"
        "El signo está en 1.\n"
        "Mientras la k no esté en 100, "
        "hacé que la pi esté en la pi más el signo entre (2 por la k más 1) "
        "y que el signo esté en 0 menos el signo "
        "y que la k esté en la k más 1.\n"
        "Decí 4 por la pi.\n"
    )
    approx = float(inflexion.run_source(src).strip())
    # 100 terms — error ~0.01
    assert abs(approx - math.pi) < 0.02
