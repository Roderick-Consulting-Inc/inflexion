# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión parser — Phase 1.

Recognises exactly two sentence shapes, separated by periods:

    1. Ser-binding:        <article> <noun> es <value>.
       e.g. `El saludo es "Hola, mundo".`

    2. Vos-imperative:     <vos-imperative-verb-with-optional-clitic>.
       e.g. `Decilo.`

Anything else raises SyntaxError. Phase 2+ will extend the grammar.

Clitic detection: spaCy's es_core_news_sm does not always split enclitic
pronouns off the verb, so we apply a manual suffix-strip pass over the known
single-clitic set (lo, la, le, los, las, les, me, te, se, nos, os) for tokens
the morphology tags as a verb form. Phase 1 only supports a single clitic.
"""
from __future__ import annotations

from .ast import BindingSer, Expr, Identifier, ImperativeCall, Program, Statement, StringLit
from .lexer import Token

# Singular definite + indefinite articles. Phase 1 only handles singular bindings.
_SINGULAR_ARTICLES = {"el", "la", "un", "una"}

# Spanish clitic pronouns. Order matters: longer suffixes first so we don't
# strip "le" off "les" or "la" off "las".
_CLITICS = ("nos", "los", "las", "les", "me", "te", "se", "os", "lo", "la", "le")

# Map common vos-imperative surface forms to their infinitive lemma. Phase 1
# only handles `decir`. spaCy's lemmatiser is unreliable on bare imperatives,
# so we maintain an explicit table. Phase 2+ will broaden coverage and rely on
# a richer morphological analyser.
#
# Note on the orthographic accent: in Rioplatense, the vos imperative of
# *decir* is written `decí` (accented í) when standalone, but when one
# enclitic is attached the stress falls on the same syllable by default and
# the accent is conventionally dropped in writing (`decilo`, not `decílo`).
# Phase 1 accepts both unaccented and accented bare-stem variants.
_VOS_IMPERATIVE_LEMMAS = {
    "decí": "decir",
    "deci": "decir",
}


def _strip_clitic(verb_form: str) -> tuple[str, str | None]:
    """Return (bare_verb, clitic_or_None) by stripping a known enclitic suffix."""
    low = verb_form.lower()
    for clitic in _CLITICS:
        if low.endswith(clitic) and len(low) > len(clitic):
            return low[: -len(clitic)], clitic
    return low, None


def _value_from_token(tok: Token, strings: list[str]) -> Expr:
    """Resolve a value-position token to a StringLit or an Identifier."""
    if tok.is_string_placeholder:
        return StringLit(strings[tok.placeholder_index])
    return Identifier(tok.lower)


def _split_sentences(tokens: list[Token]) -> list[list[Token]]:
    """Split the token stream into sentences terminated by `.`."""
    sentences: list[list[Token]] = []
    current: list[Token] = []
    for tok in tokens:
        if tok.text == ".":
            if current:
                sentences.append(current)
                current = []
            continue
        current.append(tok)
    if current:
        sentences.append(current)
    return sentences


def _parse_ser_binding(sentence: list[Token], strings: list[str]) -> BindingSer:
    """Parse `<article> <noun> es <value>` into a BindingSer."""
    # Layout: [article, noun, "es", value]. We tolerate spaCy POS noise by
    # working off surface forms for the structural tokens.
    if len(sentence) < 4:
        raise SyntaxError(f"Incomplete ser-binding: {[t.text for t in sentence]}")
    article, noun, copula, value, *rest = sentence
    if article.lower not in _SINGULAR_ARTICLES:
        raise SyntaxError(f"Expected singular article, got {article.text!r}")
    if copula.lower != "es":
        raise SyntaxError(f"Expected `es` (ser copula), got {copula.text!r}")
    if rest:
        raise SyntaxError(
            f"Phase 1 only supports `<article> <noun> es <single-value>`; "
            f"got trailing tokens {[t.text for t in rest]}"
        )
    return BindingSer(name=noun.lower, value=_value_from_token(value, strings))


def _parse_imperative(sentence: list[Token]) -> ImperativeCall:
    """Parse a single-token vos-imperative-with-optional-clitic."""
    if len(sentence) != 1:
        raise SyntaxError(
            f"Phase 1 imperatives must be a single token; got "
            f"{[t.text for t in sentence]}"
        )
    (tok,) = sentence
    surface = tok.lower
    # First try: surface is a known vos-imperative with no clitic.
    if surface in _VOS_IMPERATIVE_LEMMAS:
        return ImperativeCall(verb_lemma=_VOS_IMPERATIVE_LEMMAS[surface], clitic=None)
    # Second: peel a clitic and re-check.
    bare, clitic = _strip_clitic(surface)
    if bare in _VOS_IMPERATIVE_LEMMAS:
        return ImperativeCall(verb_lemma=_VOS_IMPERATIVE_LEMMAS[bare], clitic=clitic)
    raise SyntaxError(
        f"Unrecognised imperative form {tok.text!r}. Phase 1 only supports "
        f"vos-imperatives of: {sorted(_VOS_IMPERATIVE_LEMMAS)}"
    )


def parse(tokens: list[Token], strings: list[str]) -> Program:
    """Parse a token stream + string table into a Program."""
    statements: list[Statement] = []
    for sentence in _split_sentences(tokens):
        first = sentence[0]
        if first.lower in _SINGULAR_ARTICLES:
            statements.append(_parse_ser_binding(sentence, strings))
        else:
            statements.append(_parse_imperative(sentence))
    return Program(statements=tuple(statements))
