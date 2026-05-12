# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión interpreter — Phase 1.

Walks the AST, evaluating ser-bindings into an Environment and dispatching
vos-imperatives to side-effect handlers. Returns captured stdout as a string.

Phase 1 simplifications:
    - The clitic `lo` (third-person singular masculine direct object) on a
      vos-imperative dereferences the most-recent immutable binding. This is
      the minimum needed to make Example 1 work; Phase 2 will replace it with
      proper anaphora resolution.
    - The only imperative verb wired up is `decir` (to say → print to stdout).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from .ast import BindingSer, Expr, Identifier, ImperativeCall, Program, StringLit


class InflexionRuntimeError(RuntimeError):
    """Raised when an Inflexión program is well-formed but cannot execute."""


@dataclass
class Environment:
    """Immutable-binding environment. Phase 2+ will add an estar-cell layer."""

    bindings: dict[str, object] = field(default_factory=dict)
    binding_order: list[str] = field(default_factory=list)

    def bind_ser(self, name: str, value: object) -> None:
        if name in self.bindings:
            raise InflexionRuntimeError(
                f"Cannot rebind {name!r}: ser-bindings are immutable."
            )
        self.bindings[name] = value
        self.binding_order.append(name)

    def lookup(self, name: str) -> object:
        if name not in self.bindings:
            raise InflexionRuntimeError(f"Unknown binding: {name!r}")
        return self.bindings[name]

    def most_recent(self) -> object:
        if not self.binding_order:
            raise InflexionRuntimeError(
                "Clitic `lo` has no antecedent: no bindings in scope."
            )
        return self.bindings[self.binding_order[-1]]


def _eval_expr(expr: Expr, env: Environment) -> object:
    if isinstance(expr, StringLit):
        return expr.value
    if isinstance(expr, Identifier):
        return env.lookup(expr.name)
    raise InflexionRuntimeError(f"Unsupported expression: {expr!r}")


def _resolve_clitic(clitic: str, env: Environment) -> object:
    """Phase 1: `lo` dereferences the most-recent binding. Other clitics fail."""
    if clitic == "lo":
        return env.most_recent()
    raise InflexionRuntimeError(
        f"Phase 1 only supports the `lo` clitic on imperatives; got {clitic!r}."
    )


def _execute_imperative(call: ImperativeCall, env: Environment, out: io.StringIO) -> None:
    if call.verb_lemma == "decir":
        if call.clitic is None:
            raise InflexionRuntimeError(
                "`Decí` without an object is not yet supported in Phase 1; "
                "use `Decilo` (decir + lo) to print the most-recent binding."
            )
        value = _resolve_clitic(call.clitic, env)
        out.write(f"{value}\n")
        return
    raise InflexionRuntimeError(
        f"Phase 1 only wires the `decir` imperative; got verb {call.verb_lemma!r}."
    )


def run(program: Program, env: Environment) -> str:
    """Execute a parsed Program. Returns captured stdout."""
    out = io.StringIO()
    for stmt in program.statements:
        if isinstance(stmt, BindingSer):
            env.bind_ser(stmt.name, _eval_expr(stmt.value, env))
        elif isinstance(stmt, ImperativeCall):
            _execute_imperative(stmt, env, out)
        else:  # pragma: no cover - exhaustive
            raise InflexionRuntimeError(f"Unsupported statement: {stmt!r}")
    return out.getvalue()
