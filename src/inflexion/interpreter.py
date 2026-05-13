# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión interpreter — Phase 3b.

Walks the AST, evaluating bindings into an Environment that distinguishes
*ser* (immutable) from *estar* (mutable) bindings, dispatches imperatives,
and (Phase 3a) supports subjunctive deferred bindings: `Cuando el X esté
en Y, <imperative>` registers a one-shot observer on the mutable cell `X`
that fires its action when a subsequent mutation sets `X` equal to `Y`.

Phase 3b additions:
    - Integer arithmetic in expression position (`+` via `más`, `−` via
      `menos`) on bindings and literals.
    - Negated subjunctive condition (`no esté en Y`) — fires when the
      cell's current value is NOT equal to Y. Used as the head of a
      `Mientras` loop; not yet supported by `Cuando`.
    - `Mientras <condition>, hacé <imperative>` while-loop with a hard
      safety cap on iterations (see `MAX_MIENTRAS_ITERATIONS`) so a
      mis-bounded loop fails fast instead of hanging the interpreter.

Phase 3b simplifications retained:
    - The clitic `lo` on a vos-imperative still dereferences the most-recent
      binding (Phase 1 anaphora). Proper resolution lands later.
    - The only imperative verbs wired up are `decir` (print) and `hacer` (the
      mutation marker `Hacé que ...`).
    - Equality is value-identity (Python `==`). Arithmetic comparisons
      other than equality (`<`, `>`, `≥`) are deferred to Phase 4+.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from enum import Enum

from .ast import (
    BinaryOp,
    BindingEstar,
    BindingSer,
    Condition,
    DecirCommand,
    DecirExpr,
    DecirLiteral,
    DeferredBinding,
    EstaCondition,
    Expr,
    Identifier,
    ImperativeCall,
    IntLit,
    MutationCommand,
    NegatedCondition,
    Program,
    Statement,
    StringLit,
    WhileLoop,
)


# Hard safety cap on `Mientras` iteration count. Phase 3b is intentionally
# not aiming for unbounded recursion or coinduction; a runaway loop should
# fail fast with a clear error rather than hang the interpreter.
MAX_MIENTRAS_ITERATIONS = 100_000


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
    if isinstance(expr, BinaryOp):
        left = _eval_expr(expr.left, env)
        right = _eval_expr(expr.right, env)
        # Phase 3b restricts arithmetic to integers. Strings (or any
        # non-int operand) surface as a runtime error so a typo like
        # `Decí el saludo más 1` doesn't silently concatenate.
        if not isinstance(left, int) or isinstance(left, bool):
            raise InflexionRuntimeError(
                f"Arithmetic operand is not an integer: {left!r} "
                f"(in `{expr.op}`)."
            )
        if not isinstance(right, int) or isinstance(right, bool):
            raise InflexionRuntimeError(
                f"Arithmetic operand is not an integer: {right!r} "
                f"(in `{expr.op}`)."
            )
        if expr.op == "más":
            return left + right
        if expr.op == "menos":
            return left - right
        raise InflexionRuntimeError(  # pragma: no cover - parser-filtered
            f"Unsupported arithmetic operator: {expr.op!r}"
        )
    raise InflexionRuntimeError(f"Unsupported expression: {expr!r}")


def _eval_condition(cond: Condition, env: Environment) -> bool:
    """Evaluate a `Mientras`/`Cuando` condition head against the current env.

    `EstaCondition` is true iff the named cell's value equals the
    trigger; `NegatedCondition` inverts. Phase 3b uses Python `==` for
    equality; ordering comparisons are out of scope.
    """
    current = env.lookup(cond.name)
    trigger = _eval_expr(cond.trigger_value, env)
    if isinstance(cond, EstaCondition):
        return current == trigger
    if isinstance(cond, NegatedCondition):
        return current != trigger
    raise InflexionRuntimeError(  # pragma: no cover - exhaustive
        f"Unsupported condition: {cond!r}"
    )


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
    elif isinstance(stmt, DecirExpr):
        out.write(f"{_eval_expr(stmt.value, env)}\n")
    elif isinstance(stmt, DecirLiteral):
        out.write(f"{stmt.value.value}\n")
    elif isinstance(stmt, ImperativeCall):
        _execute_imperative(stmt, env, out)
    elif isinstance(stmt, DeferredBinding):
        env.register_observer(
            stmt.name, _eval_expr(stmt.trigger_value, env), stmt.action
        )
    elif isinstance(stmt, WhileLoop):
        # Bounded re-evaluation of the condition with each iteration.
        # Observers attached to the loop variable still fire from
        # within the body's `MutationCommand` branch above — `Mientras`
        # does not bypass the observer registry.
        iterations = 0
        while _eval_condition(stmt.condition, env):
            if iterations >= MAX_MIENTRAS_ITERATIONS:
                raise InflexionRuntimeError(
                    f"`Mientras` loop exceeded the safety cap of "
                    f"{MAX_MIENTRAS_ITERATIONS} iterations. Phase 3b is not "
                    f"aiming for unbounded iteration; check the loop's "
                    f"termination condition."
                )
            _execute_statement(stmt.body, env, out)
            iterations += 1
    else:  # pragma: no cover - exhaustive
        raise InflexionRuntimeError(f"Unsupported statement: {stmt!r}")


def run(program: Program, env: Environment) -> str:
    """Execute a parsed Program. Returns captured stdout."""
    out = io.StringIO()
    for stmt in program.statements:
        _execute_statement(stmt, env, out)
    return out.getvalue()
