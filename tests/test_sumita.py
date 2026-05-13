# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 6 end-to-end tests: diminutive / augmentative numeric scaling.

Covers paper §3.5 + §5 Example 4 line 6:

    - `-ito` / `-ita` halves the base value.
    - `-illo` / `-illa` quarters the base value.
    - `-ón` / `-ona` doubles the base value.
    - `-azo` / `-aza` quadruples the base value.

The mapping is lookup-time, not parse-time: an identifier whose name
is not bound is tried against the diminutive-suffix table; if a base
candidate is bound (or appears in the numeral table), the scaled
value is returned. Bare bindings, function calls referencing a base
name, and `Decí` of a diminutive form all share the same fallback.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import inflexion
from inflexion.interpreter import InflexionRuntimeError

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "sumita.infl"

EXPECTED_SUMITA = "1000\n500\n"


def test_sumita_run_file() -> None:
    """Paper §5 Example 4 lines 4-6 run end-to-end via the file API."""
    assert inflexion.run_file(EXAMPLE) == EXPECTED_SUMITA


def test_sumita_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/sumita.infl`."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == EXPECTED_SUMITA
    assert result.returncode == 0


def test_diminutive_ita_halves_int_binding() -> None:
    """`Decí la sumita` reads `suma`'s value × ½, exact-int when even."""
    source = (
        "La suma es 100.\n"
        "Decí la sumita.\n"
    )
    assert inflexion.run_source(source) == "50\n"


def test_diminutive_ita_halves_odd_int_yields_float() -> None:
    """A scaling that lands on a non-integer returns a float."""
    source = (
        "La suma es 5.\n"
        "Decí la sumita.\n"
    )
    assert inflexion.run_source(source) == "2.5\n"


def test_diminutive_illo_quarters() -> None:
    """`-illo` quarters the base value."""
    source = (
        "El monto es 20.\n"
        "Decí el montillo.\n"
    )
    # 20 × ¼ = 5
    assert inflexion.run_source(source) == "5\n"


def test_augmentative_on_doubles() -> None:
    """`-ón` doubles the base value (Phase 6 augmentative)."""
    # `montón` strips `-ón` → base `mont` → try `monto` (vowel restoration).
    source = (
        "El monto es 7.\n"
        "Decí el montón.\n"
    )
    assert inflexion.run_source(source) == "14\n"


def test_augmentative_azo_quadruples() -> None:
    """`-azo` quadruples the base value."""
    source = (
        "El golpe es 3.\n"
        "Decí el golpazo.\n"
    )
    assert inflexion.run_source(source) == "12\n"


def test_diminutive_numeric_table_cinco() -> None:
    """`cincón` resolves via the numeral table when no binding shadows it.

    `cinco` → 5 in the numeral table; `cincón` → 5 × 2 = 10.
    """
    source = "Decí el cincón.\n"
    assert inflexion.run_source(source) == "10\n"


def test_diminutive_unknown_base_raises_original_error() -> None:
    """If neither the form nor any base candidate is bound, the error names the form."""
    source = "Decí el xyzito.\n"
    with pytest.raises(InflexionRuntimeError, match="Unknown binding: 'xyzito'"):
        inflexion.run_source(source)


def test_diminutive_function_variant_not_registered_raises() -> None:
    """Phase 6 contract: a diminutive of a registered function raises a variant error."""
    source = (
        "La función buscar, que toma un x, es el x más 1.\n"
        "El r es busquito el x.\n"
        "El x es 1.\n"
    )
    with pytest.raises(InflexionRuntimeError, match="not registered"):
        inflexion.run_source(source)


def test_diminutive_function_variant_augmentative_too() -> None:
    """An augmentative function-call form (`buscazo`) also raises the variant error."""
    source = (
        "La función buscar, que toma un x, es el x más 1.\n"
        "El r es buscazo el x.\n"
        "El x es 1.\n"
    )
    with pytest.raises(InflexionRuntimeError, match="not registered"):
        inflexion.run_source(source)


def test_diminutive_in_arithmetic_position() -> None:
    """A diminutive form can appear inside arithmetic, not just bare in `Decí`."""
    source = (
        "El total es 100.\n"
        "El doble es el totalón más el totalito.\n"
        "Decí el doble.\n"
    )
    # totalón = 100 × 2 = 200; totalito = 100 × ½ = 50; sum = 250.
    assert inflexion.run_source(source) == "250\n"


def test_explicit_binding_shadows_diminutive_fallback() -> None:
    """An explicit `sumita` binding wins over the diminutive fallback."""
    source = (
        "La suma es 100.\n"
        "La sumita es 999.\n"
        "Decí la sumita.\n"
    )
    # Direct binding wins; the diminutive fallback never fires.
    assert inflexion.run_source(source) == "999\n"
