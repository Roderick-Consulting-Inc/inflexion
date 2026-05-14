# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 7a tests: Si conditional dispatch.

Covers:
    - Single-branch hit and miss
    - If-else (two arms): hit each arm
    - Chained elif: hit the middle arm
    - All five comparison operators: es, no es, es mayor que, es menor que,
      es divisible por
    - Si with hacé que mutation as the branch body (not just Decí)
"""
from __future__ import annotations

import inflexion


# ---------------------------------------------------------------------------
# Single-branch Si (no else)
# ---------------------------------------------------------------------------


def test_single_branch_hit() -> None:
    """Si condition is true: branch body executes."""
    src = (
        "El x es 7.\n"
        'Si el x es 7, decí "lucky".\n'
    )
    assert inflexion.run_source(src) == "lucky\n"


def test_single_branch_miss() -> None:
    """Si condition is false: nothing executes (no else)."""
    src = (
        "El x es 3.\n"
        'Si el x es 7, decí "lucky".\n'
    )
    assert inflexion.run_source(src) == ""


# ---------------------------------------------------------------------------
# If-else
# ---------------------------------------------------------------------------


def test_if_else_hit_then() -> None:
    """If-else: condition true → first branch."""
    src = (
        "El x es 7.\n"
        'Si el x es 7, decí "lucky"; sino, decí "ordinary".\n'
    )
    assert inflexion.run_source(src) == "lucky\n"


def test_if_else_hit_else() -> None:
    """If-else: condition false → else branch."""
    src = (
        "El x es 3.\n"
        'Si el x es 7, decí "lucky"; sino, decí "ordinary".\n'
    )
    assert inflexion.run_source(src) == "ordinary\n"


# ---------------------------------------------------------------------------
# Chained elif
# ---------------------------------------------------------------------------


def test_chained_elif_first_arm() -> None:
    """Chained elif: first arm matches."""
    src = (
        "El x es 0.\n"
        'Si el x es 0, decí "zero"; sino, si el x es 1, decí "one"; sino, decí "other".\n'
    )
    assert inflexion.run_source(src) == "zero\n"


def test_chained_elif_middle_arm() -> None:
    """Chained elif: middle arm matches, not the last."""
    src = (
        "El x es 1.\n"
        'Si el x es 0, decí "zero"; sino, si el x es 1, decí "one"; sino, decí "other".\n'
    )
    assert inflexion.run_source(src) == "one\n"


def test_chained_elif_else_arm() -> None:
    """Chained elif: no arm matches, else executes."""
    src = (
        "El x es 99.\n"
        'Si el x es 0, decí "zero"; sino, si el x es 1, decí "one"; sino, decí "other".\n'
    )
    assert inflexion.run_source(src) == "other\n"


# ---------------------------------------------------------------------------
# All five comparison operators
# ---------------------------------------------------------------------------


def test_cmp_es_equality_true() -> None:
    """`es` — equality hit."""
    src = "El n es 5.\nSi el n es 5, decí el n.\n"
    assert inflexion.run_source(src) == "5\n"


def test_cmp_es_equality_false() -> None:
    """`es` — equality miss (no else)."""
    src = "El n es 4.\nSi el n es 5, decí el n.\n"
    assert inflexion.run_source(src) == ""


def test_cmp_no_es_inequality_true() -> None:
    """`no es` — inequality hit."""
    src = (
        "El n es 4.\n"
        'Si el n no es 5, decí "distinto".\n'
    )
    assert inflexion.run_source(src) == "distinto\n"


def test_cmp_no_es_inequality_false() -> None:
    """`no es` — inequality miss."""
    src = (
        "El n es 5.\n"
        'Si el n no es 5, decí "distinto".\n'
    )
    assert inflexion.run_source(src) == ""


def test_cmp_mayor_que_true() -> None:
    """`es mayor que` — strictly greater, hit."""
    src = (
        "El n es 10.\n"
        'Si el n es mayor que 5, decí "grande".\n'
    )
    assert inflexion.run_source(src) == "grande\n"


def test_cmp_mayor_que_false() -> None:
    """`es mayor que` — strictly greater, miss (equal is not greater)."""
    src = (
        "El n es 5.\n"
        'Si el n es mayor que 5, decí "grande".\n'
    )
    assert inflexion.run_source(src) == ""


def test_cmp_menor_que_true() -> None:
    """`es menor que` — strictly less, hit."""
    src = (
        "El n es 3.\n"
        'Si el n es menor que 5, decí "chico".\n'
    )
    assert inflexion.run_source(src) == "chico\n"


def test_cmp_menor_que_false() -> None:
    """`es menor que` — strictly less, miss (equal is not less)."""
    src = (
        "El n es 5.\n"
        'Si el n es menor que 5, decí "chico".\n'
    )
    assert inflexion.run_source(src) == ""


def test_cmp_divisible_por_true() -> None:
    """`es divisible por` — divisibility hit."""
    src = (
        "El n es 15.\n"
        'Si el n es divisible por 3, decí "fizz".\n'
    )
    assert inflexion.run_source(src) == "fizz\n"


def test_cmp_divisible_por_false() -> None:
    """`es divisible por` — divisibility miss."""
    src = (
        "El n es 7.\n"
        'Si el n es divisible por 3, decí "fizz".\n'
    )
    assert inflexion.run_source(src) == ""


def test_cmp_divisible_por_combined_fizzbuzz_step() -> None:
    """FizzBuzz logic for n=15: divisible by both 3 and 5 → FizzBuzz."""
    src = (
        "El n es 15.\n"
        'Si el n es divisible por 15, decí "FizzBuzz"; sino, '
        'si el n es divisible por 3, decí "Fizz"; sino, '
        'si el n es divisible por 5, decí "Buzz"; sino, decí el n.\n'
    )
    assert inflexion.run_source(src) == "FizzBuzz\n"


# ---------------------------------------------------------------------------
# Si body: Hacé que (mutation)
# ---------------------------------------------------------------------------


def test_si_body_mutation() -> None:
    """A Si branch can mutate a variable rather than Decí."""
    src = (
        "El x está en 0.\n"
        "El flag es 1.\n"
        "Si el flag es 1, hacé que el x esté en 42.\n"
        "Decí el x.\n"
    )
    assert inflexion.run_source(src) == "42\n"


def test_si_body_mutation_miss() -> None:
    """Si condition false: mutation body is skipped."""
    src = (
        "El x está en 0.\n"
        "El flag es 0.\n"
        "Si el flag es 1, hacé que el x esté en 42.\n"
        "Decí el x.\n"
    )
    assert inflexion.run_source(src) == "0\n"


# ---------------------------------------------------------------------------
# Si inside Mientras
# ---------------------------------------------------------------------------


def test_si_inside_mientras_compound_body() -> None:
    """Si dispatch + y-que counter increment inside Mientras (compound body).

    Tests the Phase 7a `BodySequence` path:
        Mientras …, si COND, BODY; sino, BODY; y que el i esté en el i más 1.

    FizzBuzz-lite for i=1..5: multiples of 3 → "Fizz", others → the number.
    """
    src = (
        "El i está en 1.\n"
        "Mientras el i no esté en 6, "
        'si el i es divisible por 3, decí "Fizz"; sino, decí el i; '
        "y que el i esté en el i más 1.\n"
    )
    assert inflexion.run_source(src) == "1\n2\nFizz\n4\n5\n"


def test_fizzbuzz_1_to_15() -> None:
    """FizzBuzz for 1..15 (the canonical demonstration, compound Mientras body)."""
    src = (
        "El i está en 1.\n"
        "Mientras el i no esté en 16, "
        'si el i es divisible por 15, decí "FizzBuzz"; sino, '
        'si el i es divisible por 3, decí "Fizz"; sino, '
        'si el i es divisible por 5, decí "Buzz"; sino, decí el i; '
        "y que el i esté en el i más 1.\n"
    )
    expected = (
        "1\n2\nFizz\n4\nBuzz\nFizz\n7\n8\nFizz\nBuzz\n11\nFizz\n13\n14\nFizzBuzz\n"
    )
    assert inflexion.run_source(src) == expected


# Simpler: verify Si dispatch works when Si is used outside a loop.
def test_fizzbuzz_step_3() -> None:
    """FizzBuzz-style dispatch for n=3."""
    src = (
        "El n es 3.\n"
        'Si el n es divisible por 15, decí "FizzBuzz"; sino, '
        'si el n es divisible por 3, decí "Fizz"; sino, '
        'si el n es divisible por 5, decí "Buzz"; sino, decí el n.\n'
    )
    assert inflexion.run_source(src) == "Fizz\n"


def test_fizzbuzz_step_5() -> None:
    """FizzBuzz-style dispatch for n=5."""
    src = (
        "El n es 5.\n"
        'Si el n es divisible por 15, decí "FizzBuzz"; sino, '
        'si el n es divisible por 3, decí "Fizz"; sino, '
        'si el n es divisible por 5, decí "Buzz"; sino, decí el n.\n'
    )
    assert inflexion.run_source(src) == "Buzz\n"


def test_fizzbuzz_step_7() -> None:
    """FizzBuzz-style dispatch for n=7 (no match → print n)."""
    src = (
        "El n es 7.\n"
        'Si el n es divisible por 15, decí "FizzBuzz"; sino, '
        'si el n es divisible por 3, decí "Fizz"; sino, '
        'si el n es divisible por 5, decí "Buzz"; sino, decí el n.\n'
    )
    assert inflexion.run_source(src) == "7\n"
