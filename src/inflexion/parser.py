# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión parser — Phase 4.

Recognises these sentence shapes (each terminated by `.`):

    1. Ser-binding (immutable, singular): `El <noun> es <value>.`
    2. Ser-binding (immutable, plural):   `Los <noun> son <collection-expr>.`
                                          (Phase 4 — RHS must be a
                                           list literal or another
                                           collection-typed expression;
                                           `Los X son 5` is a parse error)
    3. Estar-binding (mutable):           `El <noun> está en <value>.`
    4. Mutation:                          `Hacé que el <noun> esté en <value>.`
    5. Decí read-and-print (scalar):      `Decí el <noun>.` / `Decí <expr>.`
    6. Decí read-and-print (plural):      `Decí los <noun>.`  (Phase 4)
    7. Vos-imperative w/ clitic:          `Decilo.`
    8. Subjunctive deferred:              `Cuando el <noun> esté en <value>, <imp>.`
    9. While-loop:                        `Mientras el <noun> [no] esté en <value>,
                                           <imperative>.`

Value positions accept string-literal placeholders, integer literals,
decimal literals (Phase 4), identifiers, list literals (Phase 4), an
articled binding name (`el <noun>` or `los <noun>`), or a two-operand
arithmetic form using `más` / `menos` / `por` (`por` is Phase 4).

Number agreement (paper §3.6, Phase 4):
    - A plural article (`los` / `las`) must combine with a plural noun
      and a plural verb form (`son`); singular article + plural noun
      (`el precios`) is a parse error.
    - The RHS of a plural ser binding must be a collection-producing
      expression. Phase 4 deliberately rejects the implicit scalar
      broadcast `Los X son 5` documented in paper §3.6: that rule
      requires a length to be established by context (function-call
      arity), which Phase 4 does not yet provide. Phase 5+ will lift
      this restriction.
"""
from __future__ import annotations

from .ast import (
    BinaryOp,
    BindingEstar,
    BindingSer,
    BindingSerPlural,
    Condition,
    DecirCommand,
    DecirExpr,
    DecirLiteral,
    DecirPluralCommand,
    DeferredBinding,
    EstaCondition,
    Expr,
    FloatLit,
    Identifier,
    ImperativeCall,
    IntLit,
    ListLit,
    MutationCommand,
    NegatedCondition,
    Program,
    Statement,
    StringLit,
    WhileLoop,
)
from .lexer import Token

# Arithmetic operators recognised in Phase 4. Surface-form lookups.
# `más` and `menos` were Phase 3b; `por` (multiplication) is Phase 4.
_ARITHMETIC_OPS = {"más", "menos", "por"}

# Singular definite + indefinite articles. The singular set is closed.
_SINGULAR_ARTICLES = {"el", "la", "un", "una"}

# Plural definite articles. Phase 4 adds the plural set. Indefinite
# plurals (`unos`, `unas`) are not yet used in any documented example
# but are accepted so future phases can adopt them without re-touching
# this table.
_PLURAL_ARTICLES = {"los", "las", "unos", "unas"}

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


class InflexionParseError(SyntaxError):
    """Phase 2+ parse error. Subclass of SyntaxError for backwards compatibility."""


def _strip_clitic(verb_form: str) -> tuple[str, str | None]:
    """Return (bare_verb, clitic_or_None) by stripping a known enclitic suffix."""
    low = verb_form.lower()
    for clitic in _CLITICS:
        if low.endswith(clitic) and len(low) > len(clitic):
            return low[: -len(clitic)], clitic
    return low, None


def _is_plural_noun(tok: Token) -> bool:
    """True if spaCy marks `tok` with Number=Plur (Phase 4 number-agreement check)."""
    return "Number=Plur" in tok.morph


def _atom_from_token(tok: Token, strings: list[str]) -> Expr:
    """Resolve a single value-position token to a literal or Identifier.

    Pre-Phase-3b helper; extended in Phase 4 to recognise decimal
    literals (`FloatLit`) alongside integers and strings. Multi-token
    value forms (arithmetic, articled bindings, list literals) are
    handled by `_parse_value` instead.
    """
    if tok.is_string_placeholder:
        return StringLit(strings[tok.placeholder_index])
    # Numeric literal — Phase 4 splits int / decimal so the AST carries
    # the distinction even though Python coerces them under arithmetic.
    if tok.is_numeric:
        if tok.is_integer_literal:
            return IntLit(int(tok.text))
        return FloatLit(float(tok.text))
    # Fallback: spaCy NUM tag for forms we didn't catch above.
    if tok.pos == "NUM":
        try:
            if "." in tok.text:
                return FloatLit(float(tok.text))
            return IntLit(int(tok.text))
        except ValueError as exc:  # pragma: no cover - defensive
            raise SyntaxError(f"Bad numeric literal {tok.text!r}") from exc
    return Identifier(tok.lower)


# Backwards-compat alias for any future caller that still uses the old name.
_value_from_token = _atom_from_token


def _parse_list_literal(
    tokens: list[Token], strings: list[str]
) -> tuple[ListLit, int]:
    """Parse a `[<num>, <num>, ...]` list literal starting at `tokens[0]`.

    Returns the parsed `ListLit` plus the count of tokens consumed
    (including the closing `]`). Phase 4 restricts element types to
    numeric literals (`IntLit` / `FloatLit`); identifiers, strings, and
    nested collections are deferred.
    """
    if not tokens or tokens[0].text != "[":
        raise InflexionParseError(  # pragma: no cover - caller filters
            f"Expected `[` to open a list literal; got "
            f"{tokens[0].text if tokens else '<eof>'!r}"
        )
    elements: list[Expr] = []
    i = 1
    # Empty list `[]` is allowed; arithmetic on it raises at runtime.
    if i < len(tokens) and tokens[i].text == "]":
        return ListLit(elements=()), 2
    while i < len(tokens):
        elt_tok = tokens[i]
        if not elt_tok.is_numeric:
            raise InflexionParseError(
                f"Phase 4 list literal accepts only numeric elements; "
                f"got {elt_tok.text!r}"
            )
        elements.append(_atom_from_token(elt_tok, strings))
        i += 1
        if i >= len(tokens):
            break
        sep = tokens[i]
        if sep.text == "]":
            return ListLit(elements=tuple(elements)), i + 1
        if sep.text != ",":
            raise InflexionParseError(
                f"Expected `,` or `]` in list literal; got {sep.text!r}"
            )
        i += 1
    raise InflexionParseError(
        f"Unclosed list literal: {[t.text for t in tokens]}"
    )


def _parse_arith_atom(tokens: list[Token], strings: list[str]) -> tuple[Expr, int]:
    """Parse a single arithmetic operand starting at `tokens[0]`.

    Operand shapes in Phase 4 are:
        - `[<num>, <num>, ...]`             -> ListLit         (variable token count)
        - `el <name>` / `la <name>`         -> Identifier      (2 tokens)
        - `los <name>` / `las <name>`       -> Identifier      (2 tokens, plural)
        - `<literal>`                       -> StringLit / IntLit / FloatLit (1 token)
        - `<identifier>`                    -> Identifier      (1 token)

    Returns the parsed Expr plus the number of tokens consumed. The
    plural-article variant is accepted in any value position; the
    number-agreement check on the *binding side* is enforced by the
    binding parser, not here.
    """
    if not tokens:
        raise SyntaxError("Expected value, got end of clause.")
    first = tokens[0]
    if first.text == "[":
        return _parse_list_literal(tokens, strings)
    if first.lower in _SINGULAR_ARTICLES or first.lower in _PLURAL_ARTICLES:
        if len(tokens) < 2:
            raise SyntaxError(
                f"Article {first.text!r} not followed by a noun in value position."
            )
        return Identifier(tokens[1].lower), 2
    return _atom_from_token(first, strings), 1


# Phase 4 arithmetic precedence: `por` (multiplication) binds tighter
# than `más` / `menos` (additive). Required so paper §5 Example 4's
# `los precios menos el descuento por los precios` parses as
# `precios − (descuento × precios)`, matching the gloss in the paper.
_MULT_OPS = {"por"}
_ADD_OPS = {"más", "menos"}


def _parse_mult_chain(
    tokens: list[Token], start: int, strings: list[str]
) -> tuple[Expr, int]:
    """Parse a left-associative chain of `por` operators starting at `start`.

    Returns (node, next_index). Multiplicative precedence — higher than
    additive — so `A más B por C` parses as `A más (B por C)`.
    """
    left, consumed = _parse_arith_atom(tokens[start:], strings)
    pos = start + consumed
    while pos < len(tokens) and tokens[pos].lower in _MULT_OPS:
        op = tokens[pos].lower
        right, right_consumed = _parse_arith_atom(tokens[pos + 1 :], strings)
        left = BinaryOp(op=op, left=left, right=right)
        pos += 1 + right_consumed
    return left, pos


def _parse_value(tokens: list[Token], strings: list[str]) -> Expr:
    """Parse the value/expression occupying a contiguous token slice.

    Handles a single-token literal/identifier, an articled binding name
    (`el <noun>` or `los <noun>`), a list literal, or an arithmetic
    expression using `más` / `menos` / `por`. Operator precedence: `por`
    binds tighter than `más` / `menos`; both levels are left-associative.

    Trailing or unconsumed tokens raise SyntaxError so callers don't
    silently drop user-written content.
    """
    if not tokens:
        raise SyntaxError("Expected value, got empty token slice.")
    left, pos = _parse_mult_chain(tokens, 0, strings)
    while pos < len(tokens):
        op_tok = tokens[pos]
        if op_tok.lower not in _ADD_OPS:
            if op_tok.lower in _MULT_OPS:  # pragma: no cover - mult_chain consumed it
                raise SyntaxError(
                    f"Unexpected multiplicative operator after value: {op_tok.text!r}"
                )
            tail = tokens[pos:]
            raise SyntaxError(
                f"Unexpected token {tail[0].text!r} in value position "
                f"(expected `más`/`menos`/`por` or end of clause). "
                f"Trailing: {[t.text for t in tail]}"
            )
        right, next_pos = _parse_mult_chain(tokens, pos + 1, strings)
        left = BinaryOp(op=op_tok.lower, left=left, right=right)
        pos = next_pos
    return left


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
    """True if `tok` is a Phase-3b/4 arithmetic operator (`más`/`menos`/`por`)."""
    return tok.lower in _ARITHMETIC_OPS


def _is_collection_expr(expr: Expr) -> bool:
    """True if `expr` is syntactically guaranteed to produce a collection.

    Phase 4 uses this for the static check that the RHS of a plural
    binding does not collapse to a scalar literal. The check is
    deliberately syntactic and conservative: a `ListLit` is collection;
    an `Identifier` is collection (its value is checked at runtime);
    a `BinaryOp` is collection if at least one operand syntactically is.
    A bare `IntLit` / `FloatLit` / `StringLit` is *not* collection, and
    triggers the `Los X son <scalar-literal>` parse error.
    """
    if isinstance(expr, ListLit):
        return True
    if isinstance(expr, Identifier):
        return True
    if isinstance(expr, BinaryOp):
        return _is_collection_expr(expr.left) or _is_collection_expr(expr.right)
    return False


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


def _parse_singular_binding(
    sentence: list[Token], strings: list[str]
) -> Statement:
    """Parse a sentence starting with a singular article (`el`/`la`/`un`/`una`).

    Recognised shapes:
        - `<sing-article> <noun> es <value>`        -> BindingSer
        - `<sing-article> <noun> está en <value>`   -> BindingEstar

    Phase 4 number-agreement check: a singular article followed by a
    plural noun (`el precios`) is a parse error here, regardless of
    what follows. This is the syntactic enforcement of paper §3.6.
    """
    if len(sentence) < 4:
        raise SyntaxError(
            f"Incomplete binding: {[t.text for t in sentence]}"
        )
    article, noun, copula, *rest = sentence
    if article.lower not in _SINGULAR_ARTICLES:
        raise SyntaxError(f"Expected singular article, got {article.text!r}")
    # Number-agreement check (paper §3.6): a singular article must
    # govern a singular noun. spaCy gives reliable Number=Plur
    # morphology on Spanish nouns the model knows; we trust it and
    # reject overt mismatches.
    if _is_plural_noun(noun):
        raise InflexionParseError(
            f"Number-agreement error: singular article {article.text!r} "
            f"with plural noun {noun.text!r}. Use a plural article "
            f"(`los`/`las`) for collections (paper §3.6)."
        )

    # Ser binding: `El X es Y.` — value slice may be a single token or
    # an arithmetic expression like `el total más 3`.
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


# Backwards-compat alias: the Phase-3b name was `_parse_binding_or_decir`.
_parse_binding_or_decir = _parse_singular_binding


def _parse_plural_binding(
    sentence: list[Token], strings: list[str]
) -> BindingSerPlural:
    """Parse a plural ser binding: `Los <noun> son <collection-expr>.`

    Phase 4 entry point. The verb form must be `son` (plural ser
    indicative); a singular `es` after a plural article is rejected as
    a number-agreement error. The RHS must be a collection-producing
    expression — see `_is_collection_expr` and the Phase 4 simplification
    note in the module docstring.

    Phase 4 deliberately does not support a plural *estar* binding
    (`Los X están en …`); the spec defers mutable collection bindings.
    """
    if len(sentence) < 4:
        raise SyntaxError(
            f"Incomplete plural binding: {[t.text for t in sentence]}"
        )
    article, noun, copula, *rest = sentence
    if article.lower not in _PLURAL_ARTICLES:
        raise SyntaxError(  # pragma: no cover - caller filters
            f"Expected plural article, got {article.text!r}"
        )
    # Paper §3.6: plural article requires plural noun. spaCy's tagger
    # is unreliable on novel single-letter / latinate identifiers — it
    # routinely tags user identifiers like `base` or `valores` as
    # `Number=Sing` even when the surrounding article is plural. We
    # therefore do NOT raise on the article→noun direction here; the
    # plural-verb check below (`son` vs `es`) and the
    # collection-producing-RHS check together are sufficient to keep
    # the agreement rule meaningful without false positives on novel
    # identifiers. The singular-article→plural-noun direction (caught
    # in `_parse_singular_binding`) is the asymmetric one we keep
    # strict, because Spanish nouns that the model already knows
    # (`precios`, `valores`) reliably carry their plural marking.
    # Verb form: only `son` (plural ser indicative) supported in Phase 4.
    # Mutable plural bindings (`están en …`) are deferred.
    if copula.lower != "son":
        if copula.lower == "es":
            raise InflexionParseError(
                f"Number-agreement error: plural article {article.text!r} "
                f"with singular verb {copula.text!r}. Use `son` for "
                f"plural ser bindings (paper §3.6)."
            )
        raise InflexionParseError(
            f"Phase 4 plural ser binding expects `son` after `{article.text} "
            f"{noun.text}`; got {copula.text!r}. Plural estar (`están en`) "
            f"is deferred to a later phase."
        )
    if not rest:
        raise SyntaxError(
            f"Plural ser-binding `{article.text} {noun.text} son …` missing value."
        )
    value = _parse_value(rest, strings)
    # Phase 4 simplification of paper §3.6: implicit-length scalar
    # broadcast is deferred. Require an explicit collection-producing
    # RHS.
    if not _is_collection_expr(value):
        raise InflexionParseError(
            f"Phase 4 plural binding `{article.text} {noun.text} son …` "
            f"requires a collection-producing RHS (list literal or "
            f"plural-identifier-bearing expression). The implicit-length "
            f"scalar broadcast `Los X son 5` (paper §3.6) is deferred to "
            f"Phase 5+."
        )
    return BindingSerPlural(name=noun.lower, value=value)


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
        - `Decí <sing-article> <noun>`   -> DecirCommand        (binding name)
        - `Decí los <noun>`              -> DecirPluralCommand  (Phase 4)
        - `Decí <string-literal>`        -> DecirLiteral        (direct print)
        - `Decí <expr>`                  -> DecirExpr           (arbitrary expr)
        - `Decilo` / `Decila` / …        -> ImperativeCall      (enclitic form)
    """
    if not tokens:
        raise SyntaxError("Empty imperative clause.")
    first = tokens[0]
    surface = first.lower

    # `Decí` followed by an object — full-NP form, plural-NP form (Phase 4),
    # string-literal form, or an arithmetic expression.
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
        # `Decí los <noun>` — plural read-and-print (Phase 4). Kept as a
        # distinct AST node so the singular path is unchanged.
        if (
            len(tokens) == 3
            and tokens[1].lower in _PLURAL_ARTICLES
            and not _is_arithmetic_op(tokens[2])
        ):
            return DecirPluralCommand(name=tokens[2].lower)
        # `Decí <sing-article> <noun>` — singular read-and-print.
        if (
            len(tokens) == 3
            and tokens[1].lower in _SINGULAR_ARTICLES
            and not _is_arithmetic_op(tokens[2])
        ):
            return DecirCommand(name=tokens[2].lower)
        # `Decí <value-expression>` — anything else parseable as a value
        # expression (arithmetic, list literal, plural-binding read).
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
        f"Unrecognised imperative form {first.text!r}. Phase 4 supports "
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


def parse(tokens: list[Token], strings: list[str]) -> Program:
    """Parse a token stream + string table into a Program."""
    statements: list[Statement] = []
    for sentence in _split_sentences(tokens):
        first = sentence[0]
        if first.lower == "cuando":
            statements.append(_parse_cuando(sentence, strings))
        elif first.lower == "mientras":
            statements.append(_parse_mientras(sentence, strings))
        elif first.lower in _PLURAL_ARTICLES:
            statements.append(_parse_plural_binding(sentence, strings))
        elif first.lower in _SINGULAR_ARTICLES:
            statements.append(_parse_singular_binding(sentence, strings))
        elif _is_hace_imperative(first):
            statements.append(_parse_mutation(sentence, strings))
        else:
            statements.append(_parse_decir(sentence, strings))
    return Program(statements=tuple(statements))
