# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 7 end-to-end tests: examples/brainfuck.infl.

The BF interpreter is implemented entirely in Inflexión: the BF source is
stored as a string, a 30-cell tape is a mutable list, and the main loop
dispatches on the current instruction character with nested Si chains.
Bracket matching is handled by a pair of recursive helper functions
(cierre1/buscar_cierre, apertura1/buscar_apertura).

The canonical Hello-World BF program (106 chars) outputs "Hello World!\\n"
(13 BF `.` operations: 12 visible chars + chr(10) for the trailing
newline).  In Inflexión, `decí el carácter del código N` appends a newline
per call, so the 13th call (outputting chr(10)) yields "\\n\\n" — producing
the three-newline tail visible in the full output repr.

Small-program unit tests swap only line 1 (`El programa es "...".`) to
keep the tape, functions, and dispatch loop unchanged.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "brainfuck.infl"

# Exact output from running the canonical Hello-World BF program through the
# Inflexión interpreter.  Each visible char occupies its own line; the BF
# trailing chr(10) produces an extra "\n\n" at the end.
EXPECTED_HELLO_WORLD = "H\ne\nl\nl\no\n \nW\no\nr\nl\nd\n!\n\n\n"


def _run_bf_program(bf_source: str) -> str:
    """Run an arbitrary BF program through brainfuck.infl.

    Replaces only line 1 (`El programa es "...".`) with the supplied BF
    source; all other source lines (tape init, helper functions, main loop)
    are kept unchanged.
    """
    lines = EXAMPLE.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[0] = f'El programa es "{bf_source}".\n'
    return inflexion.run_source("".join(lines))


# ---------------------------------------------------------------------------
# Hello-World integration tests
# ---------------------------------------------------------------------------

def test_brainfuck_hello_world_run_file() -> None:
    """Programmatic API: brainfuck.infl produces the expected Hello-World output."""
    assert inflexion.run_file(EXAMPLE) == EXPECTED_HELLO_WORLD


def test_brainfuck_hello_world_cli() -> None:
    """CLI smoke: `python -m inflexion run examples/brainfuck.infl`."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0
    assert result.stdout == EXPECTED_HELLO_WORLD


def test_brainfuck_hello_world_chars_join() -> None:
    """The first 12 output lines, joined, equal 'Hello World!'."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    visible = [ln for ln in lines if ln]  # drop the empty trailing lines
    assert "".join(visible) == "Hello World!"


def test_brainfuck_hello_world_line_count() -> None:
    """There are exactly 12 non-empty output lines (one per BF visible char)."""
    lines = inflexion.run_file(EXAMPLE).splitlines()
    assert len([ln for ln in lines if ln]) == 12


# ---------------------------------------------------------------------------
# Small-program unit tests (swap only the embedded BF source)
# ---------------------------------------------------------------------------

def test_brainfuck_triple_plus_dot() -> None:
    """`+++.` increments cell 0 to 3 and outputs chr(3) followed by a newline."""
    assert _run_bf_program("+++.") == "\x03\n"


def test_brainfuck_double_plus_dot() -> None:
    """`++.` increments cell 0 to 2 and outputs chr(2) followed by a newline."""
    assert _run_bf_program("++.") == "\x02\n"


def test_brainfuck_single_plus_dot() -> None:
    """`+.` increments cell 0 to 1 and outputs chr(1) followed by a newline."""
    assert _run_bf_program("+.") == "\x01\n"


def test_brainfuck_balanced_brackets_noop() -> None:
    """`[]` is a no-op when cell 0 = 0: the loop body is never entered, output is empty."""
    assert _run_bf_program("[]") == ""


def test_brainfuck_noop_program() -> None:
    """A single space (non-BF character) is treated as a no-op: no output produced.

    Note: a truly empty string ("") cannot be used here because the
    interpreter initialises `instruccion` via `el carácter 1 de el programa`
    before entering the main loop, which raises an out-of-range error on a
    zero-length string.  A space character is handled by the final `sino`
    branch of the dispatch (no-op) and exits cleanly.
    """
    assert _run_bf_program(" ") == ""


def test_brainfuck_increment_then_output_ascii_65() -> None:
    """65 increments + `.` outputs 'A' (chr(65))."""
    bf = "+" * 65 + "."
    assert _run_bf_program(bf) == "A\n"


def test_brainfuck_output_does_not_strip_non_printable() -> None:
    """Non-printable output is preserved exactly — no accidental .strip()."""
    # chr(7) = BEL — non-printable but a valid ASCII code point.
    bf = "+" * 7 + "."
    result = _run_bf_program(bf)
    assert result == "\x07\n"
    assert len(result) == 2  # the char + decí's newline
