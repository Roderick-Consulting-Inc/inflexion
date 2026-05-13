# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 4 end-to-end tests: plural articles, collection literals, broadcasting.

Covers the new constructs introduced in Phase 4 (paper §3.6 + §5 Example 4):

    - Plural ser binding (`Los X son [...]`)
    - List literals with int / decimal elements
    - `por` (multiplication) operator + standard precedence with `más` / `menos`
    - Scalar↔collection and collection↔collection broadcasting
    - `Decí los X` collection print
    - Number-agreement parse errors (`el precios`, `Los X son 5`)

Output format choice (documented in `interpreter._format_collection`):
the implementation prints collections as a Python-list repr, e.g.
`[90.0, 180.0, 270.0, 360.0]`, with a trailing newline. The tests
encode this choice.
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
EXAMPLE = REPO_ROOT / "examples" / "precios.infl"

EXPECTED_PRECIOS = "[90.0, 180.0, 270.0, 360.0]\n"


def test_precios_run_file() -> None:
    """Programmatic API: the paper §5 Example 4 program runs end-to-end."""
    assert inflexion.run_file(EXAMPLE) == EXPECTED_PRECIOS


def test_precios_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/precios.infl` prints the list."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == EXPECTED_PRECIOS
    assert result.returncode == 0


def test_scalar_times_collection_broadcasts() -> None:
    """`Decí los X por 2` broadcasts the scalar across the collection."""
    source = "Los valores son [1, 2, 3].\nDecí los valores por 2.\n"
    assert inflexion.run_source(source) == "[2, 4, 6]\n"


def test_collection_minus_collection_elementwise() -> None:
    """Two equal-length collections subtract element-wise."""
    source = (
        "Los a son [10, 20].\n"
        "Los b son [1, 2].\n"
        "Decí los a menos los b.\n"
    )
    assert inflexion.run_source(source) == "[9, 18]\n"


def test_collection_plus_collection_elementwise() -> None:
    """Two equal-length collections add element-wise."""
    source = (
        "Los a son [10, 20, 30].\n"
        "Los b son [1, 2, 3].\n"
        "Decí los a más los b.\n"
    )
    assert inflexion.run_source(source) == "[11, 22, 33]\n"


def test_mismatched_length_collection_arithmetic_raises() -> None:
    """Different-length collection arithmetic is a runtime error."""
    source = (
        "Los a son [1, 2, 3].\n"
        "Los b son [10, 20].\n"
        "Decí los a más los b.\n"
    )
    with pytest.raises(InflexionRuntimeError, match="length mismatch"):
        inflexion.run_source(source)


def test_singular_article_with_plural_noun_is_parse_error() -> None:
    """`el precios` (singular article on plural noun) raises a parse error."""
    source = "El precios es 5.\n"
    with pytest.raises(InflexionParseError, match="Number-agreement"):
        inflexion.run_source(source)


def test_plural_binding_with_scalar_literal_is_parse_error() -> None:
    """Phase 4 simplification: `Los X son 5` is rejected at parse time."""
    source = "Los valores son 5.\n"
    with pytest.raises(InflexionParseError, match="collection-producing RHS"):
        inflexion.run_source(source)


def test_plural_binding_with_singular_verb_is_parse_error() -> None:
    """`Los X es …` is a number-agreement error on the verb."""
    source = "Los valores es [1, 2].\n"
    with pytest.raises(InflexionParseError, match="Number-agreement"):
        inflexion.run_source(source)


def test_decimal_literal_round_trip() -> None:
    """A decimal literal binds and prints as a Python float repr."""
    source = "El descuento es 0.10.\nDecí el descuento.\n"
    assert inflexion.run_source(source) == "0.1\n"


def test_collection_times_scalar_with_decimal() -> None:
    """A decimal scalar broadcasts across an int collection (paper §5 inner step)."""
    source = (
        "El descuento es 0.10.\n"
        "Los precios son [100, 200].\n"
        "Decí el descuento por los precios.\n"
    )
    assert inflexion.run_source(source) == "[10.0, 20.0]\n"


def test_arithmetic_precedence_por_binds_tighter() -> None:
    """`A menos B por C` parses as `A menos (B por C)` (paper §5 Example 4)."""
    # 10 menos 2 por 3 → 10 - (2*3) = 4 (not (10-2)*3 = 24).
    source = "El total es 10 menos 2 por 3.\nDecí el total.\n"
    assert inflexion.run_source(source) == "4\n"


def test_plural_binding_chains_through_another_plural() -> None:
    """A plural ser binding may reference another plural binding in arithmetic."""
    source = (
        "Los base son [1, 2, 3].\n"
        "Los doblado son los base por 2.\n"
        "Decí los doblado.\n"
    )
    assert inflexion.run_source(source) == "[2, 4, 6]\n"
