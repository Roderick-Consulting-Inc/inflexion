# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""End-to-end test: examples/quicksort.infl.

Functional 3-way quicksort: recursive D&C using `unir` (concat) +
dynamic list literals (`[el idx-ésimo de la xs]`) + recursive predicate
helpers (`pequeños` / `grandes`).
"""
from __future__ import annotations

from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "quicksort.infl"
EXAMPLE_TEXT = EXAMPLE.read_text(encoding="utf-8")


def _run_qs(list_literal: str) -> str:
    lines = EXAMPLE_TEXT.splitlines(keepends=True)
    lines[-2] = f"La lista está en {list_literal}.\n"
    return inflexion.run_source("".join(lines))


def test_canonical() -> None:
    """[5, 2, 8, 1, 9, 3, 7, 4, 6] sorted → [1, 2, 3, 4, 5, 6, 7, 8, 9]."""
    assert inflexion.run_file(EXAMPLE).strip() == "[1, 2, 3, 4, 5, 6, 7, 8, 9]"


def test_already_sorted() -> None:
    """[1, 2, 3, 4, 5] → [1, 2, 3, 4, 5]."""
    assert _run_qs("[1, 2, 3, 4, 5]").strip() == "[1, 2, 3, 4, 5]"


def test_reverse_sorted() -> None:
    """[5, 4, 3, 2, 1] → [1, 2, 3, 4, 5]."""
    assert _run_qs("[5, 4, 3, 2, 1]").strip() == "[1, 2, 3, 4, 5]"


def test_with_duplicates() -> None:
    """[3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5] → sorted with duplicates preserved."""
    out = _run_qs("[3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5]").strip()
    assert out == "[1, 1, 2, 3, 3, 4, 5, 5, 5, 6, 9]"


def test_singleton() -> None:
    """[42] → [42]."""
    assert _run_qs("[42]").strip() == "[42]"
