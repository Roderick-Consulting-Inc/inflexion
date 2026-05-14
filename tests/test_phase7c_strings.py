# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 7c tests: string operations.

Covers:
    - el largo de <str>          → length
    - el carácter N de <str>     → 1-indexed char-at
    - el código de <char>        → ord
    - el carácter del código N   → chr
    - los caracteres de <str>    → list of single-char strings
"""
from __future__ import annotations

import inflexion


# ---------------------------------------------------------------------------
# el largo de
# ---------------------------------------------------------------------------


def test_largo_basic() -> None:
    """el largo de 'hola' = 4."""
    src = 'El s es "hola".\nEl n es el largo de el s.\nDecí el n.\n'
    assert inflexion.run_source(src) == "4\n"


def test_largo_empty() -> None:
    """el largo de '' = 0."""
    src = 'El s es "".\nEl n es el largo de el s.\nDecí el n.\n'
    assert inflexion.run_source(src) == "0\n"


def test_largo_single_char() -> None:
    """el largo de 'x' = 1."""
    src = 'El s es "x".\nEl n es el largo de el s.\nDecí el n.\n'
    assert inflexion.run_source(src) == "1\n"


# ---------------------------------------------------------------------------
# el carácter N de
# ---------------------------------------------------------------------------


def test_caracter_first() -> None:
    """el carácter 1 de 'hola' = 'h'  (1-indexed)."""
    src = 'El s es "hola".\nEl c es el carácter 1 de el s.\nDecí el c.\n'
    assert inflexion.run_source(src) == "h\n"


def test_caracter_last() -> None:
    """el carácter 4 de 'hola' = 'a'."""
    src = 'El s es "hola".\nEl c es el carácter 4 de el s.\nDecí el c.\n'
    assert inflexion.run_source(src) == "a\n"


def test_caracter_middle() -> None:
    """el carácter 2 de 'hola' = 'o'."""
    src = 'El s es "hola".\nEl c es el carácter 2 de el s.\nDecí el c.\n'
    assert inflexion.run_source(src) == "o\n"


def test_caracter_out_of_range() -> None:
    """el carácter 5 de 'hola' raises a runtime error (1-indexed, length=4)."""
    from inflexion.interpreter import InflexionRuntimeError
    src = 'El s es "hola".\nEl c es el carácter 5 de el s.\nDecí el c.\n'
    with pytest.raises(InflexionRuntimeError, match="out of range"):
        inflexion.run_source(src)


import pytest  # noqa: E402 (after the first use to keep tests readable)


# ---------------------------------------------------------------------------
# el código de
# ---------------------------------------------------------------------------


def test_codigo_A() -> None:
    """el código de 'A' = 65."""
    src = 'El c es "A".\nEl n es el código de el c.\nDecí el n.\n'
    assert inflexion.run_source(src) == "65\n"


def test_codigo_lowercase_a() -> None:
    """el código de 'a' = 97."""
    src = 'El c es "a".\nEl n es el código de el c.\nDecí el n.\n'
    assert inflexion.run_source(src) == "97\n"


def test_codigo_space() -> None:
    """el código de ' ' = 32."""
    src = 'El c es " ".\nEl n es el código de el c.\nDecí el n.\n'
    assert inflexion.run_source(src) == "32\n"


# ---------------------------------------------------------------------------
# el carácter del código N
# ---------------------------------------------------------------------------


def test_char_from_code_65() -> None:
    """el carácter del código 65 = 'A'."""
    src = "El n es 65.\nEl c es el carácter del código el n.\nDecí el c.\n"
    assert inflexion.run_source(src) == "A\n"


def test_char_from_code_97() -> None:
    """el carácter del código 97 = 'a'."""
    src = "El n es 97.\nEl c es el carácter del código el n.\nDecí el c.\n"
    assert inflexion.run_source(src) == "a\n"


def test_code_roundtrip() -> None:
    """el carácter del código (el código de 'Z') = 'Z'."""
    src = (
        'El ch es "Z".\n'
        "El cod es el código de el ch.\n"
        "El back es el carácter del código el cod.\n"
        "Decí el back.\n"
    )
    assert inflexion.run_source(src) == "Z\n"


# ---------------------------------------------------------------------------
# los caracteres de
# ---------------------------------------------------------------------------


def test_caracteres_hola() -> None:
    """los caracteres de 'hola' = ['h','o','l','a']."""
    src = (
        'El s es "hola".\n'
        "Los chars son los caracteres de el s.\n"
        "Decí los chars.\n"
    )
    assert inflexion.run_source(src) == "['h', 'o', 'l', 'a']\n"


def test_caracteres_single() -> None:
    """los caracteres de 'x' = ['x']."""
    src = (
        'El s es "x".\n'
        "Los chars son los caracteres de el s.\n"
        "Decí los chars.\n"
    )
    assert inflexion.run_source(src) == "['x']\n"
