# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Tests for the runtime extensions added in the v0.0.10 / v0.0.11 cycle:

- `módulo` / `modulo` arithmetic operator
- `el largo de` extended to lists
- `unir A y B` list concatenation
- `los primeros N de` / `los últimos N de` list slicing
- Dynamic list literals (identifiers / expressions as elements)
- Multi-mutation Si-arm bodies (`si COND, hacé que A y que B y que C`)
"""
from __future__ import annotations

import inflexion


# ---------------------------------------------------------------------------
# `módulo` operator
# ---------------------------------------------------------------------------


def test_modulo_basic() -> None:
    """17 módulo 5 = 2."""
    assert inflexion.run_source("Decí 17 módulo 5.\n").strip() == "2"


def test_modulo_exact() -> None:
    """10 módulo 5 = 0."""
    assert inflexion.run_source("Decí 10 módulo 5.\n").strip() == "0"


def test_modulo_unaccented_modulo() -> None:
    """`modulo` (unaccented) also works."""
    assert inflexion.run_source("Decí 13 modulo 4.\n").strip() == "1"


def test_modulo_precedence_with_addition() -> None:
    """7 más 3 módulo 2 = 7 + (3 mod 2) = 7 + 1 = 8 (módulo binds tighter)."""
    assert inflexion.run_source("Decí 7 más 3 módulo 2.\n").strip() == "8"


def test_modulo_by_zero_errors() -> None:
    """Modulo by 0 raises a runtime error."""
    import pytest
    from inflexion.interpreter import InflexionRuntimeError
    with pytest.raises(InflexionRuntimeError, match="Modulo by zero"):
        inflexion.run_source("Decí 5 módulo 0.\n")


# ---------------------------------------------------------------------------
# `el largo de` extended to lists
# ---------------------------------------------------------------------------


def test_largo_de_lista() -> None:
    """`el largo de` works on lists, not just strings."""
    src = "La xs está en [10, 20, 30, 40, 50].\nDecí el largo de la xs.\n"
    assert inflexion.run_source(src).strip() == "5"


def test_largo_de_lista_vacia() -> None:
    """Length of an empty list is 0."""
    src = "La xs está en [].\nDecí el largo de la xs.\n"
    assert inflexion.run_source(src).strip() == "0"


def test_largo_de_string_still_works() -> None:
    """String length still works (regression)."""
    src = 'El s es "hola".\nDecí el largo de el s.\n'
    assert inflexion.run_source(src).strip() == "4"


# ---------------------------------------------------------------------------
# `unir A y B` concatenation
# ---------------------------------------------------------------------------


def test_unir_simple() -> None:
    """`unir [1,2,3] y [4,5,6]` = `[1,2,3,4,5,6]`."""
    src = (
        "La a está en [1, 2, 3].\n"
        "La b está en [4, 5, 6].\n"
        "Decí unir la a y la b.\n"
    )
    assert inflexion.run_source(src).strip() == "[1, 2, 3, 4, 5, 6]"


def test_unir_with_empty() -> None:
    """`unir [] y [1,2]` = `[1,2]`."""
    src = (
        "La a está en [].\n"
        "La b está en [1, 2].\n"
        "Decí unir la a y la b.\n"
    )
    assert inflexion.run_source(src).strip() == "[1, 2]"


def test_unir_two_empties() -> None:
    """`unir [] y []` = `[]`."""
    src = (
        "La a está en [].\n"
        "La b está en [].\n"
        "Decí unir la a y la b.\n"
    )
    assert inflexion.run_source(src).strip() == "[]"


# ---------------------------------------------------------------------------
# `los primeros N de` / `los últimos N de` slicing
# ---------------------------------------------------------------------------


def test_primeros_n_de() -> None:
    """First 2 of [10, 20, 30, 40] = [10, 20]."""
    src = "La xs está en [10, 20, 30, 40].\nDecí los primeros 2 de la xs.\n"
    assert inflexion.run_source(src).strip() == "[10, 20]"


def test_ultimos_n_de() -> None:
    """Last 2 of [10, 20, 30, 40] = [30, 40]."""
    src = "La xs está en [10, 20, 30, 40].\nDecí los últimos 2 de la xs.\n"
    assert inflexion.run_source(src).strip() == "[30, 40]"


def test_primeros_all() -> None:
    """First N of a length-N list returns the whole list."""
    src = "La xs está en [1, 2, 3].\nDecí los primeros 3 de la xs.\n"
    assert inflexion.run_source(src).strip() == "[1, 2, 3]"


def test_primeros_zero() -> None:
    """First 0 of any list = []."""
    src = "La xs está en [1, 2, 3].\nDecí los primeros 0 de la xs.\n"
    assert inflexion.run_source(src).strip() == "[]"


# ---------------------------------------------------------------------------
# Dynamic list literals
# ---------------------------------------------------------------------------


def test_dynamic_list_literal_identifiers() -> None:
    """[la x, la y, la x más la y]: identifiers + arithmetic in literal."""
    src = "La x está en 7.\nLa y está en 9.\nDecí [la x, la y, la x más la y].\n"
    assert inflexion.run_source(src).strip() == "[7, 9, 16]"


def test_dynamic_list_literal_single_element() -> None:
    """[la x] — single-element list wrapping a binding."""
    src = "La x está en 42.\nDecí [la x].\n"
    assert inflexion.run_source(src).strip() == "[42]"


def test_dynamic_list_literal_with_indexed_access() -> None:
    """[el primero de la xs, el segundo de la xs] — indexed access elements."""
    src = (
        "La xs está en [10, 20, 30].\n"
        "Decí [el primero de la xs, el segundo de la xs].\n"
    )
    assert inflexion.run_source(src).strip() == "[10, 20]"


# ---------------------------------------------------------------------------
# Multi-mutation Si-arm bodies
# ---------------------------------------------------------------------------


def test_si_arm_multi_mutation() -> None:
    """Si arm can carry multiple y-que mutations (single conditional, several effects)."""
    src = (
        "La a está en 0.\n"
        "La b está en 0.\n"
        "La c está en 0.\n"
        "El flag es 1.\n"
        "Si el flag es 1, hacé que la a esté en 10 y que la b esté en 20 y que la c esté en 30.\n"
        "Decí la a.\n"
        "Decí la b.\n"
        "Decí la c.\n"
    )
    assert inflexion.run_source(src) == "10\n20\n30\n"


def test_si_arm_multi_mutation_else_path() -> None:
    """Multi-mutation also works in the sino arm."""
    src = (
        "La a está en 0.\n"
        "La b está en 0.\n"
        "El flag es 0.\n"
        "Si el flag es 1, hacé que la a esté en 10 y que la b esté en 20; "
        "sino, hacé que la a esté en 99 y que la b esté en 88.\n"
        "Decí la a.\n"
        "Decí la b.\n"
    )
    assert inflexion.run_source(src) == "99\n88\n"
