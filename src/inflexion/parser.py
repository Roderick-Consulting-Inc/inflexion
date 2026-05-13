# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión parser — Phase 3b.

Recognises these sentence shapes (each terminated by `.`):

    1. Ser-binding (immutable):  `El <noun> es <value>.`
    2. Estar-binding (mutable):  `El <noun> está en <value>.`
    3. Mutation:                 `Hacé que el <noun> esté en <value>.`
    4. Decí read-and-print:      `Decí <value>.`
    5. Vos-imperative w/ clitic: `Decilo.`  (Phase 1 single-clitic form)
    6. Subjunctive deferred:     `Cuando el <noun> esté en <value>, <imperative>.`
                                  (Phase 3a — registers a one-shot observer)
    7. While-loop (Phase 3b):    `Mientras el <noun> [no] esté en <value>,
                                  <imperative>.`

Value positions accept string-literal placeholders, integer literals,
identifiers, or a Phase-3b two-operand arithmetic form: `el <name> más
<value>` / `el <name> menos <value>` (and equally `<literal> más
<value>`). Arithmetic operands are themselves restricted to identifiers
or integer literals; nested arithmetic is deferred to a later phase.

Clitic detection: spaCy's es_core_news_sm does not always split enclitic
pronouns off the verb, so we apply a manual suffix-strip pass over the known
single-clitic set for tokens that look like verb forms. Phase 3b still supports
only a single enclitic on the Phase 1 imperative path.
"""
from __future__ import annotations

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
from .lexer import Token

# Arithmetic operators recognised in Phase 3b. Both are surface-form lookups.
_ARITHMETIC_OPS = {"más", "menos"}

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


def _atom_from_token(tok: Token, strings: list[str]) -> Expr:
    """Resolve a single value-position token to a StringLit, IntLit, or Identifier.

    Pre-Phase-3b helper. Multi-token value forms (arithmetic, articled
    bindings) are handled by `_parse_value` instead.
    """
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


# Backwards-compat alias for any future caller that still uses the old name.
_value_from_token = _atom_from_token


def _parse_arith_atom(tokens: list[Token], strings: list[str]) -> tuple[Expr, int]:
    """Parse a single arithmetic operand starting at `tokens[0]`.

    Operand shapes in Phase 3b are:
        - `el <name>` / `la <name>` / ...   -> Identifier  (2 tokens)
        - `<literal>`                       -> StringLit / IntLit (1 token)
        - `<identifier>`                    -> Identifier (1 token)

    Returns the parsed Expr plus the number of tokens consumed.
    """
    if not tokens:
        raise SyntaxError("Expected value, got end of clause.")
    first = tokens[0]
    if first.lower in _SINGULAR_ARTICLES:
        if len(tokens) < 2:
            raise SyntaxError(
                f"Article {first.text!r} not followed by a noun in value position."
            )
        return Identifier(tokens[1].lower), 2
    return _atom_from_token(first, strings), 1


def _parse_value(tokens: list[Token], strings: list[str]) -> Expr:
    """Parse the value/expression occupying a contiguous token slice.

    Handles a single-token literal/identifier, an articled binding name
    (`el <noun>`), or a Phase-3b two-operand arithmetic form
    (`<operand> más <operand>`, `<operand> menos <operand>`). Trailing
    or unconsumed tokens raise SyntaxError so callers don't silently
    drop user-written content.
    """
    if not tokens:
        raise SyntaxError("Expected value, got empty token slice.")
    left, consumed = _parse_arith_atom(tokens, strings)
    if consumed == len(tokens):
        return left
    # Arithmetic: expect `<op> <atom>` after the first operand.
    op_tok = tokens[consumed]
    if op_tok.lower not in _ARITHMETIC_OPS:
        raise SyntaxError(
            f"Unexpected token {op_tok.text!r} in value position "
            f"(expected `más`/`menos` or end of clause)."
        )
    right, right_consumed = _parse_arith_atom(tokens[consumed + 1 :], strings)
    if consumed + 1 + right_consumed != len(tokens):
        tail = tokens[consumed + 1 + right_consumed :]
        raise SyntaxError(
            f"Trailing tokens after arithmetic expression: "
            f"{[t.text for t in tail]} (Phase 3b allows only one operator)."
        )
    return BinaryOp(op=op_tok.lower, left=left, right=right)


def _is_estar_indicative(tok: Token) -> bool:
    """True if `tok` is an indicative form of *estar* (e.g. `está`, `están`)."""
    return tok.lemma == "estar" and "Mood=Ind" in tok.morph


def _is_estar_subjunctive(tok: Token) -> bool:
    """True if `tok` is a subjunctive form of *estar* (e.g. `esté`, `estén`)."""
    return tok.lemma == "estar" and "Mood=Sub" in tok.morph


def _is_hace_imperative(tok: Token) -> bool:
    """True if `tok` is the vos imperative of *hacer* (`hacé`/`hace`)."""
    return tok.lower in {"hacé", "hace"}


def _is_arithmetic_op(tok: Token) -> bool:
    """True if `tok` is a Phase-3b arithmetic operator (`más`/`menos`)."""
    return tok.lower in _ARITHMETIC_OPS


def _parse_condition(tokens: list[Token], strings: list[str]) -> Condition:
    """Parse a subjunctive condition head: `el <noun> [no] esté en <value>`.

    Shared by `Cuando` (Phase 3a) and `Mientras` (Phase 3b). Phase 3b
    extends the shape with an optional `no` between the noun and the
    subjunctive copula, producing a `NegatedCondition` when present.
    """
    if len(tokens) < 5:
        raise SyntaxError(
            f"Condition head expects `<article> <noun> [no] esté en <value>`; "
            f"got {[t.text for t in tokens]}"
        )
    article = tokens[0]
    noun = tokens[1]
    rest = tokens[2:]
    if article.lower not in _SINGULAR_ARTICLES:
        raise SyntaxError(
            f"Expected singular article in condition, got {article.text!r}"
        )
    negated = False
    if rest and rest[0].lower == "no":
        negated = True
        rest = rest[1:]
    if not rest:
        raise SyntaxError(
            f"Condition missing subjunctive copula `esté`: "
            f"{[t.text for t in tokens]}"
        )
    este = rest[0]
    if not _is_estar_subjunctive(este):
        raise SyntaxError(
            f"Expected subjunctive `esté` in condition, got {este.text!r}"
        )
    if len(rest) < 3 or rest[1].lower != "en":
        raise SyntaxError(
            f"Expected `en <value>` after subjunctive `esté` in condition; "
            f"got {[t.text for t in rest]}"
        )
    value = _parse_value(rest[2:], strings)
    if negated:
        return NegatedCondition(name=noun.lower, trigger_value=value)
    return EstaCondition(name=noun.lower, trigger_value=value)


def _parse_mientras(sentence: list[Token], strings: list[str]) -> WhileLoop:
    """Parse `Mientras el <noun> [no] esté en <value>, <imperative>`.

    Layout: [mientras, ...condition-tokens, ',', ...body-tokens]. The
    body is any Phase-1/2/3a imperative parsed via
    `_parse_imperative_tokens`. The condition is re-evaluated each
    iteration by the interpreter, bounded by a safety cap.
    """
    # Locate the comma separating condition and body.
    comma_idx: int | None = None
    for i, tok in enumerate(sentence):
        if tok.text == ",":
            comma_idx = i
            break
    if comma_idx is None:
        raise SyntaxError(
            "`Mientras` clause requires a comma before the imperative body; "
            f"got {[t.text for t in sentence]}"
        )
    head = sentence[1:comma_idx]  # drop the leading `Mientras`
    tail = sentence[comma_idx + 1 :]
    if sentence[0].lower != "mientras":
        raise SyntaxError(  # pragma: no cover - caller filters
            f"Expected `Mientras`, got {sentence[0].text!r}"
        )
    condition = _parse_condition(head, strings)
    if not tail:
        raise SyntaxError("`Mientras` clause is missing its imperative body.")
    # The body must be a `Hacé que …` mutation, or any other Phase-1+
    # imperative. `Mientras X, hacé que Y esté en Z` is the canonical
    # counter-loop shape; we dispatch to the mutation parser when the
    # body opens with a hacé imperative, otherwise we fall through to
    # the general imperative path so `Decí …` bodies still work.
    if _is_hace_imperative(tail[0]):
        body: Statement = _parse_mutation(tail, strings)
    else:
        body = _parse_imperative_tokens(tail, strings)
    return WhileLoop(condition=condition, body=body)


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

    # Ser binding: `El X es Y.` — value slice may be a single token or, in
    # Phase 3b, an arithmetic expression like `el total más 3`.
    if copula.lower == "es":
        if not rest:
            raise SyntaxError(
                f"Ser-binding `{article.text} {noun.text} es …` missing value."
            )
        return BindingSer(name=noun.lower, value=_parse_value(rest, strings))

    # Estar binding: `El X está en Y.`
    if _is_estar_indicative(copula):
        if len(rest) < 2 or rest[0].lower != "en":
            raise SyntaxError(
                f"Phase 2 estar-binding expects `<article> <noun> está en <value>`; "
                f"got {[t.text for t in [copula, *rest]]}"
            )
        return BindingEstar(name=noun.lower, value=_parse_value(rest[1:], strings))

    raise SyntaxError(
        f"Expected `es` or `está` after `{article.text} {noun.text}`, got {copula.text!r}"
    )


def _parse_mutation(sentence: list[Token], strings: list[str]) -> MutationCommand:
    """Parse `Hacé que el <noun> esté en <value>` into a MutationCommand.

    Phase 3b: `<value>` may be an arithmetic expression, so the value
    slice can be longer than one token.
    """
    # Layout: [hacé, que, article, noun, esté, en, value...]
    if len(sentence) < 7:
        raise SyntaxError(
            f"Phase 2 mutation expects at least 7 tokens "
            f"(`Hacé que el <noun> esté en <value>`); got "
            f"{[t.text for t in sentence]}"
        )
    hace, que, article, noun, este, en, *value_tokens = sentence
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
    return MutationCommand(name=noun.lower, value=_parse_value(value_tokens, strings))


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

    # `Decí` followed by an object — full-NP form, string-literal form,
    # or (Phase 3b) an arithmetic expression like `Decí el total más 3`.
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
        # `Decí <article> <noun>` — read-and-print a binding (kept as a
        # distinct AST node so the interpreter's name-lookup path is
        # unchanged for the common case).
        if (
            len(tokens) == 3
            and tokens[1].lower in _SINGULAR_ARTICLES
            and not _is_arithmetic_op(tokens[2])
        ):
            return DecirCommand(name=tokens[2].lower)
        # Phase 3b: `Decí <value-expression>` — e.g. `Decí el total más 3`.
        # Reuse `_parse_value` so the same arithmetic surface works here as
        # in any other value position, and wrap the result so the
        # interpreter evaluates and prints it.
        value = _parse_value(tokens[1:], strings)
        return DecirExpr(value=value)

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

    Layout (head before comma): [cuando, article, noun, esté, en, value..., ',', ...tail].
    Phase 3b re-uses the shared `_parse_condition` helper so the value
    slot accepts the same arithmetic forms that other value positions
    do; the underlying observer registry is unchanged.
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
    head = sentence[1:comma_idx]  # drop the leading `Cuando`
    tail = sentence[comma_idx + 1 :]
    if sentence[0].lower != "cuando":
        raise SyntaxError(  # pragma: no cover - caller filters
            f"Expected `Cuando`, got {sentence[0].text!r}"
        )
    condition = _parse_condition(head, strings)
    if isinstance(condition, NegatedCondition):
        # Phase 3b deliberately restricts `Cuando` to positive equality.
        # A negated-observer (`Cuando … no esté en …`) has no clean
        # one-shot semantics; defer to a later phase.
        raise SyntaxError(
            "Phase 3b does not support `Cuando … no esté en …`; use "
            "`Mientras` for negated conditions."
        )
    if not tail:
        raise SyntaxError("`Cuando` clause is missing its imperative action.")
    action = _parse_imperative_tokens(tail, strings)
    return DeferredBinding(
        name=condition.name,
        trigger_value=condition.trigger_value,
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
        elif first.lower == "mientras":
            statements.append(_parse_mientras(sentence, strings))
        elif first.lower in _SINGULAR_ARTICLES:
            statements.append(_parse_binding_or_decir(sentence, strings))
        elif _is_hace_imperative(first):
            statements.append(_parse_mutation(sentence, strings))
        else:
            statements.append(_parse_decir(sentence, strings))
    return Program(statements=tuple(statements))
