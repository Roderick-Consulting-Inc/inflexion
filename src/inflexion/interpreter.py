# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión interpreter — Phase 6.

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

Phase 6 additions (diminutive scaling + aspect-marked lazy):
    - Diminutive / augmentative scaling is *implemented as a
      lookup-time fallback*, not a new AST node — keeping the parser
      and AST surface unchanged. An `Identifier` whose name is not
      bound in scope (and not a base numeral) is tried against the
      diminutive-suffix table; if a base-name + suffix yields a
      bound or numeral value, the scaled value is returned.
    - The numeric scaling factors are: `-ito` / `-ita` → ×½,
      `-illo` / `-illa` → ×¼, `-ón` / `-ona` → ×2, `-azo` / `-aza`
      → ×4. These are coined extensions of standard Spanish
      diminutive / augmentative morphology (paper §3.5); the factors
      are language-internal, not derived from natural-language
      register. When the base value and scaling factor combine to an
      exact integer (the common case for halving an even number),
      the result is returned as an `int` rather than a `float`.
    - A function-call name that is not a registered function but
      that, after suffix-stripping, *would* be a registered function,
      raises a specific `InflexionRuntimeError` naming the convention
      — e.g. `busquito` invoked when `buscar` is defined but no
      `busquito` variant is registered.
    - Aspect-marked operations: an `AspectMarkedOperation` statement
      dispatches on the (verb-lemma, operation) pair to a Phase-6
      backend. The imperfective form prints the first six terms of
      the operation's lazy stream followed by a `, ...` truncation
      marker. The perfective form computes eagerly without printing
      — paper §5 Example 2 reads the perfective as value-producing
      whose effect is visible downstream (via `Cuando`, a `ser` bind,
      etc.); Phase 6 wires the basic case and defers binding-target
      capture to a later installment.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from enum import Enum

from .ast import (
    AspectMarkedOperation,
    BinaryOp,
    BindingEstar,
    BindingSer,
    BindingSerPlural,
    BodySequence,
    CharCode,
    CliticImperativeCall,
    CodeToChar,
    ComparisonCondition,
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
    IfExpression,
    IfStatement,
    ImperativeCall,
    IntLit,
    ListIndexGet,
    ListIndexSet,
    ListLit,
    MutationCommand,
    MutationSequence,
    NegatedCondition,
    Program,
    Reduction,
    Statement,
    StdinReadLine,
    StdinReadNumber,
    StringCharAt,
    StringChars,
    StringLen,
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
    # Phase 7c stdin: root env holds the line buffer and cursor.
    stdin_lines: list[str] = field(default_factory=list)
    stdin_pos: int = field(default=0)

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

    def read_stdin_line(self) -> str:
        """Read the next line from the stdin stream (Phase 7c).

        The root environment holds the stdin line buffer (``stdin_lines``
        field, set by `run_source` / `run`). Returns the empty string
        when the buffer is exhausted (EOF convention).
        """
        root = self._root()
        lines = root.stdin_lines
        pos = root.stdin_pos
        if pos >= len(lines):
            return ""
        root.stdin_pos = pos + 1
        return lines[pos]

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
    left_is_coll = _is_collection(left)
    right_is_coll = _is_collection(right)
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


# Diminutive / augmentative suffix → scaling factor (Phase 6, paper §3.5).
# The factors are language-internal commitments, not derived from
# natural-language register. Order matters here: longer suffixes are
# checked first so `-illa` wins over `-la`, `-azo` over `-zo`, etc.
_DIMINUTIVE_SUFFIXES: tuple[tuple[str, float], ...] = (
    ("illa", 0.25),
    ("illo", 0.25),
    ("ita", 0.5),
    ("ito", 0.5),
    ("ona", 2.0),
    ("aza", 4.0),
    ("azo", 4.0),
    ("ón", 2.0),
)


# A tiny Spanish-numeral table so `cincón`, `cinquito`, etc. resolve
# even though `cinco` is not a binding. Phase 6 wires the cardinals
# 0–10; future phases can extend this without re-touching the
# diminutive-lookup helper.
_NUMERAL_VALUES: dict[str, int] = {
    "cero": 0,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
}


def _diminutive_base_candidates(name: str) -> list[tuple[str, float]]:
    """Return plausible (base, factor) pairs for `name` under diminutive morphology.

    The Spanish morphology for diminutive / augmentative suffixes on a
    noun involves dropping the final unstressed vowel of the base and
    occasionally restoring an orthographic spelling (`c` → `qu` before
    `i`/`e`, `g` → `gu`, `z` → `c`). Phase 6's reverse-derivation is
    conservative: for each suffix that `name` could carry, the helper
    returns a list of plausible bases ordered from most-likely to
    least-likely. The caller looks each up in turn against the binding
    environment and the numeral table.

    The minimum count of letters in the base stem is two — this rules
    out spurious matches like stripping `ito` from `pinto` (which
    happens to end in `ito` but is not a diminutive form).
    """
    results: list[tuple[str, float]] = []
    for suffix, factor in _DIMINUTIVE_SUFFIXES:
        if not name.endswith(suffix):
            continue
        stem = name[: -len(suffix)]
        if len(stem) < 2:
            continue
        candidates = [stem]
        # Restore `qu` (before front vowels) back to `c`.
        if stem.endswith("qu"):
            candidates.append(stem[:-2] + "c")
        # Try common final-vowel restorations.
        for ending in ("o", "a", "e"):
            candidates.append(stem + ending)
            if stem.endswith("qu"):
                candidates.append(stem[:-2] + "c" + ending)
        # De-duplicate while preserving order.
        seen: set[str] = set()
        for cand in candidates:
            if cand in seen:
                continue
            seen.add(cand)
            results.append((cand, factor))
    return results


def _scale_value(value: object, factor: float) -> object:
    """Apply a diminutive / augmentative scaling factor to a numeric value.

    Returns an `int` when the scaled value is an exact integer (the
    common case for halving an even number or doubling), otherwise a
    `float`. Tuples (collection values) are scaled element-wise.
    """
    if _is_collection(value):
        return tuple(_scale_value(elt, factor) for elt in value)  # type: ignore[union-attr]
    if not _is_scalar_number(value):
        raise InflexionRuntimeError(
            f"Cannot apply diminutive / augmentative scaling to non-numeric "
            f"value {value!r}."
        )
    scaled = value * factor
    if isinstance(scaled, float) and scaled.is_integer():
        return int(scaled)
    return scaled


def _try_diminutive_value_lookup(
    name: str, env: Environment
) -> object | None:
    """Return the scaled value of `name` if it is a diminutive of a known base.

    Lookup order for each candidate base:
        1. Binding environment (`env.lookup`).
        2. Numeral table (`_NUMERAL_VALUES`).

    Returns `None` if no base resolves; the caller then surfaces the
    original "unknown binding" error so the user sees a message keyed
    on the form they wrote, not on a synthetic stem.
    """
    for base, factor in _diminutive_base_candidates(name):
        try:
            base_value = env.lookup(base)
        except InflexionRuntimeError:
            base_value = None
        if base_value is not None:
            return _scale_value(base_value, factor)
        if base in _NUMERAL_VALUES:
            return _scale_value(_NUMERAL_VALUES[base], factor)
    return None


def _try_diminutive_function_variant(
    name: str, env: Environment
) -> None:
    """If `name` is a diminutive of a registered function, raise the variant error.

    Phase 6 contract: when a function-call's name doesn't match any
    registered function but, after suffix-stripping, would name one,
    raise `InflexionRuntimeError` with a message naming the convention.
    A user that writes `busquito el dato.` when only `buscar` is
    defined gets a message pointing at the diminutive convention.

    Function names are infinitives; the stripped diminutive stem is a
    noun-shaped fragment, so we additionally try appending each of the
    Spanish infinitive endings (`-ar` / `-er` / `-ir`) to each base
    candidate when looking up the registry. `busquito` → stem `busqu`
    → orthographic-restore to `busc` → `buscar` (registered).
    """
    for base, factor in _diminutive_base_candidates(name):
        for completion in ("", "ar", "er", "ir"):
            candidate = base + completion
            try:
                env.get_function(candidate)
            except InflexionRuntimeError:
                continue
            register = "cheap" if factor < 1 else "thorough"
            raise InflexionRuntimeError(
                f"Function variant {name!r} (a {register} variant of "
                f"{candidate!r}) is not registered. Phase 6 accepts the "
                f"morphological form but requires the variant to be "
                f"explicitly defined. Define a separate "
                f"`La función {name}, que toma …, es ….` if the "
                f"{register} variant has a distinct body."
            )


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

    Phase 6 addition: if the call's name isn't a registered function
    but is morphologically a diminutive / augmentative of one, raise
    a clear "variant not registered" error (paper §3.5 — Phase 6
    accepts the morphology but requires explicit variant definition).
    """
    try:
        fn = env.get_function(call.name)
    except InflexionRuntimeError:
        # Phase 6: try to surface a diminutive-variant-specific error
        # before falling through to the generic unknown-function error.
        _try_diminutive_function_variant(call.name, env)
        raise
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
    if _is_collection(value):
        inner = ", ".join(repr(elt) for elt in value)  # type: ignore[union-attr]
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
    if not _is_collection(target_value):
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
        # Phase 6: an Identifier lookup that fails first checks whether
        # the surface form is a diminutive / augmentative of a known
        # binding or numeral. The original error is re-raised if no
        # base resolves, so the user sees a message keyed on what they
        # wrote rather than on a synthetic stem.
        try:
            return env.lookup(expr.name)
        except InflexionRuntimeError:
            scaled = _try_diminutive_value_lookup(expr.name, env)
            if scaled is not None:
                return scaled
            raise
    if isinstance(expr, BinaryOp):
        return _broadcast(
            expr.op, _eval_expr(expr.left, env), _eval_expr(expr.right, env)
        )
    if isinstance(expr, FunctionCall):
        return _eval_function_call(expr, env)
    if isinstance(expr, Reduction):
        return _eval_reduction(expr, env)
    # Phase 7b: if-then-else expression.
    if isinstance(expr, IfExpression):
        if _eval_comparison_condition(expr.condition, env):
            return _eval_expr(expr.then_value, env)
        return _eval_expr(expr.else_value, env)
    # Phase 7c: string operations.
    if isinstance(expr, StringLen):
        s = _eval_expr(expr.target, env)
        if not isinstance(s, str):
            raise InflexionRuntimeError(
                f"`el largo de` requires a string; got {s!r}."
            )
        return len(s)
    if isinstance(expr, StringCharAt):
        idx = _eval_expr(expr.index, env)
        s = _eval_expr(expr.target, env)
        if not isinstance(s, str):
            raise InflexionRuntimeError(
                f"`el carácter N de` requires a string; got {s!r}."
            )
        if not isinstance(idx, int):
            raise InflexionRuntimeError(
                f"`el carácter N de` index must be an integer; got {idx!r}."
            )
        if idx < 1 or idx > len(s):
            raise InflexionRuntimeError(
                f"`el carácter {idx} de` is out of range for string of length {len(s)}."
            )
        return s[idx - 1]  # 1-indexed
    if isinstance(expr, CharCode):
        ch = _eval_expr(expr.target, env)
        if not isinstance(ch, str) or len(ch) != 1:
            raise InflexionRuntimeError(
                f"`el código de` requires a single-character string; got {ch!r}."
            )
        return ord(ch)
    if isinstance(expr, CodeToChar):
        code = _eval_expr(expr.code, env)
        if not isinstance(code, int):
            raise InflexionRuntimeError(
                f"`el carácter del código` requires an integer; got {code!r}."
            )
        return chr(code)
    if isinstance(expr, StringChars):
        s = _eval_expr(expr.target, env)
        if not isinstance(s, str):
            raise InflexionRuntimeError(
                f"`los caracteres de` requires a string; got {s!r}."
            )
        return tuple(s)  # tuple of single-char strings
    if isinstance(expr, ListIndexGet):
        idx = _eval_expr(expr.index, env)
        lst = _eval_expr(expr.target, env)
        if not isinstance(lst, (tuple, list)):
            raise InflexionRuntimeError(
                f"`el N-ésimo de` requires a list; got {lst!r}."
            )
        if not isinstance(idx, int):
            raise InflexionRuntimeError(
                f"`el N-ésimo de` index must be an integer; got {idx!r}."
            )
        if idx < 1 or idx > len(lst):
            raise InflexionRuntimeError(
                f"`el {idx}-ésimo de` is out of range for list of length {len(lst)}."
            )
        return lst[idx - 1]  # 1-indexed
    raise InflexionRuntimeError(f"Unsupported expression: {expr!r}")


def _eval_comparison_condition(cond: ComparisonCondition, env: Environment) -> bool:
    """Evaluate a Phase 7a indicative comparison condition.

    The left-hand side is looked up by name; the right-hand side is
    evaluated as an Expr in the current scope. Comparison operators:

        ``"es"``            Python ``==``
        ``"no_es"``         Python ``!=``
        ``"mayor_que"``     Python ``>``
        ``"menor_que"``     Python ``<``
        ``"divisible_por"`` ``lhs % rhs == 0``
    """
    lhs = env.lookup(cond.name)
    rhs = _eval_expr(cond.value, env)
    if cond.op == "es":
        return lhs == rhs
    if cond.op == "no_es":
        return lhs != rhs
    if cond.op == "mayor_que":
        return lhs > rhs  # type: ignore[operator]
    if cond.op == "menor_que":
        return lhs < rhs  # type: ignore[operator]
    if cond.op == "divisible_por":
        if not isinstance(rhs, int) or rhs == 0:
            raise InflexionRuntimeError(
                f"`es divisible por` requires a non-zero integer divisor; got {rhs!r}."
            )
        return int(lhs) % rhs == 0  # type: ignore[arg-type]
    raise InflexionRuntimeError(  # pragma: no cover — parser-filtered
        f"Unknown comparison op: {cond.op!r}"
    )


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


def _is_collection(value: object) -> bool:
    """True if `value` is a collection (tuple or mutable list).

    Phase 7c: estar-bound lists are stored as Python `list`; ser-bound
    collections remain `tuple`. Both are valid collection values.
    """
    return isinstance(value, (tuple, list))


def _format_collection(value: object) -> str:
    """Render a collection value for `Decí los X`.

    Format choice: Python-list repr (e.g. `[90.0, 180.0, 270.0, 360.0]`).
    Phase 7c: accepts both `tuple` (ser-bound) and `list` (estar-bound).
    """
    if not _is_collection(value):
        raise InflexionRuntimeError(
            f"`Decí los <name>` requires a collection; got {value!r} "
            f"(a scalar). Did you mean `Decí el {value!r}`?"
        )
    inner = ", ".join(repr(elt) for elt in value)  # type: ignore[union-attr]
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


# Phase 6 lazy-stream rendering: number of terms to print before the
# `, ...` truncation marker. Chosen as a small visible prefix that fits
# on a single line for the standard powers-of-2 demo (1, 2, 4, 8, 16, 32).
_LAZY_PREFIX_TERMS = 6


def _powers_stream(base: object):
    """Lazy generator of powers of `base`, starting at base^0 = 1."""
    if not _is_scalar_number(base):
        raise InflexionRuntimeError(
            f"Operation `potencias del N` requires a numeric base; "
            f"got {base!r}."
        )
    n = 0
    while True:
        yield base ** n
        n += 1


# Phase 6 aspect-marked operation dispatch table. The key is
# (verb_lemma, operation); the value is a callable taking the
# evaluated base value and returning an iterator. The interpreter
# wraps the iterator with either eager consumption (perfective) or
# truncated-prefix printing (imperfective).
_ASPECT_OPERATIONS_DISPATCH: dict[tuple[str, str], "object"] = {
    ("calcular", "potencia"): _powers_stream,
}


def _execute_aspect_marked(
    stmt: AspectMarkedOperation, env: Environment, out: io.StringIO
) -> None:
    """Execute an aspect-marked operation (Phase 6).

    Imperfective form (`Calculaba …`): print the first
    `_LAZY_PREFIX_TERMS` terms of the operation stream comma-separated,
    followed by `, ...`. The trailing newline matches the convention
    used by `Decí` so output composes cleanly.

    Perfective form (`Calculó …`): consume the stream eagerly into a
    finite truncation so the eager path has well-defined termination
    without binding-target capture (Phase 6 deferred). The eager path
    intentionally does *not* print — it returns the computed prefix as
    the most-recent-binding for the local scope's `lo` antecedent.
    """
    op_fn = _ASPECT_OPERATIONS_DISPATCH.get((stmt.verb_lemma, stmt.operation))
    if op_fn is None:
        raise InflexionRuntimeError(
            f"Phase 6 aspect-marked dispatch supports "
            f"{sorted(_ASPECT_OPERATIONS_DISPATCH)}; got "
            f"({stmt.verb_lemma!r}, {stmt.operation!r})."
        )
    base_value = _eval_expr(stmt.base, env)
    stream = op_fn(base_value)
    if stmt.aspect == "imperfective":
        prefix: list[object] = []
        for _ in range(_LAZY_PREFIX_TERMS):
            prefix.append(next(stream))
        rendered = ", ".join(str(elt) for elt in prefix)
        out.write(f"{rendered}, ...\n")
        return
    if stmt.aspect == "perfective":
        # Eager consumption to a finite prefix. No output — the value
        # is computed and discarded (Phase 6 has no binding-target
        # capture for aspect-marked operations).
        for _ in range(_LAZY_PREFIX_TERMS):
            next(stream)
        return
    raise InflexionRuntimeError(  # pragma: no cover - parser-filtered
        f"Unknown aspect: {stmt.aspect!r}."
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
        value = _eval_expr(stmt.value, env)
        # Phase 7c: estar-bound collections are stored as mutable Python
        # lists so that ListIndexSet can mutate individual elements.
        # Ser-bound collections remain tuples (immutable).
        if isinstance(value, tuple):
            value = list(value)
        env.bind_estar(stmt.name, value)
    elif isinstance(stmt, MutationCommand):
        fired = env.mutate(stmt.name, _eval_expr(stmt.value, env))
        for action in fired:
            _execute_statement(action, env, out)
    elif isinstance(stmt, MutationSequence):
        # Phase 7a: sequential semantics — each mutation sees prior ones.
        for mut in stmt.mutations:
            fired = env.mutate(mut.name, _eval_expr(mut.value, env))
            for action in fired:
                _execute_statement(action, env, out)
    elif isinstance(stmt, BodySequence):
        # Phase 7a: compound body (Si chain + trailing mutations).
        for sub in stmt.statements:
            _execute_statement(sub, env, out)
    elif isinstance(stmt, DecirCommand):
        # Phase 6: route through `_eval_expr(Identifier)` so the
        # diminutive / augmentative lookup fallback fires for forms
        # like `Decí la sumita.` (sumita = suma × ½) without
        # requiring an explicit `sumita` binding.
        value = _eval_expr(Identifier(stmt.name), env)
        out.write(f"{value}\n")
    elif isinstance(stmt, DecirPluralCommand):
        value = _eval_expr(Identifier(stmt.name), env)
        out.write(f"{_format_collection(value)}\n")
    elif isinstance(stmt, DecirExpr):
        value = _eval_expr(stmt.value, env)
        if _is_collection(value):
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
    elif isinstance(stmt, AspectMarkedOperation):
        _execute_aspect_marked(stmt, env, out)
    elif isinstance(stmt, DeferredBinding):
        env.register_observer(
            stmt.name, _eval_expr(stmt.trigger_value, env), stmt.action
        )
    elif isinstance(stmt, IfStatement):
        # Phase 7a: try each arm in order; execute the first matching body.
        executed = False
        for cond, body in stmt.arms:
            if _eval_comparison_condition(cond, env):
                _execute_statement(body, env, out)
                executed = True
                break
        if not executed and stmt.else_body is not None:
            _execute_statement(stmt.else_body, env, out)
    elif isinstance(stmt, ListIndexSet):
        # Phase 7c: 1-indexed set on an estar-bound list (mutates in place).
        idx = _eval_expr(stmt.index, env)
        new_val = _eval_expr(stmt.value, env)
        lst = env.lookup(stmt.list_name)
        if not isinstance(lst, list):
            raise InflexionRuntimeError(
                f"`hacé que el N-ésimo de {stmt.list_name!r} esté en …` requires a "
                f"mutable list (estar-bound); got {lst!r}."
            )
        if not isinstance(idx, int):
            raise InflexionRuntimeError(
                f"List index must be an integer; got {idx!r}."
            )
        if idx < 1 or idx > len(lst):
            raise InflexionRuntimeError(
                f"Index {idx} out of range for list of length {len(lst)}."
            )
        lst[idx - 1] = new_val  # 1-indexed, mutate in-place
    elif isinstance(stmt, StdinReadLine):
        # Phase 7c: read a line from the stdin stream in the environment.
        line = env.read_stdin_line()
        # Bind as estar (mutable) so the value can be overwritten in loops.
        if stmt.name in env.cells:
            env.mutate(stmt.name, line)
        else:
            env.bind_estar(stmt.name, line)
    elif isinstance(stmt, StdinReadNumber):
        line = env.read_stdin_line()
        try:
            number = int(line.strip())
        except ValueError as exc:
            raise InflexionRuntimeError(
                f"`Escuchá un número` could not parse {line!r} as an integer."
            ) from exc
        if stmt.name in env.cells:
            env.mutate(stmt.name, number)
        else:
            env.bind_estar(stmt.name, number)
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
