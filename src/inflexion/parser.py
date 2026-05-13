# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión parser — Phase 3a.

Recognises these sentence shapes (each terminated by `.`):

    1. Ser-binding (immutable):  `El <noun> es <value>.`
    2. Estar-binding (mutable):  `El <noun> está en <value>.`
    3. Mutation:                 `Hacé que el <noun> esté en <value>.`
    4. Decí read-and-print:      `Decí el <noun>.`
    5. Vos-imperative w/ clitic: `Decilo.`  (Phase 1 single-clitic form)
    6. Subjunctive deferred:     `Cuando el <noun> esté en <value>, <imperative>.`
                                  (Phase 3a — registers a one-shot observer)

Value positions accept string-literal placeholders, integer literals, or
identifiers. Anything else raises SyntaxError.

Clitic detection: spaCy's es_core_news_sm does not always split enclitic
pronouns off the verb, so we apply a manual suffix-strip pass over the known
single-clitic set for tokens that look like verb forms. Phase 3a still supports
only a single enclitic on the Phase 1 imperative path.
"""
from __future__ import annotations

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
from .lexer import Token

# Singular definite + indefinite articles. Phase 2 still only handles singular.
_SINGULAR_ARTICLES = {"el", "la", "un", "una"}

# Spanish clitic pronouns. Order matters: longer suffixes first so we don't
# strip "le" off "les" or "la" off "las".
_CLITICS = ("nos", "los", "las", "les", "me", "te", "se", "os", "lo", "la", "le")

# Surface-form lookup for vos imperatives whose lemma spaCy mistags. Phase 2
# wires `decir` (which Phase 1 already used) and `hacer`. The `hacé` form is
# tagged with a bogus lemma `hazar` by es_core_news_sm, so we override.
#
# Note on the orthographic accent: in Rioplatense, the vos imperative is
# written with a closing accent (`decí`, `hacé`) when standalone, but the
# accent is conventionally dropped in writing when one enclitic is attached
# (`decilo`, not `decílo`). We accept both unaccented and accented bare-stem
# variants here.
_VOS_IMPERATIVE_LEMMAS = {
    "decí": "decir",
    "deci": "decir",
    "hacé": "hacer",
    "hace": "hacer",
}


def _strip_clitic(verb_form: str) -> tuple[str, str | None]:
    """Return (bare_verb, clitic_or_None) by stripping a known enclitic suffix."""
    low = verb_form.lower()
    for clitic in _CLITICS:
        if low.endswith(clitic) and len(low) > len(clitic):
            return low[: -len(clitic)], clitic
    return low, None


def _value_from_token(tok: Token, strings: list[str]) -> Expr:
    """Resolve a value-position token to a StringLit, IntLit, or Identifier."""
    if tok.is_string_placeholder:
        return StringLit(strings[tok.placeholder_index])
    # Integer literal: spaCy tags as NUM with NumForm=Digit. Fall back to a
    # str-isdigit check for robustness against tagger variation.
    if tok.pos == "NUM" or tok.text.lstrip("-").isdigit():
        try:
            return IntLit(int(tok.text))
        except ValueError as exc:  # pragma: no cover - defensive
            raise SyntaxError(f"Bad numeric literal {tok.text!r}") from exc
    return Identifier(tok.lower)


def _is_estar_indicative(tok: Token) -> bool:
    """True if `tok` is an indicative form of *estar* (e.g. `está`, `están`)."""
    return tok.lemma == "estar" and "Mood=Ind" in tok.morph


def _is_estar_subjunctive(tok: Token) -> bool:
    """True if `tok` is a subjunctive form of *estar* (e.g. `esté`, `estén`)."""
    return tok.lemma == "estar" and "Mood=Sub" in tok.morph


def _is_hace_imperative(tok: Token) -> bool:
    """True if `tok` is the vos imperative of *hacer* (`hacé`/`hace`)."""
    return tok.lower in {"hacé", "hace"}


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


def _parse_binding_or_decir(sentence: list[Token], strings: list[str]) -> Statement:
    """Parse a sentence starting with an article.

    Recognised shapes:
        - `<article> <noun> es <value>`             -> BindingSer
        - `<article> <noun> está en <value>`        -> BindingEstar
    """
    if len(sentence) < 4:
        raise SyntaxError(
            f"Incomplete binding: {[t.text for t in sentence]}"
        )
    article, noun, copula, *rest = sentence
    if article.lower not in _SINGULAR_ARTICLES:
        raise SyntaxError(f"Expected singular article, got {article.text!r}")

    # Ser binding: `El X es Y.`
    if copula.lower == "es":
        if len(rest) != 1:
            raise SyntaxError(
                f"Phase 2 ser-binding expects `<article> <noun> es <single-value>`; "
                f"got trailing tokens {[t.text for t in rest]}"
            )
        return BindingSer(name=noun.lower, value=_value_from_token(rest[0], strings))

    # Estar binding: `El X está en Y.`
    if _is_estar_indicative(copula):
        if len(rest) != 2 or rest[0].lower != "en":
            raise SyntaxError(
                f"Phase 2 estar-binding expects `<article> <noun> está en <value>`; "
                f"got {[t.text for t in [copula, *rest]]}"
            )
        return BindingEstar(name=noun.lower, value=_value_from_token(rest[1], strings))

    raise SyntaxError(
        f"Expected `es` or `está` after `{article.text} {noun.text}`, got {copula.text!r}"
    )


def _parse_mutation(sentence: list[Token], strings: list[str]) -> MutationCommand:
    """Parse `Hacé que el <noun> esté en <value>` into a MutationCommand."""
    # Layout: [hacé, que, article, noun, esté, en, value]
    if len(sentence) != 7:
        raise SyntaxError(
            f"Phase 2 mutation expects 7 tokens "
            f"(`Hacé que el <noun> esté en <value>`); got "
            f"{[t.text for t in sentence]}"
        )
    hace, que, article, noun, este, en, value = sentence
    if not _is_hace_imperative(hace):
        raise SyntaxError(f"Expected `Hacé`, got {hace.text!r}")
    if que.lower != "que":
        raise SyntaxError(f"Expected `que` after `Hacé`, got {que.text!r}")
    if article.lower not in _SINGULAR_ARTICLES:
        raise SyntaxError(
            f"Expected singular article in mutation, got {article.text!r}"
        )
    if not _is_estar_subjunctive(este):
        raise SyntaxError(
            f"Expected subjunctive `esté` in mutation, got {este.text!r}"
        )
    if en.lower != "en":
        raise SyntaxError(f"Expected `en` before the new value, got {en.text!r}")
    return MutationCommand(name=noun.lower, value=_value_from_token(value, strings))


def _parse_imperative_tokens(
    tokens: list[Token], strings: list[str]
) -> Statement:
    """Parse a contiguous run of tokens forming a single imperative clause.

    Recognised shapes (used both at top level and as the action of a
    `Cuando ..., <imperative>` deferred binding):
        - `Decí <article> <noun>`     -> DecirCommand   (binding name)
        - `Decí <string-literal>`     -> DecirLiteral   (direct print)
        - `Decilo` / `Decila` / …     -> ImperativeCall (enclitic form)
    """
    if not tokens:
        raise SyntaxError("Empty imperative clause.")
    first = tokens[0]
    surface = first.lower

    # `Decí` followed by an object — full-NP form or string-literal form.
    if surface in _VOS_IMPERATIVE_LEMMAS and _VOS_IMPERATIVE_LEMMAS[surface] == "decir":
        if len(tokens) == 1:
            raise InflexionParseError(
                "`Decí` without an object is not supported; either name a "
                "binding (`Decí el saludo`), pass a string literal "
                "(`Decí \"hola\"`), or use the enclitic form `Decilo`."
            )
        # `Decí "<text>"` — direct string-literal print.
        if len(tokens) == 2 and tokens[1].is_string_placeholder:
            return DecirLiteral(value=StringLit(strings[tokens[1].placeholder_index]))
        # `Decí <article> <noun>` — read-and-print a binding.
        if len(tokens) == 3:
            article, noun = tokens[1], tokens[2]
            if article.lower not in _SINGULAR_ARTICLES:
                raise SyntaxError(
                    f"Expected singular article or string literal after "
                    f"`Decí`, got {article.text!r}"
                )
            return DecirCommand(name=noun.lower)
        raise SyntaxError(
            f"`Decí` expects `Decí <article> <noun>` or `Decí \"<text>\"`; got "
            f"{[t.text for t in tokens]}"
        )

    # Phase 1 enclitic form: `Decilo`, etc. — must be a single token.
    if len(tokens) != 1:
        raise SyntaxError(
            f"Imperative clause must be `Decí <article> <noun>`, "
            f"`Decí \"<text>\"`, or a single enclitic form like `Decilo`; "
            f"got {[t.text for t in tokens]}"
        )
    bare, clitic = _strip_clitic(surface)
    if bare in _VOS_IMPERATIVE_LEMMAS:
        return ImperativeCall(
            verb_lemma=_VOS_IMPERATIVE_LEMMAS[bare], clitic=clitic
        )
    raise SyntaxError(
        f"Unrecognised imperative form {first.text!r}. Phase 3a supports "
        f"vos-imperatives of: {sorted(set(_VOS_IMPERATIVE_LEMMAS.values()))}"
    )


def _parse_decir(sentence: list[Token], strings: list[str]) -> Statement:
    """Parse a top-level imperative sentence."""
    return _parse_imperative_tokens(sentence, strings)


def _parse_cuando(sentence: list[Token], strings: list[str]) -> DeferredBinding:
    """Parse `Cuando el <noun> esté en <value>, <imperative>` into a DeferredBinding.

    Layout (head before comma): [cuando, article, noun, esté, en, value, ',', ...tail]
    """
    # Locate the comma — required separator between condition and action.
    comma_idx: int | None = None
    for i, tok in enumerate(sentence):
        if tok.text == ",":
            comma_idx = i
            break
    if comma_idx is None:
        raise SyntaxError(
            "`Cuando` clause requires a comma before the imperative action; "
            f"got {[t.text for t in sentence]}"
        )
    head = sentence[:comma_idx]
    tail = sentence[comma_idx + 1 :]
    if len(head) != 6:
        raise SyntaxError(
            "Phase 3a `Cuando` head expects `Cuando <article> <noun> esté en "
            f"<value>`; got {[t.text for t in head]}"
        )
    cuando, article, noun, este, en, value = head
    if cuando.lower != "cuando":
        raise SyntaxError(f"Expected `Cuando`, got {cuando.text!r}")
    if article.lower not in _SINGULAR_ARTICLES:
        raise SyntaxError(
            f"Expected singular article in `Cuando` clause, got {article.text!r}"
        )
    if not _is_estar_subjunctive(este):
        raise SyntaxError(
            f"Expected subjunctive `esté` in `Cuando` clause, got {este.text!r}"
        )
    if en.lower != "en":
        raise SyntaxError(
            f"Expected `en` before the trigger value, got {en.text!r}"
        )
    if not tail:
        raise SyntaxError("`Cuando` clause is missing its imperative action.")
    action = _parse_imperative_tokens(tail, strings)
    return DeferredBinding(
        name=noun.lower,
        trigger_value=_value_from_token(value, strings),
        action=action,
    )


class InflexionParseError(SyntaxError):
    """Phase 2 parse error. Subclass of SyntaxError for backwards compatibility."""


def parse(tokens: list[Token], strings: list[str]) -> Program:
    """Parse a token stream + string table into a Program."""
    statements: list[Statement] = []
    for sentence in _split_sentences(tokens):
        first = sentence[0]
        if first.lower == "cuando":
            statements.append(_parse_cuando(sentence, strings))
        elif first.lower in _SINGULAR_ARTICLES:
            statements.append(_parse_binding_or_decir(sentence, strings))
        elif _is_hace_imperative(first):
            statements.append(_parse_mutation(sentence, strings))
        else:
            statements.append(_parse_decir(sentence, strings))
    return Program(statements=tuple(statements))
