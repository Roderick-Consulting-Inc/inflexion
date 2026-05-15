# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Tests for the `Hablá` imperative — streaming output, no trailing newline.

Covers the four parallels of the Decir family:
    - Hablá <singular-article> <noun>      → HablarCommand
    - Hablá los <noun>                     → HablarPluralCommand
    - Hablá <value-expression>             → HablarExpr
    - Hablá "<literal>"                    → HablarLiteral

The grammatical-semantic distinction is *decir* (to say — committed
content, terminated utterance) vs *hablar* (to speak — ongoing activity,
sound-by-sound, no inherent termination). Both are vos imperatives under
the mood mapping; the verb choice selects the content-vs-activity axis.
"""
from __future__ import annotations

import inflexion


# ---------------------------------------------------------------------------
# HablarLiteral — string literal, no newline
# ---------------------------------------------------------------------------


def test_hablar_literal_no_newline() -> None:
    """`Hablá "hola".` writes 'hola' with no trailing newline."""
    assert inflexion.run_source('Hablá "hola".\n') == "hola"


def test_hablar_literal_concatenates() -> None:
    """Two `Hablá` calls produce token-streamed output on the same line."""
    src = 'Hablá "Hola, ".\nHablá "mundo".\nHablá "!".\n'
    assert inflexion.run_source(src) == "Hola, mundo!"


# ---------------------------------------------------------------------------
# HablarCommand — named binding, no newline
# ---------------------------------------------------------------------------


def test_hablar_binding_string() -> None:
    """`Hablá el saludo.` writes the bound string with no newline."""
    src = 'El saludo es "Hola".\nHablá el saludo.\n'
    assert inflexion.run_source(src) == "Hola"


def test_hablar_binding_int() -> None:
    """`Hablá la n.` writes the bound int with no newline (single-letter var: feminine)."""
    src = "La n es 42.\nHablá la n.\n"
    assert inflexion.run_source(src) == "42"


# ---------------------------------------------------------------------------
# HablarExpr — arithmetic / expression result, no newline
# ---------------------------------------------------------------------------


def test_hablar_expr_arithmetic() -> None:
    """`Hablá 2 más 3.` writes '5' with no newline."""
    assert inflexion.run_source("Hablá 2 más 3.\n") == "5"


def test_hablar_expr_function_call() -> None:
    """`Hablá` with a function-call expression."""
    src = (
        "La función doblar, que toma una n, es la n por 2.\n"
        "Hablá doblar (3).\n"
    )
    assert inflexion.run_source(src) == "6"


# ---------------------------------------------------------------------------
# HablarPluralCommand — collection, no newline
# ---------------------------------------------------------------------------


def test_hablar_plural() -> None:
    """`Hablá los precios.` writes the collection with no newline."""
    src = "Los precios son [10, 20, 30].\nHablá los precios.\n"
    out = inflexion.run_source(src)
    assert not out.endswith("\n")
    assert out == "[10, 20, 30]"


# ---------------------------------------------------------------------------
# Distinction from Decí — same value, different termination
# ---------------------------------------------------------------------------


def test_decir_and_hablar_distinguished() -> None:
    """`Decí "hola".` produces 'hola\\n'; `Hablá "hola".` produces 'hola'."""
    assert inflexion.run_source('Decí "hola".\n') == "hola\n"
    assert inflexion.run_source('Hablá "hola".\n') == "hola"


def test_mixed_decir_hablar() -> None:
    """Mix the two: tokens via Hablá, terminated utterance via Decí."""
    src = (
        'Hablá "Hello".\n'
        'Hablá ", ".\n'
        'Decí "world!".\n'
    )
    assert inflexion.run_source(src) == "Hello, world!\n"


# ---------------------------------------------------------------------------
# Character-code → character → Hablá (BF interpreter pattern)
# ---------------------------------------------------------------------------


def test_hablar_character_from_code() -> None:
    """The BF `.` pattern: emit a char from its ASCII code without newline."""
    src = "Hablá el carácter del código 65.\n"
    assert inflexion.run_source(src) == "A"


def test_hablar_streams_characters() -> None:
    """Streaming five chars from codes produces a single five-char string."""
    src = (
        "Hablá el carácter del código 72.\n"
        "Hablá el carácter del código 101.\n"
        "Hablá el carácter del código 108.\n"
        "Hablá el carácter del código 108.\n"
        "Hablá el carácter del código 111.\n"
    )
    assert inflexion.run_source(src) == "Hello"
