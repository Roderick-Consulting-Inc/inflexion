# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 7c tests: Escuchá stdin binding.

Covers:
    - Escuchá una línea en el x → bind string from stdin
    - Escuchá un número en el x → bind parsed int from stdin
    - Multiple reads consume lines in order
    - Empty buffer returns empty string
    - run_source(source, stdin=...) API
"""
from __future__ import annotations

import inflexion


# ---------------------------------------------------------------------------
# Escuchá una línea
# ---------------------------------------------------------------------------


def test_escucha_linea_basic() -> None:
    """Escuchá una línea reads the first stdin line as a string."""
    src = "Escuchá una línea en el entrada.\nDecí el entrada.\n"
    assert inflexion.run_source(src, stdin="hola mundo") == "hola mundo\n"


def test_escucha_linea_second_line() -> None:
    """Two consecutive reads consume lines in order."""
    src = (
        "Escuchá una línea en el a.\n"
        "Escuchá una línea en el b.\n"
        "Decí el a.\n"
        "Decí el b.\n"
    )
    assert inflexion.run_source(src, stdin="primera\nsegunda") == "primera\nsegunda\n"


def test_escucha_linea_empty_buffer() -> None:
    """Reading past the end of stdin returns the empty string."""
    src = "Escuchá una línea en el x.\nDecí el x.\n"
    # No stdin supplied → empty string
    assert inflexion.run_source(src, stdin="") == "\n"


# ---------------------------------------------------------------------------
# Escuchá un número
# ---------------------------------------------------------------------------


def test_escucha_numero_basic() -> None:
    """Escuchá un número reads and parses an integer."""
    src = "Escuchá un número en el n.\nDecí el n.\n"
    assert inflexion.run_source(src, stdin="42") == "42\n"


def test_escucha_numero_arithmetic() -> None:
    """A parsed number can be used in arithmetic immediately."""
    src = (
        "Escuchá un número en el n.\n"
        "El doble es el n por 2.\n"
        "Decí el doble.\n"
    )
    assert inflexion.run_source(src, stdin="7") == "14\n"


def test_escucha_numero_multiple() -> None:
    """Two numbers read from stdin."""
    src = (
        "Escuchá un número en el a.\n"
        "Escuchá un número en el b.\n"
        "El suma es el a más el b.\n"
        "Decí el suma.\n"
    )
    assert inflexion.run_source(src, stdin="3\n7") == "10\n"


# ---------------------------------------------------------------------------
# run_source stdin= API
# ---------------------------------------------------------------------------


def test_stdin_kwarg_only() -> None:
    """stdin must be a keyword argument (enforced by *)."""
    import inspect
    sig = inspect.signature(inflexion.run_source)
    # `stdin` must be keyword-only (after `*`)
    param = sig.parameters["stdin"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY


def test_stdin_default_empty() -> None:
    """Default stdin is empty — programs without Escuchá are unaffected."""
    src = "El x es 5.\nDecí el x.\n"
    assert inflexion.run_source(src) == "5\n"
