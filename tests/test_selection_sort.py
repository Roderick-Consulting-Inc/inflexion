# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""End-to-end test: examples/selection-sort.infl.

Selection sort: outer mientras loop over positions; recursive helper
`indice_min` finds the min-index in the unsorted tail; swap via four
sequential mutations in a y-que chain (aux, list[i], list[m], i).
"""
from __future__ import annotations

from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "selection-sort.infl"


def test_selection_sort_canonical() -> None:
    """[5, 2, 8, 1, 9, 3, 7, 4, 6] → [1, 2, 3, 4, 5, 6, 7, 8, 9]."""
    output = inflexion.run_file(EXAMPLE)
    assert output.strip() == "[1, 2, 3, 4, 5, 6, 7, 8, 9]"


def test_selection_sort_already_sorted() -> None:
    """Already-sorted input remains sorted (idempotent)."""
    src = (
        "La lista está en [1, 2, 3, 4, 5].\n"
        "La n está en 5.\n"
        "La aux está en 0.\n"
        "La m está en 0.\n"
        "La función indice_min, que toma una lista, una desde, una hasta, una idx, "
        "es si la desde es mayor que la hasta, entonces la idx; "
        "sino, si el desde-ésimo de la lista es menor que el idx-ésimo de la lista, "
        "entonces indice_min la lista (la desde más 1) la hasta la desde; "
        "sino, indice_min la lista (la desde más 1) la hasta la idx.\n"
        "La i está en 1.\n"
        "Mientras la i no esté en la n, "
        "hacé que la m esté en indice_min la lista (la i más 1) la n la i "
        "y que la aux esté en el i-ésimo de la lista "
        "y que el i-ésimo de la lista esté en el m-ésimo de la lista "
        "y que el m-ésimo de la lista esté en la aux "
        "y que la i esté en la i más 1.\n"
        "Decí la lista.\n"
    )
    assert inflexion.run_source(src).strip() == "[1, 2, 3, 4, 5]"


def test_selection_sort_reverse() -> None:
    """[5, 4, 3, 2, 1] (worst case) → [1, 2, 3, 4, 5]."""
    src = (
        "La lista está en [5, 4, 3, 2, 1].\n"
        "La n está en 5.\n"
        "La aux está en 0.\n"
        "La m está en 0.\n"
        "La función indice_min, que toma una lista, una desde, una hasta, una idx, "
        "es si la desde es mayor que la hasta, entonces la idx; "
        "sino, si el desde-ésimo de la lista es menor que el idx-ésimo de la lista, "
        "entonces indice_min la lista (la desde más 1) la hasta la desde; "
        "sino, indice_min la lista (la desde más 1) la hasta la idx.\n"
        "La i está en 1.\n"
        "Mientras la i no esté en la n, "
        "hacé que la m esté en indice_min la lista (la i más 1) la n la i "
        "y que la aux esté en el i-ésimo de la lista "
        "y que el i-ésimo de la lista esté en el m-ésimo de la lista "
        "y que el m-ésimo de la lista esté en la aux "
        "y que la i esté en la i más 1.\n"
        "Decí la lista.\n"
    )
    assert inflexion.run_source(src).strip() == "[1, 2, 3, 4, 5]"
