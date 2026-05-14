# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 7a tests: `y que` multi-clause mutation body in Mientras loops.

Covers:
    - 2-clause body: `hacé que … y que …`
    - 3-clause body: `hacé que … y que … y que …`
    - Sequential (not atomic) semantics: prior mutations in a sequence
      are visible to later ones in the SAME iteration.
"""
from __future__ import annotations

import inflexion


# ---------------------------------------------------------------------------
# Two-clause `y que` body
# ---------------------------------------------------------------------------


def test_two_clause_body() -> None:
    """A 2-clause Mientras body increments two counters per iteration."""
    src = (
        "El i está en 0.\n"
        "El suma está en 0.\n"
        "Mientras el i no esté en 5, "
        "hacé que el i esté en el i más 1 y que el suma esté en el suma más el i.\n"
        "Decí el suma.\n"
    )
    # Loop: i goes 0→1→2→3→4→5; suma accumulates the NEW i each iteration:
    # iter 1: i→1, suma→0+1=1
    # iter 2: i→2, suma→1+2=3
    # iter 3: i→3, suma→3+3=6
    # iter 4: i→4, suma→6+4=10
    # iter 5: i→5, suma→10+5=15 (sequential: i is already 5 here)
    assert inflexion.run_source(src) == "15\n"


def test_two_clause_body_both_accessible() -> None:
    """Both variables updated in each iteration are readable after the loop."""
    src = (
        "El a está en 0.\n"
        "El b está en 10.\n"
        "Mientras el a no esté en 3, "
        "hacé que el a esté en el a más 1 y que el b esté en el b menos 1.\n"
        "Decí el a.\n"
        "Decí el b.\n"
    )
    # 3 iterations: a: 0→1→2→3, b: 10→9→8→7
    assert inflexion.run_source(src) == "3\n7\n"


# ---------------------------------------------------------------------------
# Three-clause `y que` body
# ---------------------------------------------------------------------------


def test_three_clause_body() -> None:
    """A 3-clause Mientras body updates three vars per iteration."""
    src = (
        "El i está en 0.\n"
        "El x está en 0.\n"
        "El y está en 0.\n"
        "Mientras el i no esté en 3, "
        "hacé que el i esté en el i más 1 "
        "y que el x esté en el x más 2 "
        "y que el y esté en el y más 3.\n"
        "Decí el i.\n"
        "Decí el x.\n"
        "Decí el y.\n"
    )
    # 3 iterations: i→3, x→6, y→9
    assert inflexion.run_source(src) == "3\n6\n9\n"


# ---------------------------------------------------------------------------
# Sequential (not atomic) semantics
# ---------------------------------------------------------------------------


def test_sequential_not_atomic_semantics() -> None:
    """Sequential semantics: `y que el b esté en el a` sees the NEW a.

    If semantics were atomic (all RHS evaluated before any mutation),
    `y que el b esté en el a` would see the OLD a.
    With sequential semantics, it sees the NEW a (post first mutation).

    Loop runs once (i: 0→1 stops the loop).
    First mutation:  a ← 99  (a was 0)
    Second mutation: b ← a   → b ← 99  (sequential: sees new a=99)
    Atomic would give: b ← 0  (old a).
    """
    src = (
        "El i está en 0.\n"
        "El a está en 0.\n"
        "El b está en 0.\n"
        "Mientras el i no esté en 1, "
        "hacé que el i esté en el i más 1 "
        "y que el a esté en 99 "
        "y que el b esté en el a.\n"
        "Decí el a.\n"
        "Decí el b.\n"
    )
    # Sequential: a becomes 99, then b takes the NEW a (99).
    # Atomic would give b=0 (old a). We document sequential behaviour.
    assert inflexion.run_source(src) == "99\n99\n"


def test_sequential_semantics_not_swap() -> None:
    """`y que el b esté en el a y que el a esté en el b` is NOT a swap.

    With sequential semantics:
        b ← a   (b gets old a, say 10)
        a ← b   (a gets the NEW b, which is the old a = 10)
    Result: a=10, b=10 — both equal old a. NOT a swap.
    An atomic swap would give a=20, b=10.
    """
    src = (
        "El i está en 0.\n"
        "El a está en 10.\n"
        "El b está en 20.\n"
        "Mientras el i no esté en 1, "
        "hacé que el i esté en el i más 1 "
        "y que el b esté en el a "
        "y que el a esté en el b.\n"
        "Decí el a.\n"
        "Decí el b.\n"
    )
    # Sequential: b←10 (old a), then a←10 (new b). NOT atomic swap.
    assert inflexion.run_source(src) == "10\n10\n"


# ---------------------------------------------------------------------------
# Single-clause (regression: should still work as MutationCommand)
# ---------------------------------------------------------------------------


def test_single_mutation_still_works() -> None:
    """Existing single-clause mutation body is unchanged by Phase 7a."""
    src = (
        "El i está en 0.\n"
        "Mientras el i no esté en 3, hacé que el i esté en el i más 1.\n"
        "Decí el i.\n"
    )
    assert inflexion.run_source(src) == "3\n"
