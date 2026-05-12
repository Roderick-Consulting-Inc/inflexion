# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión AST — Phase 1 node types.

Phase 1 covers only:
    - Program: top-level container
    - BindingSer: immutable binding via *ser* (El X es Y)
    - ImperativeCall: vos-imperative verb form with up to one enclitic clitic
    - StringLit / Identifier: the two Phase 1 expression forms

Phase 2+ will add BindingEstar, SubjunctiveDeferred, FunctionDef, ListLit,
NumericLit with diminutive/augmentative scaling, etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class StringLit:
    """A string literal, e.g. "Hola, mundo"."""

    value: str


@dataclass(frozen=True)
class Identifier:
    """A bare identifier — the noun in a binding or referent name."""

    name: str


Expr = Union[StringLit, Identifier]


@dataclass(frozen=True)
class BindingSer:
    """Immutable binding via *ser*: `El <name> es <value>.`"""

    name: str
    value: Expr


@dataclass(frozen=True)
class ImperativeCall:
    """A vos-imperative verb (optionally with a single enclitic clitic).

    Phase 1 only handles single-clitic imperatives like `Decilo` (decir + lo).
    `verb_lemma` is the dictionary form of the verb (e.g. "decir").
    `clitic` is one of: lo, la, le, los, las, les, me, te, se, nos, os.
    """

    verb_lemma: str
    clitic: str | None


Statement = Union[BindingSer, ImperativeCall]


@dataclass(frozen=True)
class Program:
    """An Inflexión program — an ordered list of statements."""

    statements: tuple[Statement, ...]
