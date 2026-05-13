# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión AST — Phase 4 node types.

Phase 2 added:
    - BindingEstar: mutable binding via *estar* (El X está en Y)
    - MutationCommand: imperative mutation (Hacé que el X esté en Y)
    - IntLit: integer numeric literal
    - DecirCommand: vos-imperative `Decí <noun-phrase>` reading by name
      (the Phase 1 `Decilo` enclitic form remains an ImperativeCall)

Phase 3a added:
    - DeferredBinding: subjunctive deferred observer
      (`Cuando el X esté en Y, <imperative>`)

Phase 3b added:
    - BinaryOp: arithmetic (`el X más N`, `el X menos N`), with operands
      themselves drawn from `Expr` so bindings and literals can both
      appear in either slot
    - EstaCondition / NegatedCondition: subjunctive condition shapes
      (`el X esté en Y` / `el X no esté en Y`) — reused as the head
      of a `mientras` clause
    - WhileLoop: bounded iteration (`Mientras <cond>, hacé <imperative>`)

Phase 4 adds (number agreement → scalar / collection):
    - FloatLit: decimal-literal support (`0.10`, `3.14`). Distinct from
      `IntLit` so downstream consumers can keep scalar-int tests cheap.
    - ListLit: homogeneous numeric collection literal (`[100, 200, 300]`).
      Phase 4 restricts element type to int / float; strings and nested
      collections are deferred.
    - BindingSerPlural: plural ser binding (`Los X son <expr>`). Parser-
      and runtime-enforced: the RHS must evaluate to a collection, and
      `Los X son 5` is a parse error per the Phase 4 simplification of
      paper §3.6 (implicit-length scalar broadcast deferred to Phase 5+).
    - DecirPluralCommand: print a collection bound under a plural article
      (`Decí los X`). Distinct from `DecirCommand` so the singular path
      stays byte-for-byte unchanged.
    - `BinaryOp.op` is extended to accept `"por"` (multiplication).

Phase 5+ will add function definitions, clitic stacks > 1, diminutive /
augmentative scaling, aspect-marked lazy evaluation, and reduction
constructs (`el resultado de sumar los X`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class StringLit:
    """A string literal, e.g. "Hola, mundo"."""

    value: str


@dataclass(frozen=True)
class IntLit:
    """An integer literal, e.g. 0, 1, 100."""

    value: int


@dataclass(frozen=True)
class FloatLit:
    """A decimal literal, e.g. 0.10, 3.14. Phase 4 addition.

    Kept distinct from `IntLit` so the existing integer-only arithmetic
    paths can fast-path scalar-int cases without an isinstance(float) check.
    """

    value: float


@dataclass(frozen=True)
class Identifier:
    """A bare identifier — the noun in a binding or referent name."""

    name: str


@dataclass(frozen=True)
class ListLit:
    """A homogeneous numeric collection literal: `[100, 200, 300, 400]`.

    Phase 4 restricts element types to `IntLit` and `FloatLit`. Mixing the
    two within one literal is allowed (Python coerces under arithmetic);
    strings, identifiers, and nested collections are deferred.
    """

    elements: tuple["Expr", ...]


@dataclass(frozen=True)
class BinaryOp:
    """Numeric arithmetic on two `Expr` operands.

    Phase 3b wired `+` (*más*) and `−` (*menos*); Phase 4 adds `×` (*por*).
    Either operand may be an `Identifier`, an `IntLit` / `FloatLit`, a
    `ListLit`, or another `BinaryOp`. Scalar–collection and collection–
    collection broadcasting is handled at evaluation time (see the
    interpreter); the AST itself is shape-agnostic.
    """

    op: str  # "más", "menos", "por"
    left: "Expr"
    right: "Expr"


Expr = Union[StringLit, IntLit, FloatLit, Identifier, ListLit, "BinaryOp"]


@dataclass(frozen=True)
class BindingSer:
    """Immutable scalar binding via *ser*: `El <name> es <value>.`"""

    name: str
    value: Expr


@dataclass(frozen=True)
class BindingSerPlural:
    """Immutable plural binding via *ser*: `Los <name> son <collection-expr>.`

    Phase 4 addition. The RHS must evaluate to a collection at runtime;
    the parser rejects `Los X son <scalar-literal>` outright per the
    Phase 4 simplification of paper §3.6. Plural identifiers and
    plural-yielding arithmetic (broadcast / element-wise) are allowed
    on the RHS.
    """

    name: str
    value: Expr


@dataclass(frozen=True)
class BindingEstar:
    """Mutable binding via *estar*: `El <name> está en <value>.`

    The name is bound to a cell currently holding `value`; subsequent
    `Hacé que el <name> esté en <new_value>` mutates the cell.
    """

    name: str
    value: Expr


@dataclass(frozen=True)
class MutationCommand:
    """Imperative mutation: `Hacé que el <name> esté en <value>.`

    Vos imperative of *hacer* + subjunctive complement (*esté*). Sets the
    mutable (*estar*) binding `name` to `value`. Mutating a *ser* binding
    is a runtime error.
    """

    name: str
    value: Expr


@dataclass(frozen=True)
class DecirCommand:
    """Imperative read-and-print of a scalar: `Decí <singular-article> <noun>.`

    Phase 2 form that names its argument as a full noun phrase, as opposed
    to the Phase 1 `Decilo` form which dereferences the most-recent binding
    via the enclitic `lo`.
    """

    name: str


@dataclass(frozen=True)
class DecirPluralCommand:
    """Imperative read-and-print of a collection: `Decí los <noun>.`

    Phase 4 addition. Distinct from `DecirCommand` so the existing
    singular path is byte-for-byte unchanged; the plural form prints
    the collection using a Python-list repr (documented choice; see
    `interpreter._format_collection`).
    """

    name: str


@dataclass(frozen=True)
class DecirExpr:
    """Imperative print of an arbitrary expression: `Decí <expr>.`

    Phase 3b addition, motivated by arithmetic in print position
    (`Decí el total más 3`). The wrapped `Expr` is evaluated and the
    result printed with a trailing newline, like `DecirCommand`.
    Distinct from `DecirCommand` (Identifier-only, no arithmetic) so
    existing Phase 1+2+3a paths stay byte-for-byte unchanged.
    """

    value: "Expr"


@dataclass(frozen=True)
class DecirLiteral:
    """Imperative print of a string literal: `Decí "<text>".`

    Phase 3a addition, motivated by §5 Example 2's `decí "listo"` clause.
    Distinct from `DecirCommand` (which names a binding) and
    `ImperativeCall` (which carries an enclitic).
    """

    value: StringLit


@dataclass(frozen=True)
class ImperativeCall:
    """A vos-imperative verb (optionally with a single enclitic clitic).

    Phase 1 form — kept for `Decilo` and other single-clitic enclitic
    imperatives. `verb_lemma` is the dictionary form (e.g. "decir");
    `clitic` is one of: lo, la, le, los, las, les, me, te, se, nos, os.
    """

    verb_lemma: str
    clitic: str | None


@dataclass(frozen=True)
class DeferredBinding:
    """Subjunctive deferred binding: `Cuando el <name> esté en <trigger>, <action>.`

    Registers a one-shot observer on the mutable cell `name`: when a
    subsequent mutation sets `name`'s value equal to `trigger_value`, the
    nested `action` (an imperative statement — `DecirCommand` or
    `ImperativeCall` in Phase 3a) fires exactly once and the observer is
    removed.

    The subjunctive *esté* is the grammatical carrier of the deferral
    (white-paper §3.2): the action is hypothetical until the trigger is
    realised, mirroring Spanish mood semantics.
    """

    name: str
    trigger_value: "Expr"
    action: "Statement"


@dataclass(frozen=True)
class EstaCondition:
    """Subjunctive equality test: `el <name> esté en <trigger_value>`.

    Phase 3b factoring of the condition-head shape that Phase 3a's
    `DeferredBinding` carried inline. Reused as the condition of a
    `mientras` loop. True iff `name`'s current value equals
    `trigger_value`.
    """

    name: str
    trigger_value: "Expr"


@dataclass(frozen=True)
class NegatedCondition:
    """Negated subjunctive equality: `el <name> no esté en <trigger_value>`.

    True iff `name`'s current value is NOT equal to `trigger_value`.
    Used as a `mientras` head — the canonical counter-loop reads
    `Mientras el contador no esté en 0, hacé …`. (Phase 3b does not
    fold negation into `Cuando`; observer-style negation is deferred.)
    """

    name: str
    trigger_value: "Expr"


Condition = Union[EstaCondition, NegatedCondition]


@dataclass(frozen=True)
class WhileLoop:
    """Bounded while-loop: `Mientras <condition>, hacé <imperative>`.

    Phase 3b iteration construct. The condition is re-evaluated before
    each iteration; the body is any Phase-1/2/3a imperative statement.
    The interpreter enforces a safety cap on iteration count
    (currently 100,000) to keep runaway loops from hanging the
    interpreter — Phase 3b is intentionally not aiming for unbounded
    coinduction.
    """

    condition: "Condition"
    body: "Statement"


Statement = Union[
    BindingSer,
    BindingSerPlural,
    BindingEstar,
    MutationCommand,
    DecirCommand,
    DecirPluralCommand,
    DecirExpr,
    DecirLiteral,
    ImperativeCall,
    DeferredBinding,
    WhileLoop,
]


@dataclass(frozen=True)
class Program:
    """An Inflexión program — an ordered list of statements."""

    statements: tuple[Statement, ...]
