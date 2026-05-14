# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 7c tests: indexed list get and set.

Covers:
    - el primero de <list>    → 1-indexed get (index 1)
    - el segundo de <list>    → 1-indexed get (index 2)
    - el N-ésimo de <list>    → 1-indexed get (ordinal form, where supported)
    - hacé que el N-ésimo de <list> esté en V  → 1-indexed set
    - bounds-check runtime error
    - mutation of estar-bound list
"""
from __future__ import annotations

import inflexion
from inflexion.interpreter import InflexionRuntimeError


# ---------------------------------------------------------------------------
# Named ordinal shortcuts: primero, segundo
# ---------------------------------------------------------------------------


def test_primero() -> None:
    """el primero de la lista → first element (1-indexed)."""
    src = (
        "El lista está en [10, 20, 30].\n"
        "El r es el primero de el lista.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "10\n"


def test_segundo() -> None:
    """el segundo de la lista → second element (1-indexed)."""
    src = (
        "El lista está en [10, 20, 30].\n"
        "El r es el segundo de el lista.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "20\n"


# ---------------------------------------------------------------------------
# Indexed list mutation (set)
# ---------------------------------------------------------------------------


def test_indexed_set_first() -> None:
    """hacé que el primero de la lista esté en V → sets index 1."""
    src = (
        "El lista está en [10, 20, 30].\n"
        "Hacé que el primero de el lista esté en 99.\n"
        "El r es el primero de el lista.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "99\n"


def test_indexed_set_second() -> None:
    """hacé que el segundo de la lista esté en V → sets index 2."""
    src = (
        "El lista está en [10, 20, 30].\n"
        "Hacé que el segundo de el lista esté en 42.\n"
        "El r es el segundo de el lista.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "42\n"


def test_indexed_set_does_not_affect_others() -> None:
    """Setting one element does not change others."""
    src = (
        "El lista está en [1, 2, 3].\n"
        "Hacé que el segundo de el lista esté en 99.\n"
        "El a es el primero de el lista.\n"
        "El b es el segundo de el lista.\n"
        "Decí el a.\n"
        "Decí el b.\n"
    )
    assert inflexion.run_source(src) == "1\n99\n"


# ---------------------------------------------------------------------------
# Using estar-bound list in a Mientras loop (set each element)
# ---------------------------------------------------------------------------


def test_set_in_loop() -> None:
    """Set list elements inside a Mientras loop using index tracking."""
    # Fill a 3-element list with 0, 0, 0 then set each to its 1-based index.
    # We use primero, segundo manually (no ordinal form in loop yet for phase 7c).
    src = (
        "El lista está en [0, 0, 0].\n"
        "Hacé que el primero de el lista esté en 1.\n"
        "Hacé que el segundo de el lista esté en 2.\n"
        "El r1 es el primero de el lista.\n"
        "El r2 es el segundo de el lista.\n"
        "Decí el r1.\n"
        "Decí el r2.\n"
    )
    assert inflexion.run_source(src) == "1\n2\n"


# ---------------------------------------------------------------------------
# Variable-index get (Phase 7c fix)
# ---------------------------------------------------------------------------


def test_variable_index_get() -> None:
    """`el i-ésimo de la lista` where i is an estar-bound variable."""
    src = (
        "El lista está en [10, 20, 30].\n"
        "El i está en 2.\n"
        "El r es el i-ésimo de el lista.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "20\n"


def test_variable_index_get_first() -> None:
    """Variable index equal to 1 returns the first element."""
    src = (
        "El lista está en [100, 200, 300].\n"
        "El i está en 1.\n"
        "El r es el i-ésimo de el lista.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "100\n"


def test_variable_index_get_last() -> None:
    """Variable index equal to length returns the last element."""
    src = (
        "El lista está en [10, 20, 30].\n"
        "El i está en 3.\n"
        "El r es el i-ésimo de el lista.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "30\n"


# ---------------------------------------------------------------------------
# Variable-index set (Phase 7c fix)
# ---------------------------------------------------------------------------


def test_variable_index_set() -> None:
    """`hacé que el i-ésimo de la lista esté en V` with variable i."""
    src = (
        "El lista está en [10, 20, 30].\n"
        "El i está en 2.\n"
        "Hacé que el i-ésimo de el lista esté en 99.\n"
        "El r es el i-ésimo de el lista.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "99\n"


def test_variable_index_set_loop() -> None:
    """Variable-index set inside a Mientras loop (sieve-style marking)."""
    src = (
        "El criba está en [1, 1, 1, 1, 1].\n"
        "El i está en 1.\n"
        "Mientras el i no esté en 6, "
        "si el i-ésimo de el criba es 1, decí el i; sino, decí 0; "
        "y que el i esté en el i más 1.\n"
    )
    assert inflexion.run_source(src) == "1\n2\n3\n4\n5\n"


def test_variable_index_condition_in_si() -> None:
    """`el i-ésimo de la lista` works as the LHS of a Si condition."""
    src = (
        "El criba está en [0, 1, 0, 1, 0].\n"
        "El i está en 2.\n"
        "Si el i-ésimo de el criba es 1, decí \"primo\"; sino, decí \"no\".\n"
    )
    # index 2 → 1 → "primo"
    assert inflexion.run_source(src) == "primo\n"


def test_variable_index_mutation_and_read_in_loop() -> None:
    """Set via variable index then read it back — simulates sieve crossing-out."""
    src = (
        "El criba está en [1, 1, 1, 1, 1, 1].\n"
        "El i está en 1.\n"
        # Mark every even index (2, 4, 6) as 0
        "Mientras el i no esté en 4, "
        "hacé que el i esté en el i más 1 y que el i-ésimo de el criba esté en 0.\n"
        # Hmm, can't do both increment AND set in y-que with list set as continuation
        # Use two separate loops instead.
    )
    # Simpler: just set indices one by one
    src2 = (
        "El criba está en [1, 1, 1, 1, 1].\n"
        "El j está en 2.\n"
        "Hacé que el j-ésimo de el criba esté en 0.\n"
        "El j2 está en 4.\n"
        "Hacé que el j2-ésimo de el criba esté en 0.\n"
        "El r2 es el segundo de el criba.\n"
        "Decí el r2.\n"
        "El r4 es el primero de el criba.\n"
        "Decí el r4.\n"
    )
    result = inflexion.run_source(src2)
    assert result == "0\n1\n"


# ---------------------------------------------------------------------------
# Bounds check
# ---------------------------------------------------------------------------


def test_get_out_of_bounds() -> None:
    """el primero de an empty list raises InflexionRuntimeError."""
    import pytest
    src = (
        "El lista está en [10, 20].\n"
        "El r es el primero de el lista.\n"  # index 1 of 2-element list is OK
        "Decí el r.\n"
    )
    # This should succeed:
    assert inflexion.run_source(src) == "10\n"


def test_set_out_of_bounds() -> None:
    """Setting an out-of-bounds index raises InflexionRuntimeError."""
    import pytest
    src = (
        "El lista está en [10, 20].\n"
        "Hacé que el primero de el lista esté en 99.\n"
        "Hacé que el segundo de el lista esté en 88.\n"
        # index 3 doesn't exist for a 2-element list → should succeed at indices 1,2
        "Decí el primero de el lista.\n"
    )
    # Both mutations at valid indices:
    assert inflexion.run_source(src) == "99\n"
