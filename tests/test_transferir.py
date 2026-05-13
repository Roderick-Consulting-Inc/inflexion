# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 5 end-to-end tests: clitic-stack vos-imperative call form.

Covers paper §3.4 + §5 Example 3:

    - Function definition with three named parameters and an elided body
      (`La función transferir, que toma una A, una B y un C, es ...`).
    - Vos-imperative with a two-clitic stack
      (`Transferíselo`, `Dámelo`, `Dáselo`).
    - The Phase-5 record-of-call side effect: an elided-body imperative
      with clitics writes a line `"<verb>(<clitic1>, <clitic2>)"` to
      stdout, in fixed Spanish order.

The Phase 5 contract on these forms is intentionally minimal — full
positional clitic routing arrives with the ops-sem installment. These
tests pin the surface contract (the parse shape and the record-of-call
output) so the Phase 6+ work has a known-good baseline.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import inflexion
from inflexion.interpreter import InflexionRuntimeError

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "transferir.infl"

EXPECTED_TRANSFERIR = "transferir(se, lo)\n"


def test_transferir_run_file() -> None:
    """Programmatic API: the paper §5 Example 3 elided-body program runs."""
    assert inflexion.run_file(EXAMPLE) == EXPECTED_TRANSFERIR


def test_transferir_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/transferir.infl`."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == EXPECTED_TRANSFERIR
    assert result.returncode == 0


def test_dame_lo_clitic_stack_records_call() -> None:
    """`Dámelo` over an elided-body function logs `dar(me, lo)`."""
    source = (
        "La función dar, que toma un receptor y un objeto, es ...\n"
        "Dámelo.\n"
    )
    assert inflexion.run_source(source) == "dar(me, lo)\n"


def test_dase_lo_clitic_stack_records_call() -> None:
    """`Dáselo` over an elided-body function logs `dar(se, lo)`."""
    source = (
        "La función dar, que toma un receptor y un objeto, es ...\n"
        "Dáselo.\n"
    )
    assert inflexion.run_source(source) == "dar(se, lo)\n"


def test_clitic_order_is_fixed_spanish_order() -> None:
    """The clitics appear in the surface left-to-right order (Spanish-grammar order)."""
    source = (
        "La función mover, que toma un origen, un destino y un cuerpo, es ...\n"
        "Movételo.\n"
    )
    # `Movételo` → strip `lo`, then `te` → `mové`; clitics = (te, lo).
    assert inflexion.run_source(source) == "mover(te, lo)\n"


def test_clitic_stack_on_undefined_function_raises() -> None:
    """A clitic-stack imperative referencing an unknown verb is a runtime error."""
    source = "Transferíselo.\n"
    with pytest.raises(InflexionRuntimeError, match="Unknown function"):
        inflexion.run_source(source)


def test_clitic_stack_with_defined_body_still_records_call() -> None:
    """Phase 5: defined-body functions also log the call shape via clitic-stack form.

    Full positional routing is deferred to the ops-sem installment; for now
    the Phase 5 contract is that the call is *observable* (a record line
    written), and the surface tests pin that contract.
    """
    source = (
        "La función pasar, que toma un a y un b, es el a más el b.\n"
        "Pasámelo.\n"
    )
    assert inflexion.run_source(source) == "pasar(me, lo)\n"


def test_phase1_decilo_still_emits_imperative_call() -> None:
    """Backward-compat: `Decilo` continues to use the Phase 1 anaphora path."""
    # If Phase 5's clitic-stack path captured `Decilo`, this would fail
    # with `Unknown function 'decir'` since `decir` isn't in the registry.
    # The Phase 1 single-clitic path takes precedence and prints the
    # most-recent binding.
    source = 'El saludo es "Hola, mundo".\nDecilo.\n'
    assert inflexion.run_source(source) == "Hola, mundo\n"
