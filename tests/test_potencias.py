# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 6 end-to-end tests: aspect-marked lazy / eager evaluation.

Covers paper §3.3 + §5 Example 2 lines 3–4:

    - Perfective aspect (`Calculó las potencias del N`) requests eager
      evaluation. Phase 6 wires the eager path as a finite-prefix
      consume that produces no output (binding-target capture for
      aspect-marked operations is deferred to the ops-sem paper).
    - Imperfective aspect (`Calculaba las potencias del N`) requests
      lazy / streaming evaluation. The Phase-6 backend prints the
      first six terms of the operation stream, comma-separated and
      followed by a `, ...` truncation marker.

Lazy-prefix length is documented in `interpreter._LAZY_PREFIX_TERMS`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import inflexion
from inflexion.interpreter import InflexionRuntimeError
from inflexion.parser import InflexionParseError

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "potencias.infl"

EXPECTED_POTENCIAS = "1, 2, 4, 8, 16, 32, ...\n"


def test_potencias_run_file() -> None:
    """`Calculaba las potencias del 2.` runs end-to-end and prints six terms truncated."""
    assert inflexion.run_file(EXAMPLE) == EXPECTED_POTENCIAS


def test_potencias_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/potencias.infl`."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == EXPECTED_POTENCIAS
    assert result.returncode == 0


def test_perfective_aspect_produces_no_output() -> None:
    """Perfective `Calculó las potencias del 2.` consumes eagerly but does not print.

    Phase 6: the eager path computes the prefix and discards it
    (binding-target capture is deferred). The aspect-marked operation
    is therefore observable in difference-to-the-imperfective: same
    base, same operation, but no stream is rendered to stdout.
    """
    source = "Calculó las potencias del 2.\n"
    assert inflexion.run_source(source) == ""


def test_imperfective_aspect_prints_truncated_stream() -> None:
    """Imperfective `Calculaba las potencias del 2.` prints the truncated stream."""
    source = "Calculaba las potencias del 2.\n"
    assert inflexion.run_source(source) == EXPECTED_POTENCIAS


def test_imperfective_with_base_3() -> None:
    """Same imperfective form with base 3: first six powers of 3, truncated."""
    source = "Calculaba las potencias del 3.\n"
    # 3^0 = 1, 3^1 = 3, 3^2 = 9, 3^3 = 27, 3^4 = 81, 3^5 = 243.
    assert inflexion.run_source(source) == "1, 3, 9, 27, 81, 243, ...\n"


def test_aspect_perfective_vs_imperfective_pair() -> None:
    """Both forms accepted in the same program; only the imperfective prints."""
    source = (
        "Calculó las potencias del 2.\n"
        "Calculaba las potencias del 2.\n"
    )
    # Line 1 = silent; line 2 = stream.
    assert inflexion.run_source(source) == EXPECTED_POTENCIAS


def test_aspect_with_identifier_base() -> None:
    """The base can be an identifier (`del contador`), not just a literal."""
    source = (
        "El contador es 2.\n"
        "Calculaba las potencias del contador.\n"
    )
    assert inflexion.run_source(source) == EXPECTED_POTENCIAS


def test_aspect_unknown_operation_raises() -> None:
    """An aspect-marker verb without a wired operation raises a parse error.

    The Phase-6 dispatch table is intentionally narrow — `calcular las
    potencias del N` is the only operation; other operation nouns
    are rejected at parse-time so the dispatch surface is visible.
    """
    source = "Calculaba las cuadraturas del 2.\n"
    with pytest.raises(InflexionParseError, match="aspect-marked operations"):
        inflexion.run_source(source)


def test_six_mapping_close_program() -> None:
    """Closing program combining Phases 4-6 (paper §5 Example 4 lines 1-5)."""
    source = (
        "Los precios son [100, 200, 300, 400].\n"
        "La suma es el resultado de sumar los precios.\n"
        "Decí la suma.\n"
        "Decí la sumita.\n"
        "Calculaba las potencias del 2.\n"
    )
    assert inflexion.run_source(source) == "1000\n500\n" + EXPECTED_POTENCIAS
