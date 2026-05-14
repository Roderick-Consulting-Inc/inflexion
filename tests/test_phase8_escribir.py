# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 8 tests: `Escribí` imperative — write without trailing newline.

Covers the four parallels of the Decir family:
    - Escribí <singular-article> <noun>      → EscribirCommand
    - Escribí los <noun>                     → EscribirPluralCommand
    - Escribí <value-expression>             → EscribirExpr
    - Escribí "<literal>"                    → EscribirLiteral

The grammatical-semantic distinction is decir (to say — finished utterance,
terminated with a newline) vs escribir (to write — token streaming, no
inherent termination). Both are vos imperatives under the mood mapping;
the verb choice selects the termination axis.
"""
from __future__ import annotations

import inflexion


# ---------------------------------------------------------------------------
# EscribirLiteral — string literal, no newline
# ---------------------------------------------------------------------------


def test_escribir_literal_no_newline() -> None:
    """`Escribí "hola".` writes 'hola' with no trailing newline."""
    assert inflexion.run_source('Escribí "hola".\n') == "hola"


def test_escribir_literal_concatenates() -> None:
    """Two `Escribí` calls produce token-streamed output on the same line."""
    src = 'Escribí "Hola, ".\nEscribí "mundo".\nEscribí "!".\n'
    assert inflexion.run_source(src) == "Hola, mundo!"


# ---------------------------------------------------------------------------
# EscribirCommand — named binding, no newline
# ---------------------------------------------------------------------------


def test_escribir_binding_string() -> None:
    """`Escribí el saludo.` writes the bound string with no newline."""
    src = 'El saludo es "Hola".\nEscribí el saludo.\n'
    assert inflexion.run_source(src) == "Hola"


def test_escribir_binding_int() -> None:
    """`Escribí el n.` writes the bound int with no newline."""
    src = "El n es 42.\nEscribí el n.\n"
    assert inflexion.run_source(src) == "42"


# ---------------------------------------------------------------------------
# EscribirExpr — arithmetic / expression result, no newline
# ---------------------------------------------------------------------------


def test_escribir_expr_arithmetic() -> None:
    """`Escribí 2 más 3.` writes '5' with no newline."""
    assert inflexion.run_source("Escribí 2 más 3.\n") == "5"


def test_escribir_expr_function_call() -> None:
    """`Escribí` with a function-call expression."""
    src = (
        "La función doblar, que toma un n, es el n por 2.\n"
        "Escribí doblar (3).\n"
    )
    assert inflexion.run_source(src) == "6"


# ---------------------------------------------------------------------------
# EscribirPluralCommand — collection, no newline
# ---------------------------------------------------------------------------


def test_escribir_plural() -> None:
    """`Escribí los precios.` writes the collection with no newline."""
    src = "Los precios son [10, 20, 30].\nEscribí los precios.\n"
    out = inflexion.run_source(src)
    assert not out.endswith("\n")
    assert out == "[10, 20, 30]"


# ---------------------------------------------------------------------------
# Distinction from Decí — same value, different termination
# ---------------------------------------------------------------------------


def test_decir_and_escribir_distinguished() -> None:
    """`Decí "hola".` produces 'hola\\n'; `Escribí "hola".` produces 'hola'."""
    assert inflexion.run_source('Decí "hola".\n') == "hola\n"
    assert inflexion.run_source('Escribí "hola".\n') == "hola"


def test_mixed_decir_escribir() -> None:
    """Mix the two: tokens via Escribí, terminated utterance via Decí."""
    src = (
        'Escribí "Hello".\n'
        'Escribí ", ".\n'
        'Decí "world!".\n'
    )
    assert inflexion.run_source(src) == "Hello, world!\n"


# ---------------------------------------------------------------------------
# Character-code → character → Escribí (BF interpreter pattern)
# ---------------------------------------------------------------------------


def test_escribir_character_from_code() -> None:
    """The BF `.` pattern: emit a char from its ASCII code without newline."""
    src = "Escribí el carácter del código 65.\n"
    assert inflexion.run_source(src) == "A"


def test_escribir_streams_characters() -> None:
    """Streaming five chars from codes produces a single five-char string."""
    src = (
        "Escribí el carácter del código 72.\n"
        "Escribí el carácter del código 101.\n"
        "Escribí el carácter del código 108.\n"
        "Escribí el carácter del código 108.\n"
        "Escribí el carácter del código 111.\n"
    )
    assert inflexion.run_source(src) == "Hello"
