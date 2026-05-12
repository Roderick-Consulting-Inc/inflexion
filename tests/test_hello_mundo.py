# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Phase 1 end-to-end test: Example 1 from white paper §5."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import inflexion

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "examples" / "hello-mundo.infl"


def test_hello_mundo_run_file() -> None:
    """Programmatic API: running the example file prints `Hola, mundo\\n`."""
    assert inflexion.run_file(EXAMPLE) == "Hola, mundo\n"


def test_hello_mundo_run_source() -> None:
    """Source-string API: same result as the file."""
    source = 'El saludo es "Hola, mundo".\nDecilo.\n'
    assert inflexion.run_source(source) == "Hola, mundo\n"


def test_hello_mundo_cli() -> None:
    """CLI smoke: `python -m inflexion run <file>` prints the expected text."""
    result = subprocess.run(
        [sys.executable, "-m", "inflexion", "run", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "Hola, mundo\n"
    assert result.returncode == 0
