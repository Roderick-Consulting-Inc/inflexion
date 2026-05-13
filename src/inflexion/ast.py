# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión AST — Phase 3a node types.

Phase 2 added:
    - BindingEstar: mutable binding via *estar* (El X está en Y)
    - MutationCommand: imperative mutation (Hacé que el X esté en Y)
    - IntLit: integer numeric literal
    - DecirCommand: vos-imperative `Decí <noun-phrase>` reading by name
      (the Phase 1 `Decilo` enclitic form remains an ImperativeCall)

Phase 3a adds:
    - DeferredBinding: subjunctive deferred observer
      (`Cuando el X esté en Y, <imperative>`)

Phase 3b+ will add MientrasLoop, arithmetic, FunctionDef, ListLit, etc.
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
class Identifier:
    """A bare identifier — the noun in a binding or referent name."""

    name: str


Expr = Union[StringLit, IntLit, Identifier]


@dataclass(frozen=True)
class BindingSer:
    """Immutable binding via *ser*: `El <name> es <value>.`"""

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
    """Imperative read-and-print: `Decí <article> <noun>.`

    Phase 2 form that names its argument as a full noun phrase, as opposed
    to the Phase 1 `Decilo` form which dereferences the most-recent binding
    via the enclitic `lo`.
    """

    name: str


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


Statement = Union[
    BindingSer,
    BindingEstar,
    MutationCommand,
    DecirCommand,
    DecirLiteral,
    ImperativeCall,
    DeferredBinding,
]


@dataclass(frozen=True)
class Program:
    """An Inflexión program — an ordered list of statements."""

    statements: tuple[Statement, ...]
