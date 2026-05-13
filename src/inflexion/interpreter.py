# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión interpreter — Phase 5.

Walks the AST, evaluating bindings into an Environment that distinguishes
*ser* (immutable) from *estar* (mutable) bindings, dispatches imperatives,
and (Phase 3a) supports subjunctive deferred bindings: `Cuando el X esté
en Y, <imperative>` registers a one-shot observer on the mutable cell `X`
that fires its action when a subsequent mutation sets `X` equal to `Y`.

Phase 3b additions:
    - Integer arithmetic in expression position (`+` via `más`, `−` via
      `menos`) on bindings and literals.
    - Negated subjunctive condition (`no esté en Y`) — fires when the
      cell's current value is NOT equal to Y.
    - `Mientras <condition>, hacé <imperative>` while-loop with a hard
      safety cap on iterations (see `MAX_MIENTRAS_ITERATIONS`).

Phase 4 additions (number agreement → scalar / collection):
    - Collection values: a `ListLit` evaluates to a tuple. Tuples are
      treated as immutable values throughout — Phase 4 plural ser
      bindings are immutable, and there is no plural estar yet.
    - Float literals: `FloatLit` evaluates to a Python float; arithmetic
      mixing int and float promotes to float per Python's usual rules.
    - `por` (multiplication) joins `más` / `menos` as a recognised
      arithmetic operator.
    - Broadcasting:
        * scalar `op` collection  →  element-wise (collection length preserved)
        * collection `op` scalar  →  element-wise
        * collection `op` collection of equal length  → element-wise
        * collection `op` collection of different lengths → runtime error
    - `Decí los <name>` (DecirPluralCommand) prints a collection. Format
      choice: Python-list repr (e.g. `[90.0, 180.0, 270.0, 360.0]`) plus
      a trailing newline. Documented in `_format_collection`.

Phase 5 additions (function abstraction + clitic routing + reduction):
    - Function definitions register a `FunctionDef` in the environment's
      function registry (always stored at the root of the scope chain).
      Names are first-class in their own namespace, distinct from
      ser/estar bindings, so a function can share a name with a binding
      without collision (in practice we recommend against it).
    - Function calls (`FunctionCall`) evaluate args in the *calling*
      scope, then push a child scope with the formal parameters bound
      as fresh *ser* cells, evaluate the body, and discard the scope.
      Calling an elided-body function (body is `None`) produces a
      record-of-call string `"<name>(<arg1>, <arg2>, …)"` — the Phase 5
      contract; full semantics for elided bodies arrives with the
      ops-sem installment.
    - Clitic-stack imperatives (`CliticImperativeCall`) look up the verb
      lemma in the function registry. For Phase 5 the call is
      side-effecting: it prints a record line capturing the routing
      `"<verb>(<clitic1>, <clitic2>, …)"` to stdout. Phase 5 does not
      yet bind clitic values; that lands with the ops-sem paper.
    - Reductions (`Reduction`) evaluate the target to a collection and
      fold it under a dispatch-table-resolved op. `sumar` → built-in
      `sum`; other ops can be added by extending `_REDUCTION_OPS`
      without re-touching the parse shape.

Phase 5 simplifications carried forward:
    - The clitic `lo` on a single-clitic vos-imperative still
      dereferences the most-recent binding (Phase 1 anaphora).
    - Equality is value-identity (Python `==`).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from enum import Enum

from .ast import (
    BinaryOp,
    BindingEstar,
    BindingSer,
    BindingSerPlural,
    CliticImperativeCall,
    Condition,
    DecirCommand,
    DecirExpr,
    DecirLiteral,
    DecirPluralCommand,
    DeferredBinding,
    EstaCondition,
    Expr,
    FloatLit,
    FunctionCall,
    FunctionDef,
    Identifier,
    ImperativeCall,
    IntLit,
    ListLit,
    MutationCommand,
    NegatedCondition,
    Program,
    Reduction,
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

    Phase 5 adds:
        - `parent`: optional parent scope for lexical lookup. A function
          call pushes a child whose `parent` points back at the call
          site's scope, so the body can see outer bindings while keeping
          its own parameter bindings local. Mutations and observer
          registrations always target the *local* scope and raise if the
          name is not bound locally — outer-scope mutation is not
          supported in Phase 5.
        - `functions`: a per-root function registry. All `define_function`
          / `get_function` operations walk to the root of the parent
          chain, so functions are effectively top-level even when defined
          inside a child scope (Phase 5 forbids the latter at the parse
          shape, but the runtime is permissive).
    """

    cells: dict[str, _Cell] = field(default_factory=dict)
    binding_order: list[str] = field(default_factory=list)
    deferred: dict[str, list[tuple[object, "Statement"]]] = field(default_factory=dict)
    parent: "Environment | None" = None
    functions: dict[str, FunctionDef] = field(default_factory=dict)

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
        """Look up `name` locally, then walk the parent chain (Phase 5)."""
        if name in self.cells:
            return self.cells[name].value
        if self.parent is not None:
            return self.parent.lookup(name)
        raise InflexionRuntimeError(f"Unknown binding: {name!r}")

    def most_recent(self) -> object:
        """Most-recent binding in the *local* scope (Phase 1 anaphora).

        Walks to parent scopes if the local scope has none — a Phase 5
        consideration so that `Decilo` after a function call still
        dereferences the caller's most-recent binding rather than failing.
        """
        if self.binding_order:
            return self.cells[self.binding_order[-1]].value
        if self.parent is not None:
            return self.parent.most_recent()
        raise InflexionRuntimeError(
            "Clitic `lo` has no antecedent: no bindings in scope."
        )

    def _root(self) -> "Environment":
        """Walk to the root of the parent chain (where functions live)."""
        env = self
        while env.parent is not None:
            env = env.parent
        return env

    def define_function(self, fn: FunctionDef) -> None:
        """Register a function in the root scope's function registry.

        Phase 5: redefinition of an existing function is a runtime error,
        matching the immutability discipline of *ser* bindings — the
        relative-clause function-def syntax is the *ser* / function
        analogue.
        """
        root = self._root()
        if fn.name in root.functions:
            raise InflexionRuntimeError(
                f"Cannot redefine function {fn.name!r}: already defined."
            )
        root.functions[fn.name] = fn

    def get_function(self, name: str) -> FunctionDef:
        """Look up a function by name in the root scope's registry."""
        root = self._root()
        if name not in root.functions:
            raise InflexionRuntimeError(
                f"Unknown function: {name!r}. Define it with "
                f"`La función {name}, que toma …, es ….`."
            )
        return root.functions[name]

    def child_scope(self) -> "Environment":
        """Construct a fresh child scope rooted at this env (Phase 5)."""
        return Environment(parent=self)


def _is_scalar_number(value: object) -> bool:
    """True if `value` is a numeric scalar (int or float, but not bool)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_numeric(value: object, op: str) -> None:
    """Raise if `value` is not a numeric scalar (used inside element-wise apply)."""
    if not _is_scalar_number(value):
        raise InflexionRuntimeError(
            f"Arithmetic operand is not a number: {value!r} (in `{op}`)."
        )


def _apply_scalar(op: str, left: float, right: float) -> float:
    """Apply a Phase-4 binary arithmetic op to two numeric scalars."""
    if op == "más":
        return left + right
    if op == "menos":
        return left - right
    if op == "por":
        return left * right
    raise InflexionRuntimeError(  # pragma: no cover - parser-filtered
        f"Unsupported arithmetic operator: {op!r}"
    )


def _broadcast(op: str, left: object, right: object) -> object:
    """Apply `op` to `left` and `right` with Phase 4 broadcast semantics.

    Rules:
        - scalar op scalar          → scalar
        - tuple  op scalar          → tuple (element-wise)
        - scalar op tuple           → tuple (element-wise)
        - tuple  op tuple (eq len)  → tuple (element-wise)
        - tuple  op tuple (mismatch)→ InflexionRuntimeError

    Phase 4 collections are represented as tuples. Mixed-type
    collections (e.g. a tuple containing both numbers and strings) are
    out of scope; element-wise apply checks each operand for numericness
    at use time and raises on non-numeric content.
    """
    left_is_coll = isinstance(left, tuple)
    right_is_coll = isinstance(right, tuple)
    if left_is_coll and right_is_coll:
        if len(left) != len(right):
            raise InflexionRuntimeError(
                f"Collection-arithmetic length mismatch (`{op}`): "
                f"left has {len(left)} elements, right has {len(right)}."
            )
        result: list[object] = []
        for l_elt, r_elt in zip(left, right):
            _check_numeric(l_elt, op)
            _check_numeric(r_elt, op)
            result.append(_apply_scalar(op, l_elt, r_elt))
        return tuple(result)
    if left_is_coll:
        _check_numeric(right, op)
        scalar = right
        out: list[object] = []
        for elt in left:
            _check_numeric(elt, op)
            out.append(_apply_scalar(op, elt, scalar))
        return tuple(out)
    if right_is_coll:
        _check_numeric(left, op)
        scalar = left
        out_r: list[object] = []
        for elt in right:
            _check_numeric(elt, op)
            out_r.append(_apply_scalar(op, scalar, elt))
        return tuple(out_r)
    # Both scalar.
    _check_numeric(left, op)
    _check_numeric(right, op)
    return _apply_scalar(op, left, right)


# Reduction dispatch table (Phase 5). Maps a verb-infinitive surface form
# to a Python callable that takes a tuple-of-numbers and returns the
# folded scalar. Wiring `sumar` is the Phase 5 minimum; other ops
# (`multiplicar`, `promediar`, etc.) can land later without re-touching
# the parser.
_REDUCTION_OPS: dict[str, "object"] = {
    "sumar": sum,
}


def _eval_function_call(call: FunctionCall, env: Environment) -> object:
    """Evaluate a function call: bind args in a child scope, run the body.

    Phase 5 evaluation order:
        1. Look up the function by name (raises if unknown).
        2. Verify arg-count == param-count (raises on mismatch).
        3. Evaluate each arg in the *calling* scope.
        4. Push a child scope, bind formal parameters as fresh *ser*
           cells (so the body cannot mutate its own parameters).
        5. If the body is `None` (elided), return a record-of-call
           string; otherwise evaluate the body and return its value.
    """
    fn = env.get_function(call.name)
    if len(call.args) != len(fn.params):
        raise InflexionRuntimeError(
            f"Function {call.name!r} expects {len(fn.params)} argument(s) "
            f"({', '.join(fn.params) or '(none)'}); got {len(call.args)}."
        )
    arg_values = [_eval_expr(a, env) for a in call.args]
    if fn.body is None:
        # Elided body — Phase 5 contract is a record-of-call string. The
        # caller may print it via `Decí` or discard it.
        rendered = ", ".join(_render_record_value(v) for v in arg_values)
        return f"{fn.name}({rendered})"
    scope = env.child_scope()
    for name, value in zip(fn.params, arg_values):
        scope.bind_ser(name, value)
    return _eval_expr(fn.body, scope)


def _render_record_value(value: object) -> str:
    """Render an arg value inside a record-of-call string.

    Tuples are rendered with the same Python-list-repr shape that
    `_format_collection` produces, so the record line round-trips
    cleanly when the user pipes it to `Decí`.
    """
    if isinstance(value, tuple):
        inner = ", ".join(repr(elt) for elt in value)
        return f"[{inner}]"
    return repr(value) if isinstance(value, str) else str(value)


def _eval_reduction(red: Reduction, env: Environment) -> object:
    """Evaluate `el resultado de <op> los X` by folding the target collection."""
    op_fn = _REDUCTION_OPS.get(red.op)
    if op_fn is None:
        raise InflexionRuntimeError(
            f"Phase 5 supports reduction operators: "
            f"{sorted(_REDUCTION_OPS)}. Got: {red.op!r}."
        )
    target_value = _eval_expr(red.target, env)
    if not isinstance(target_value, tuple):
        raise InflexionRuntimeError(
            f"Reduction `el resultado de {red.op} …` requires a collection "
            f"target; got scalar {target_value!r}."
        )
    return op_fn(target_value)


def _eval_expr(expr: Expr, env: Environment) -> object:
    if isinstance(expr, StringLit):
        return expr.value
    if isinstance(expr, IntLit):
        return expr.value
    if isinstance(expr, FloatLit):
        return expr.value
    if isinstance(expr, ListLit):
        # Element-wise eval; result is a Python tuple (immutable).
        return tuple(_eval_expr(e, env) for e in expr.elements)
    if isinstance(expr, Identifier):
        return env.lookup(expr.name)
    if isinstance(expr, BinaryOp):
        return _broadcast(
            expr.op, _eval_expr(expr.left, env), _eval_expr(expr.right, env)
        )
    if isinstance(expr, FunctionCall):
        return _eval_function_call(expr, env)
    if isinstance(expr, Reduction):
        return _eval_reduction(expr, env)
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


def _format_collection(value: object) -> str:
    """Render a collection value for `Decí los X`.

    Format choice: Python-list repr (e.g. `[90.0, 180.0, 270.0, 360.0]`).
    Rationale: round-trippable with the list-literal source syntax,
    unambiguous on element type (a float prints with its `.0`), and
    keeps the prose distinct from a single scalar print. The
    JSON-style and Spanish-prose alternatives the spec offers were
    considered; the list-repr form was chosen because it is the cheapest
    output that survives reparse by the same lexer.
    """
    if not isinstance(value, tuple):
        raise InflexionRuntimeError(
            f"`Decí los <name>` requires a collection; got {value!r} "
            f"(a scalar). Did you mean `Decí el {value!r}`?"
        )
    inner = ", ".join(repr(elt) for elt in value)
    return f"[{inner}]"


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


def _execute_clitic_imperative(
    call: CliticImperativeCall, env: Environment, out: io.StringIO
) -> None:
    """Execute a vos-imperative carrying a clitic stack (Phase 5).

    The verb name is looked up in the function registry. For Phase 5 the
    semantics is a record-of-call line written to stdout, capturing the
    routing through the clitic positions. The line is of the form
    `<verb>(<clitic1>, <clitic2>, …)` with the clitics in fixed Spanish
    order.

    An unknown verb raises a clear error pointing the user at the
    function-definition syntax — the most common cause of the failure.
    """
    fn = env.get_function(call.verb_lemma)
    rendered_clitics = ", ".join(call.clitics)
    if fn.body is None:
        # Elided body (Phase 5 contract): record-of-call side effect.
        out.write(f"{fn.name}({rendered_clitics})\n")
        return
    # Defined body but no value bindings yet for the clitic positions —
    # Phase 5 stops at logging the call shape; full positional routing
    # arrives with the ops-sem paper. We still print the record so the
    # call is observable.
    out.write(f"{fn.name}({rendered_clitics})\n")


def _execute_statement(
    stmt: Statement, env: Environment, out: io.StringIO
) -> None:
    """Execute a single statement against `env`, writing any output to `out`.

    Used both for top-level statements and for the actions of fired
    deferred bindings.
    """
    if isinstance(stmt, BindingSer):
        env.bind_ser(stmt.name, _eval_expr(stmt.value, env))
    elif isinstance(stmt, BindingSerPlural):
        value = _eval_expr(stmt.value, env)
        if not isinstance(value, tuple):
            # Phase 4 invariant: a plural ser binding must hold a
            # collection. The parser already rejects scalar-literal
            # RHS; this guard catches the runtime case where an
            # identifier-on-the-right turned out to be scalar.
            raise InflexionRuntimeError(
                f"Plural binding `Los {stmt.name} son …` requires a "
                f"collection-valued RHS; evaluated to scalar {value!r}."
            )
        env.bind_ser(stmt.name, value)
    elif isinstance(stmt, BindingEstar):
        env.bind_estar(stmt.name, _eval_expr(stmt.value, env))
    elif isinstance(stmt, MutationCommand):
        fired = env.mutate(stmt.name, _eval_expr(stmt.value, env))
        for action in fired:
            _execute_statement(action, env, out)
    elif isinstance(stmt, DecirCommand):
        out.write(f"{env.lookup(stmt.name)}\n")
    elif isinstance(stmt, DecirPluralCommand):
        out.write(f"{_format_collection(env.lookup(stmt.name))}\n")
    elif isinstance(stmt, DecirExpr):
        value = _eval_expr(stmt.value, env)
        if isinstance(value, tuple):
            out.write(f"{_format_collection(value)}\n")
        else:
            out.write(f"{value}\n")
    elif isinstance(stmt, DecirLiteral):
        out.write(f"{stmt.value.value}\n")
    elif isinstance(stmt, ImperativeCall):
        _execute_imperative(stmt, env, out)
    elif isinstance(stmt, FunctionDef):
        env.define_function(stmt)
    elif isinstance(stmt, CliticImperativeCall):
        _execute_clitic_imperative(stmt, env, out)
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
