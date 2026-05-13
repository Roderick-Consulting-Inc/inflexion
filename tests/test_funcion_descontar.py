# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 5 end-to-end tests: function definitions, reductions, broadcasting via call.

Covers the constructs introduced in Phase 5 (paper §3.4 + §5 Examples 3 & 4):

    - Relative-clause function definitions
      (`La función X, que toma una A, una B y un C, es <body>`).
    - Positional function calls by infinitive head
      (`descontar los precios el descuento`).
    - Reductions of a collection to a scalar
      (`el resultado de sumar los X`).
    - Phase 4 plural-binding RHS now accepts a function call.

The target program is the composite drawn from paper §5 Examples 3+4:
a `descontar` function called with a plural and a scalar arg, producing
the same discounted-price collection that Phase 4's bare-arithmetic
example produced. Output expectation is byte-equal to Phase 4's
`precios.infl` so the Phase 5 routing is visibly value-preserving.
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
EXAMPLE = REPO_ROOT / "examples" / "funcion-descontar.infl"

EXPECTED_PRECIOS = "[90.0, 180.0, 270.0, 360.0]\n"


def test_funcion_descontar_run_file() -> None:
    """Programmatic API: the composite §5 Examples 3+4 program runs end-to-end."""
    assert inflexion.run_file(EXAMPLE) == EXPECTED_PRECIOS


def test_funcion_descontar_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/funcion-descontar.infl`."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == EXPECTED_PRECIOS
    assert result.returncode == 0


def test_function_def_single_param_scalar() -> None:
    """A single-arg function applied to a scalar binds and prints correctly."""
    source = (
        "La función doblar, que toma un valor, es el valor por 2.\n"
        "El base es 7.\n"
        "El doble es doblar el base.\n"
        "Decí el doble.\n"
    )
    assert inflexion.run_source(source) == "14\n"


def test_function_def_single_param_broadcasts_on_collection() -> None:
    """A single-arg function broadcasts when called with a collection arg."""
    source = (
        "La función doblar, que toma un valor, es el valor por 2.\n"
        "Los base son [1, 2, 3].\n"
        "Los dobles son doblar los base.\n"
        "Decí los dobles.\n"
    )
    assert inflexion.run_source(source) == "[2, 4, 6]\n"


def test_function_def_two_params_arithmetic_body() -> None:
    """Two-param function with a two-operand arithmetic body, numeric-literal args."""
    source = (
        "La función agregar, que toma un a y un b, es el a más el b.\n"
        "Decí agregar 3 4.\n"
    )
    # Phase 5 accepts a numeric literal as a function-call arg. `agregar`
    # is chosen as the function name because spaCy reliably tags it
    # `POS=VERB, VerbForm=Inf` — a stem like `sumar_dos` is mis-tagged
    # NOUN due to the trailing numeral and would not trip the
    # infinitive-detection path.
    assert inflexion.run_source(source) == "7\n"


def test_function_call_arity_mismatch_raises() -> None:
    """Calling a 2-param function with 1 arg is a runtime error."""
    source = (
        "La función descontar, que toma un precio y un descuento, "
        "es el precio menos el descuento.\n"
        "El bad es descontar el precio.\n"
        "El precio es 10.\n"
    )
    # Note: lookup of `precio` happens at call time inside `descontar`,
    # so the arity check fires first.
    with pytest.raises(InflexionRuntimeError, match="expects"):
        inflexion.run_source(source)


def test_unknown_function_call_raises() -> None:
    """Calling an undefined function is a runtime error pointing at the syntax."""
    source = "El x es triplicar el valor.\nEl valor es 3.\n"
    with pytest.raises(InflexionRuntimeError, match="Unknown function"):
        inflexion.run_source(source)


def test_function_redefinition_raises() -> None:
    """Defining the same function twice is a runtime error (ser-like immutability)."""
    source = (
        "La función f, que toma un x, es el x más 1.\n"
        "La función f, que toma un x, es el x menos 1.\n"
    )
    with pytest.raises(InflexionRuntimeError, match="Cannot redefine function"):
        inflexion.run_source(source)


def test_reduction_sumar_collection() -> None:
    """`el resultado de sumar los X` folds a plural binding to a scalar."""
    source = (
        "Los valores son [10, 20, 30, 40].\n"
        "El total es el resultado de sumar los valores.\n"
        "Decí el total.\n"
    )
    assert inflexion.run_source(source) == "100\n"


def test_reduction_in_decir_expr() -> None:
    """A reduction in `Decí` print position evaluates and prints the scalar."""
    source = (
        "Los precios son [1, 2, 3, 4].\n"
        "Decí el resultado de sumar los precios.\n"
    )
    assert inflexion.run_source(source) == "10\n"


def test_reduction_on_scalar_target_raises() -> None:
    """Reducing a scalar-valued binding is a runtime error."""
    source = (
        "El cantidad es 5.\n"
        "El total es el resultado de sumar el cantidad.\n"
    )
    with pytest.raises(InflexionRuntimeError, match="requires a collection target"):
        inflexion.run_source(source)


def test_unknown_reduction_op_raises() -> None:
    """A reduction op outside the Phase 5 dispatch table is a runtime error."""
    source = (
        "Los valores son [1, 2, 3].\n"
        "El total es el resultado de promediar los valores.\n"
    )
    with pytest.raises(InflexionRuntimeError, match="reduction operators"):
        inflexion.run_source(source)


def test_function_body_uses_outer_scope_via_arg() -> None:
    """A function body references only its params; outer ser bindings stay outer."""
    source = (
        "El descuento es 0.10.\n"
        "La función aplicar, que toma un precio y un factor, "
        "es el precio menos el factor por el precio.\n"
        "El neto es aplicar 100 el descuento.\n"
        "Decí el neto.\n"
    )
    assert inflexion.run_source(source) == "90.0\n"


def test_function_def_then_call_chained_via_plural_binding() -> None:
    """End-to-end Phase 5 routing through a plural ser binding (target shape)."""
    source = (
        "La función descontar, que toma un precio y un descuento, "
        "es el precio menos el descuento por el precio.\n"
        "Los precios son [100, 200, 300, 400].\n"
        "El descuento es 0.10.\n"
        "Los precios_finales son descontar los precios el descuento.\n"
        "Decí los precios_finales.\n"
    )
    assert inflexion.run_source(source) == EXPECTED_PRECIOS


def test_function_def_malformed_missing_es_raises() -> None:
    """A function definition without `, es <body>` is a parse error."""
    source = "La función f, que toma un x.\n"
    with pytest.raises(InflexionParseError):
        inflexion.run_source(source)


def test_function_def_malformed_missing_params_raises() -> None:
    """A function definition without a parameter list is a parse error."""
    source = "La función f, que toma, es el x.\n"
    with pytest.raises(InflexionParseError, match="parameters"):
        inflexion.run_source(source)
