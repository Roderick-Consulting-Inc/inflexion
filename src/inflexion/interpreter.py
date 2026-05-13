# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión interpreter — Phase 3a.

Walks the AST, evaluating bindings into an Environment that distinguishes
*ser* (immutable) from *estar* (mutable) bindings, dispatches imperatives,
and (Phase 3a) supports subjunctive deferred bindings: `Cuando el X esté
en Y, <imperative>` registers a one-shot observer on the mutable cell `X`
that fires its action when a subsequent mutation sets `X` equal to `Y`.

Phase 3a simplifications retained:
    - The clitic `lo` on a vos-imperative still dereferences the most-recent
      binding (Phase 1 anaphora). Proper resolution lands later.
    - The only imperative verbs wired up are `decir` (print) and `hacer` (the
      mutation marker `Hacé que ...`).
    - Equality is value-identity (Python `==`); inequality / negation /
      arithmetic conditions are deferred to Phase 3b.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from enum import Enum

from .ast import (
    BindingEstar,
    BindingSer,
    DecirCommand,
    DecirLiteral,
    DeferredBinding,
    Expr,
    Identifier,
    ImperativeCall,
    IntLit,
    MutationCommand,
    Program,
    Statement,
    StringLit,
)


class InflexionRuntimeError(RuntimeError):
    """Raised when an Inflexión program is well-formed but cannot execute."""


class BindingKind(Enum):
    """*Ser* bindings are immutable; *estar* bindings are mutable."""

    SER = "ser"
    ESTAR = "estar"


@dataclass
class _Cell:
    """An environment cell: a value plus its binding-kind tag."""

    kind: BindingKind
    value: object


@dataclass
class Environment:
    """Bindings environment with ser/estar distinction.

    *Ser* bindings are immutable: a second `bind_ser` (or `mutate`) on the
    same name raises. *Estar* bindings hold a cell whose value can be
    overwritten by `mutate`; rebinding the name via another `bind_estar` is
    also rejected so the shadowing rules stay simple.

    Phase 3a adds an observer registry (`deferred`): each mutable cell can
    accumulate `(trigger_value, action)` pairs registered by `Cuando …`
    clauses. `mutate` consults the registry after writing the cell and
    returns the list of actions whose triggers fired so the run loop can
    execute them. Each fired observer is removed (one-shot).
    """

    cells: dict[str, _Cell] = field(default_factory=dict)
    binding_order: list[str] = field(default_factory=list)
    deferred: dict[str, list[tuple[object, "Statement"]]] = field(default_factory=dict)

    def bind_ser(self, name: str, value: object) -> None:
        if name in self.cells:
            raise InflexionRuntimeError(
                f"Cannot rebind {name!r}: already bound."
            )
        self.cells[name] = _Cell(kind=BindingKind.SER, value=value)
        self.binding_order.append(name)

    def bind_estar(self, name: str, value: object) -> None:
        if name in self.cells:
            raise InflexionRuntimeError(
                f"Cannot rebind {name!r}: already bound."
            )
        self.cells[name] = _Cell(kind=BindingKind.ESTAR, value=value)
        self.binding_order.append(name)

    def mutate(self, name: str, value: object) -> list["Statement"]:
        """Mutate an *estar* cell and return any observers whose trigger fired.

        Fired observers are removed from the registry (one-shot semantics).
        The caller is responsible for executing the returned actions.
        """
        if name not in self.cells:
            raise InflexionRuntimeError(
                f"Cannot mutate unknown binding {name!r}."
            )
        cell = self.cells[name]
        if cell.kind is BindingKind.SER:
            raise InflexionRuntimeError(
                f"Cannot mutate {name!r}: it is a *ser* (immutable) binding. "
                f"Use *estar* (`El {name} está en …`) to declare a mutable cell."
            )
        cell.value = value
        observers = self.deferred.get(name, [])
        if not observers:
            return []
        fired: list[Statement] = []
        remaining: list[tuple[object, Statement]] = []
        for trigger, action in observers:
            if trigger == value:
                fired.append(action)
            else:
                remaining.append((trigger, action))
        if remaining:
            self.deferred[name] = remaining
        else:
            del self.deferred[name]
        return fired

    def register_observer(
        self, name: str, trigger_value: object, action: "Statement"
    ) -> None:
        """Attach a one-shot observer to mutable cell `name`.

        Subjunctive *Cuando* binds against a name that must already exist
        and be mutable; observing a *ser* binding (or an unbound name) is
        a runtime error since such a name can never change to fire.
        """
        if name not in self.cells:
            raise InflexionRuntimeError(
                f"`Cuando` references unknown binding {name!r}."
            )
        if self.cells[name].kind is BindingKind.SER:
            raise InflexionRuntimeError(
                f"`Cuando` cannot observe {name!r}: it is a *ser* (immutable) "
                f"binding and will never change."
            )
        self.deferred.setdefault(name, []).append((trigger_value, action))

    def lookup(self, name: str) -> object:
        if name not in self.cells:
            raise InflexionRuntimeError(f"Unknown binding: {name!r}")
        return self.cells[name].value

    def most_recent(self) -> object:
        if not self.binding_order:
            raise InflexionRuntimeError(
                "Clitic `lo` has no antecedent: no bindings in scope."
            )
        return self.cells[self.binding_order[-1]].value


def _eval_expr(expr: Expr, env: Environment) -> object:
    if isinstance(expr, StringLit):
        return expr.value
    if isinstance(expr, IntLit):
        return expr.value
    if isinstance(expr, Identifier):
        return env.lookup(expr.name)
    raise InflexionRuntimeError(f"Unsupported expression: {expr!r}")


def _resolve_clitic(clitic: str, env: Environment) -> object:
    """Phase 1 anaphora kept: `lo` dereferences the most-recent binding."""
    if clitic == "lo":
        return env.most_recent()
    raise InflexionRuntimeError(
        f"Phase 2 only supports the `lo` clitic on imperatives; got {clitic!r}."
    )


def _execute_imperative(call: ImperativeCall, env: Environment, out: io.StringIO) -> None:
    if call.verb_lemma == "decir":
        if call.clitic is None:
            raise InflexionRuntimeError(
                "`Decí` without an object requires a noun phrase "
                "(`Decí el saludo`) or the enclitic form `Decilo`."
            )
        value = _resolve_clitic(call.clitic, env)
        out.write(f"{value}\n")
        return
    raise InflexionRuntimeError(
        f"Phase 2 only wires the `decir` imperative; got verb {call.verb_lemma!r}."
    )


def _execute_statement(
    stmt: Statement, env: Environment, out: io.StringIO
) -> None:
    """Execute a single statement against `env`, writing any output to `out`.

    Used both for top-level statements and for the actions of fired
    deferred bindings.
    """
    if isinstance(stmt, BindingSer):
        env.bind_ser(stmt.name, _eval_expr(stmt.value, env))
    elif isinstance(stmt, BindingEstar):
        env.bind_estar(stmt.name, _eval_expr(stmt.value, env))
    elif isinstance(stmt, MutationCommand):
        fired = env.mutate(stmt.name, _eval_expr(stmt.value, env))
        for action in fired:
            _execute_statement(action, env, out)
    elif isinstance(stmt, DecirCommand):
        out.write(f"{env.lookup(stmt.name)}\n")
    elif isinstance(stmt, DecirLiteral):
        out.write(f"{stmt.value.value}\n")
    elif isinstance(stmt, ImperativeCall):
        _execute_imperative(stmt, env, out)
    elif isinstance(stmt, DeferredBinding):
        env.register_observer(
            stmt.name, _eval_expr(stmt.trigger_value, env), stmt.action
        )
    else:  # pragma: no cover - exhaustive
        raise InflexionRuntimeError(f"Unsupported statement: {stmt!r}")


def run(program: Program, env: Environment) -> str:
    """Execute a parsed Program. Returns captured stdout."""
    out = io.StringIO()
    for stmt in program.statements:
        _execute_statement(stmt, env, out)
    return out.getvalue()
