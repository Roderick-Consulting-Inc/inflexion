# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 7+8 end-to-end tests: examples/brainfuck.infl.

The BF interpreter is implemented entirely in Inflexión: the BF source is
stored as a string, a 30-cell tape is a mutable list, and the main loop
dispatches on the current instruction character with nested Si chains.
Bracket matching is handled by a pair of recursive helper functions
(buscar_cierre / buscar_apertura).

The canonical Hello-World BF program (106 chars) outputs "Hello World!\\n"
(13 BF `.` operations: 12 visible chars + chr(10) for the trailing
newline).  BF's `.` operator uses `Hablá` (the streaming-output
imperative — mood-imperative, ongoing speech activity) rather than
`Decí` (the say imperative — committed content, terminated utterance).
The output is a single line "Hello World!\\n", matching standard BF host
behaviour.

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
# Inflexión interpreter (Hablá streams chars, no per-char newline).
EXPECTED_HELLO_WORLD = "Hello World!\n"


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
    """Programmatic API: brainfuck.infl produces the standard BF Hello-World output."""
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


def test_brainfuck_hello_world_single_line() -> None:
    """Hello World renders as one line, not 12 — Hablá streams chars."""
    assert "\n" not in EXPECTED_HELLO_WORLD.rstrip("\n")
    assert EXPECTED_HELLO_WORLD.rstrip("\n") == "Hello World!"


def test_brainfuck_hello_world_trailing_newline_from_bf_source() -> None:
    """The single trailing \\n comes from the BF program emitting chr(10), not from Inflexión."""
    out = inflexion.run_file(EXAMPLE)
    assert out.endswith("\n")
    assert out.count("\n") == 1


# ---------------------------------------------------------------------------
# Small-program unit tests (swap only the embedded BF source)
# ---------------------------------------------------------------------------

def test_brainfuck_triple_plus_dot() -> None:
    """`+++.` increments cell 0 to 3 and outputs chr(3) raw (no newline)."""
    assert _run_bf_program("+++.") == "\x03"


def test_brainfuck_double_plus_dot() -> None:
    """`++.` increments cell 0 to 2 and outputs chr(2) raw."""
    assert _run_bf_program("++.") == "\x02"


def test_brainfuck_single_plus_dot() -> None:
    """`+.` increments cell 0 to 1 and outputs chr(1) raw."""
    assert _run_bf_program("+.") == "\x01"


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
    """65 increments + `.` outputs 'A' raw (chr(65), no newline)."""
    bf = "+" * 65 + "."
    assert _run_bf_program(bf) == "A"


def test_brainfuck_output_does_not_strip_non_printable() -> None:
    """Non-printable output is preserved exactly — no accidental .strip(), no auto-newline."""
    # chr(7) = BEL — non-printable but a valid ASCII code point.
    bf = "+" * 7 + "."
    result = _run_bf_program(bf)
    assert result == "\x07"
    assert len(result) == 1  # raw byte only — no Inflexión-side newline
