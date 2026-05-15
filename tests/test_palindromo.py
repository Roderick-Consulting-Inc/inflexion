# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""End-to-end test: examples/palindromo.infl.

Recursive palindrome check using string char access and if-expression
recursion.
"""
from __future__ import annotations

from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "palindromo.infl"


def test_palindromo_examples() -> None:
    """neuquen → 1; hola → 0; abcba → 1."""
    output = inflexion.run_file(EXAMPLE)
    assert output == "1\n0\n1\n"


def test_palindromo_single_char() -> None:
    """A single character is trivially a palindrome."""
    src = (
        'La función palindromo_ayuda, que toma una palabra, una izq y una der, '
        'es si la izq es mayor que la der, entonces 1; '
        'sino, si la izq es la der, entonces 1; '
        'sino, si el carácter la izq de la palabra es el carácter la der de la palabra, '
        'entonces palindromo_ayuda la palabra (la izq más 1) (la der menos 1); '
        'sino, 0.\n'
        'La función palindromo, que toma una palabra, '
        'es palindromo_ayuda la palabra 1 (el largo de la palabra).\n'
        'Decí palindromo "a".\n'
    )
    assert inflexion.run_source(src).strip() == "1"


def test_palindromo_two_same_chars() -> None:
    """Two identical characters form a palindrome."""
    src = (
        'La función palindromo_ayuda, que toma una palabra, una izq y una der, '
        'es si la izq es mayor que la der, entonces 1; '
        'sino, si la izq es la der, entonces 1; '
        'sino, si el carácter la izq de la palabra es el carácter la der de la palabra, '
        'entonces palindromo_ayuda la palabra (la izq más 1) (la der menos 1); '
        'sino, 0.\n'
        'La función palindromo, que toma una palabra, '
        'es palindromo_ayuda la palabra 1 (el largo de la palabra).\n'
        'Decí palindromo "aa".\n'
    )
    assert inflexion.run_source(src).strip() == "1"
