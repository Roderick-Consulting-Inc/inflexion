# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 7b tests: si-entonces-sino as an expression in value position.

Covers:
    - If-expression as the RHS of a ser binding
    - If-expression in a function body (the recursive factorial case)
    - Nested if-expressions (si-entonces in the else branch)
    - If-expression used with all comparison operators
"""
from __future__ import annotations

import inflexion


# ---------------------------------------------------------------------------
# Basic if-expression in binding position
# ---------------------------------------------------------------------------


def test_if_expr_then_branch() -> None:
    """si-entonces-sino: condition true → then-value."""
    src = (
        "El x es 5.\n"
        "El r es si el x es 5, entonces 100; sino, 200.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "100\n"


def test_if_expr_else_branch() -> None:
    """si-entonces-sino: condition false → else-value."""
    src = (
        "El x es 3.\n"
        "El r es si el x es 5, entonces 100; sino, 200.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "200\n"


def test_if_expr_string_result() -> None:
    """si-entonces-sino can yield string values."""
    src = (
        'El flag es 1.\n'
        'El msg es si el flag es 1, entonces "on"; sino, "off".\n'
        "Decí el msg.\n"
    )
    assert inflexion.run_source(src) == "on\n"


def test_if_expr_arithmetic_branches() -> None:
    """Branches can be arithmetic expressions."""
    src = (
        "El n es 6.\n"
        "El r es si el n es mayor que 5, entonces el n por 2; sino, el n más 1.\n"
        "Decí el r.\n"
    )
    # n=6 > 5 → 6*2 = 12
    assert inflexion.run_source(src) == "12\n"


# ---------------------------------------------------------------------------
# Nested if-expression (si in the else branch)
# ---------------------------------------------------------------------------


def test_nested_if_expr() -> None:
    """Nested si-entonces-sino: the else branch is itself an if-expression.

    Uses `classify`: >10 → 2, >5 → 1, otherwise → 0. Avoids negative
    literals (spaCy may split `-1` as two tokens; use arithmetic instead).
    """
    src = (
        "La función classify, que toma un n, es "
        "si el n es mayor que 10, entonces 2; sino, "
        "si el n es mayor que 5, entonces 1; sino, 0.\n"
        "El r es classify 15.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "2\n"


def test_nested_if_expr_middle() -> None:
    """Nested: middle branch (6 → 1)."""
    src = (
        "La función classify, que toma un n, es "
        "si el n es mayor que 10, entonces 2; sino, "
        "si el n es mayor que 5, entonces 1; sino, 0.\n"
        "El r es classify 6.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "1\n"


def test_nested_if_expr_zero() -> None:
    """Nested: else branch (3 → 0)."""
    src = (
        "La función classify, que toma un n, es "
        "si el n es mayor que 10, entonces 2; sino, "
        "si el n es mayor que 5, entonces 1; sino, 0.\n"
        "El r es classify 3.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "0\n"


# ---------------------------------------------------------------------------
# Relaxed-separator forms (Phase 7a fix — Bug 3)
# ---------------------------------------------------------------------------


def test_if_expr_comma_separator() -> None:
    """`si COND, entonces X, sino Y` — comma before sino (no semicolon)."""
    src = (
        "El x es 3.\n"
        'El r es si el x es 5, entonces "lucky", sino "ordinary".\n'
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "ordinary\n"


def test_if_expr_bare_sino() -> None:
    """`si COND, entonces X sino Y` — no separator between branches."""
    src = (
        "El n es 4.\n"
        'El r es si el n es divisible por 2, entonces "par" sino "impar".\n'
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "par\n"


def test_if_expr_in_function_body_bare() -> None:
    """If-expression in function body without semicolon separators."""
    src = (
        "La función etiqueta, que toma un n, es "
        "si el n es divisible por 2, entonces \"par\" sino \"impar\".\n"
        "Decí etiqueta 4.\n"
        "Decí etiqueta 3.\n"
    )
    assert inflexion.run_source(src) == "par\nimpar\n"


def test_if_expr_all_three_separator_forms() -> None:
    """Strict `;`, comma, and bare forms all produce the same result."""
    base = "El n es 6.\n"
    strict = base + 'El r es si el n es divisible por 3, entonces "fizz"; sino, "no".\nDecí el r.\n'
    comma = base + 'El r es si el n es divisible por 3, entonces "fizz", sino "no".\nDecí el r.\n'
    bare = base + 'El r es si el n es divisible por 3, entonces "fizz" sino "no".\nDecí el r.\n'
    for form, src in [("strict", strict), ("comma", comma), ("bare", bare)]:
        assert inflexion.run_source(src) == "fizz\n", f"{form} form failed"


# ---------------------------------------------------------------------------
# If-expression with comparison operators
# ---------------------------------------------------------------------------


def test_if_expr_no_es() -> None:
    """si-entonces-sino with `no es` (inequality)."""
    src = (
        "El x es 3.\n"
        "El r es si el x no es 5, entonces 99; sino, 0.\n"
        "Decí el r.\n"
    )
    assert inflexion.run_source(src) == "99\n"


def test_if_expr_divisible_por() -> None:
    """si-entonces-sino with `es divisible por`."""
    src = (
        "El n es 12.\n"
        'El msg es si el n es divisible por 4, entonces "divisible"; sino, "no".\n'
        "Decí el msg.\n"
    )
    assert inflexion.run_source(src) == "divisible\n"
