# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión parser — Phase 5.

Recognises these sentence shapes (each terminated by `.` — Phase 5
additionally treats `...` as a sentence terminator, retained inside the
sentence as the function-body elision sentinel):

    1.  Ser-binding (immutable, singular): `El <noun> es <value>.`
    2.  Ser-binding (immutable, plural):   `Los <noun> son <collection-expr>.`
    3.  Estar-binding (mutable):           `El <noun> está en <value>.`
    4.  Mutation:                          `Hacé que el <noun> esté en <value>.`
    5.  Decí read-and-print (scalar):      `Decí el <noun>.` / `Decí <expr>.`
    6.  Decí read-and-print (plural):      `Decí los <noun>.`
    7.  Vos-imperative w/ clitic:          `Decilo.`
    8.  Subjunctive deferred:              `Cuando el <noun> esté en <value>, <imp>.`
    9.  While-loop:                        `Mientras el <noun> [no] esté en <value>,
                                            <imperative>.`
    10. Function definition (Phase 5):     `La función <name>, que toma <params>,
                                            es <body>.`  (body may be `...`)
    11. Vos-imperative w/ clitic-stack:    `Dámelo.` / `Transferíselo.`  (Phase 5)

Value positions in Phase 5 additionally accept:
    - Function calls: `<verb-infinitive> <arg1> <arg2> ...` where each arg
      is `<article> <noun>`, a numeric literal, or a list literal. Args
      are parsed greedily until an arithmetic operator or unrecognised
      token is reached.
    - Reductions: `el resultado de <verb-infinitive> <article> <noun>`
      folds a collection to a scalar (paper §5 Example 4 line 4).

Number agreement (paper §3.6, Phase 4 carries into Phase 5):
    - A plural article (`los` / `las`) must combine with a plural noun
      and a plural verb form (`son`); singular article + plural noun
      (`el precios`) is a parse error.
    - The RHS of a plural ser binding must be a collection-producing
      expression. A `FunctionCall` is treated as collection-producing
      conservatively (the runtime check enforces actual shape).
"""
from __future__ import annotations

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


# Vos-imperative stressed-vowel endings — `-á` / `-é` / `-í` mark the stem
# of an `-ar` / `-er` / `-ir` verb's imperative respectively. Phase 5 uses
# these for the bare-stem check after clitic-stack stripping. The bare
# stem also retains its written accent (decí, hacé, transferí) when no
# clitics are attached; with one enclitic the accent is conventionally
# dropped (decilo, not decílo). Both forms are accepted.
_IMPERATIVE_STEM_ENDINGS = ("á", "é", "í")

# Map accented vowels to their unaccented form for lemma reconstruction.
_ACCENT_FOLD = str.maketrans({"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u"})


def _strip_clitic_stack(verb_form: str) -> tuple[str, tuple[str, ...]]:
    """Strip a stack of one-or-more enclitic clitics from `verb_form`.

    Phase 5 generalises `_strip_clitic`. Returns the bare verb stem and
    the tuple of clitics in *fixed Spanish order* (i.e. left-to-right
    as they appear in the surface form). The stripping is right-to-left
    by longest-suffix-first, with a hard cap of 3 clitics — the maximum
    that Spanish grammar permits in practice (e.g. `dándomenoslo` is
    already unusual; four is unattested).

    The function does no lemma validity check; the caller is responsible
    for verifying the bare stem maps to a recognised verb. This split
    keeps the stripping logic small and lets the caller decide what
    "recognised" means in its context.
    """
    low = verb_form.lower()
    clitics: list[str] = []
    while len(clitics) < 3:
        stripped, c = _strip_clitic(low)
        if c is None:
            break
        clitics.insert(0, c)
        low = stripped
    return low, tuple(clitics)


def _lemma_from_vos_imperative(bare: str) -> str | None:
    """Derive the dictionary infinitive from a vos-imperative bare stem.

    Lookup order:
        1. Explicit override in `_VOS_IMPERATIVE_LEMMAS` (covers irregulars
           that spaCy mis-lemmatises or that have a non-derivable mapping).
        2. Suffix rule: a stem ending in stressed `-á` / `-é` / `-í` maps
           to `-ar` / `-er` / `-ir` after accent-folding the final vowel.
           `transferí` → `transferir`; `hablá` → `hablar`; `comé` → `comer`.

    Returns `None` if no rule applies — the caller distinguishes a
    well-formed-but-unknown imperative from a non-imperative token.
    """
    if not bare:
        return None
    if bare in _VOS_IMPERATIVE_LEMMAS:
        return _VOS_IMPERATIVE_LEMMAS[bare]
    last = bare[-1]
    if last in _IMPERATIVE_STEM_ENDINGS:
        body = bare[:-1] + last.translate(_ACCENT_FOLD)
        if last == "á":
            return body + "r"
        if last == "é":
            return body + "r"
        if last == "í":
            return body + "r"
    return None


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


def _is_infinitive(tok: Token) -> bool:
    """True if `tok` is morphologically a Spanish infinitive (POS=VERB, VerbForm=Inf)."""
    return tok.pos == "VERB" and "VerbForm=Inf" in tok.morph


def _is_arg_starter(tok: Token) -> bool:
    """True if `tok` can start a function-call argument.

    A function-call argument is one of:
        - `<article> <noun>`         (articled identifier)
        - `[ ... ]`                  (list literal)
        - a numeric / string literal
        - a bare identifier that is NOT an arithmetic operator, a clitic
          pronoun, punctuation, an article on its own, or another verb.

    Phase 5 is conservative — when in doubt, an unrecognised token ends
    the arg loop rather than being adopted as a bare-identifier arg.
    """
    if tok.is_punct:
        return False
    if tok.text == "[":
        return True
    if tok.lower in _ARITHMETIC_OPS:
        return False
    if tok.lower in _SINGULAR_ARTICLES or tok.lower in _PLURAL_ARTICLES:
        return True
    if tok.is_numeric or tok.is_string_placeholder:
        return True
    return False


def _parse_function_call(
    tokens: list[Token], strings: list[str]
) -> tuple[FunctionCall, int]:
    """Parse `<verb-infinitive> <arg1> <arg2> ...`.

    Caller has already verified `_is_infinitive(tokens[0])`. Args are
    consumed greedily by `_parse_arith_atom` itself, but restricted to
    arg-shaped operands (no nested arithmetic at the arg level — Phase
    5 wants explicit parenthesisation eventually; for now the arg loop
    stops at any arithmetic operator). Returns the `FunctionCall` plus
    total tokens consumed (head + args).
    """
    head = tokens[0]
    args: list[Expr] = []
    i = 1
    while i < len(tokens):
        if not _is_arg_starter(tokens[i]):
            break
        arg, consumed = _parse_arith_atom(tokens[i:], strings)
        args.append(arg)
        i += consumed
    return FunctionCall(name=head.lower, args=tuple(args)), i


def _parse_reduction(
    tokens: list[Token], strings: list[str]
) -> tuple[Reduction, int]:
    """Parse `el resultado de <verb-infinitive> <article> <noun>`.

    Caller has already verified the reduction-prefix shape. Phase 5
    requires the target to be an articled identifier; reducing an
    arbitrary expression is deferred. The verb infinitive names the
    fold op — the interpreter's reduction dispatch table maps op
    surface forms (e.g. `sumar` → `sum`) to Python callables.
    """
    op_tok = tokens[3]
    target_art = tokens[4]
    target_noun = tokens[5]
    if (
        target_art.lower not in _SINGULAR_ARTICLES
        and target_art.lower not in _PLURAL_ARTICLES
    ):
        raise InflexionParseError(
            f"Reduction `el resultado de {op_tok.text} …` expects an articled "
            f"target (`los X`/`las X`); got {target_art.text!r}."
        )
    return (
        Reduction(op=op_tok.lower, target=Identifier(target_noun.lower)),
        6,
    )


def _parse_arith_atom(tokens: list[Token], strings: list[str]) -> tuple[Expr, int]:
    """Parse a single arithmetic operand starting at `tokens[0]`.

    Operand shapes recognised in Phase 5:
        - `el resultado de <verb-inf> <article> <noun>`  -> Reduction       (6 tokens)
        - `<verb-infinitive> <arg> <arg> ...`            -> FunctionCall    (≥1 tokens)
        - `[<num>, <num>, ...]`                          -> ListLit
        - `el <name>` / `la <name>`                      -> Identifier      (2 tokens)
        - `los <name>` / `las <name>`                    -> Identifier      (2 tokens)
        - `<literal>`                                    -> StringLit / IntLit / FloatLit
        - `<identifier>`                                 -> Identifier      (1 token)

    Returns the parsed Expr plus the number of tokens consumed.
    """
    if not tokens:
        raise SyntaxError("Expected value, got end of clause.")
    first = tokens[0]
    # Reduction prefix `el resultado de <verb-inf> <article> <noun>` — check
    # before generic article handling so the longer pattern wins.
    if (
        len(tokens) >= 6
        and first.lower == "el"
        and tokens[1].lower == "resultado"
        and tokens[2].lower == "de"
        and _is_infinitive(tokens[3])
    ):
        return _parse_reduction(tokens, strings)
    if first.text == "[":
        return _parse_list_literal(tokens, strings)
    # Function call: a verb in infinitive form heads a positional arg list.
    # Detected at the atom level so it can appear anywhere a value can.
    if _is_infinitive(first):
        return _parse_function_call(tokens, strings)
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

    Phase 5 additions:
        - A `FunctionCall` is conservatively treated as
          collection-producing — the runtime check enforces actual
          shape, raising a clear error if a plural binding receives a
          scalar return.
        - A `Reduction` is *not* collection (it folds to a scalar) and
          therefore is not legal on the RHS of a plural ser binding.
    """
    if isinstance(expr, ListLit):
        return True
    if isinstance(expr, Identifier):
        return True
    if isinstance(expr, FunctionCall):
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
    """Split the token stream into sentences terminated by `.` or `...`.

    Phase 5 adds `...` as an additional sentence terminator so that the
    function-body elision marker (`La función X, ..., es ...`) can end
    a sentence without requiring the author to write `... .`. The `...`
    token is *retained* as the final token of the sentence so the
    function-def parser can detect the elision; a bare `.` is stripped
    as in Phase 4.
    """
    sentences: list[list[Token]] = []
    current: list[Token] = []
    for tok in tokens:
        if tok.text == ".":
            if current:
                sentences.append(current)
                current = []
            continue
        current.append(tok)
        if tok.text == "...":
            sentences.append(current)
            current = []
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


def _parse_function_def(
    sentence: list[Token], strings: list[str]
) -> FunctionDef:
    """Parse `La función <name>, que toma <params>, es <body>.`.

    Layout (after lex):
        [la, función, NAME, ',', que, toma, P-LIST..., ',', es, BODY..., (...?)]

    Phase 5 conventions:
        - The opening determiner is `la` and the head noun is `función`.
        - The name is a single bare-identifier token following `función`.
        - The relative clause `, que toma <params>,` introduces a
          comma-and-y separated list of `<indef-article> <noun>` pairs.
          Plural-articled params are *accepted but treated as scalar
          formals at the param-name level* — the runtime broadcasts
          element-wise as Phase 4 already does.
        - `, es <body>` opens the body. The body is either a single
          `...` token (elided) or any Phase-5 value expression.

    A trailing `...` survives sentence-splitting as the last token of
    the sentence and is detected here as the elision marker.
    """
    if len(sentence) < 9:
        raise InflexionParseError(
            f"Function definition expects `La función <name>, que toma "
            f"<params>, es <body>`; got {[t.text for t in sentence]}"
        )
    art, fn_word, name_tok, comma1, que, toma, *rest = sentence
    if art.lower != "la":
        raise InflexionParseError(
            f"Function definition opens with `La función`; got {art.text!r}."
        )
    if fn_word.lower != "función":
        raise InflexionParseError(
            f"Expected `función` after `La`; got {fn_word.text!r}."
        )
    if comma1.text != ",":
        raise InflexionParseError(
            f"Expected `,` after function name `{name_tok.text}`; "
            f"got {comma1.text!r}."
        )
    if que.lower != "que":
        raise InflexionParseError(
            f"Expected `que` in relative clause; got {que.text!r}."
        )
    if toma.lower != "toma":
        raise InflexionParseError(
            f"Expected `toma` in relative clause; got {toma.text!r}."
        )
    # Locate the comma followed by `es` that opens the body.
    body_open_idx: int | None = None
    for i in range(len(rest) - 1):
        if rest[i].text == "," and rest[i + 1].lower == "es":
            body_open_idx = i
            break
    if body_open_idx is None:
        raise InflexionParseError(
            f"Function definition is missing `, es <body>` clause; "
            f"got {[t.text for t in sentence]}"
        )
    param_tokens = rest[:body_open_idx]
    body_tokens = rest[body_open_idx + 2 :]  # skip `,` and `es`
    params = _parse_param_list(param_tokens)
    if (
        len(body_tokens) == 1
        and body_tokens[0].text == "..."
    ):
        body: Expr | None = None
    elif not body_tokens:
        raise InflexionParseError(
            f"Function `{name_tok.text}` is missing its body (`es <body>`)."
        )
    else:
        body = _parse_value(body_tokens, strings)
    return FunctionDef(name=name_tok.lower, params=params, body=body)


def _parse_param_list(tokens: list[Token]) -> tuple[str, ...]:
    """Parse a comma-and-y separated list of `<article> <noun>` pairs.

    Accepts both singular indefinite articles (`un` / `una`) — the
    canonical form for the relative-clause function definition — and,
    permissively, definite or plural articles, since the article in a
    function-definition's parameter declaration does not carry the
    scalar/collection distinction that it carries in a binding (the
    parameter is an opaque slot until the call site).

    Returns the parameter names as a tuple of lowercased surface forms.
    """
    if not tokens:
        raise InflexionParseError(
            "Function-definition relative clause has no parameters; "
            "`que toma <article> <noun>` is required."
        )
    params: list[str] = []
    i = 0
    while i < len(tokens):
        art = tokens[i]
        if (
            art.lower not in _SINGULAR_ARTICLES
            and art.lower not in _PLURAL_ARTICLES
        ):
            raise InflexionParseError(
                f"Expected article before parameter noun; got {art.text!r}."
            )
        if i + 1 >= len(tokens):
            raise InflexionParseError(
                f"Article {art.text!r} not followed by a parameter noun."
            )
        noun = tokens[i + 1]
        params.append(noun.lower)
        i += 2
        if i >= len(tokens):
            break
        sep = tokens[i]
        if sep.text == "," or sep.lower == "y":
            i += 1
            # Allow `, y` (Oxford-comma-style) by consuming another `y` if present.
            if i < len(tokens) and tokens[i].lower == "y":
                i += 1
            continue
        raise InflexionParseError(
            f"Expected `,` or `y` between parameters; got {sep.text!r}."
        )
    return tuple(params)


def _parse_clitic_stack_imperative(
    token: Token,
) -> CliticImperativeCall | None:
    """Parse a single-token vos-imperative with a clitic stack of ≥1 clitics.

    Returns the parsed `CliticImperativeCall` if the surface form decomposes
    cleanly into a recognised vos-imperative stem plus a clitic stack;
    returns `None` if it does not (so the caller can try a different
    imperative shape — single-clitic Phase-1 path, for instance).
    """
    if token.is_punct:
        return None
    bare, clitics = _strip_clitic_stack(token.text)
    if not clitics:
        return None
    lemma = _lemma_from_vos_imperative(bare)
    if lemma is None:
        return None
    return CliticImperativeCall(verb_lemma=lemma, clitics=clitics)


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
    # Phase 1 single-clitic backward-compat: strip one clitic and look up
    # the bare stem in the explicit override table. This branch keeps
    # `Decilo`, `Hacelo`, etc. emitting `ImperativeCall` exactly as Phase 1
    # did, so the existing test corpus is byte-for-byte unaffected.
    bare, clitic = _strip_clitic(surface)
    if bare in _VOS_IMPERATIVE_LEMMAS:
        return ImperativeCall(
            verb_lemma=_VOS_IMPERATIVE_LEMMAS[bare], clitic=clitic
        )
    # Phase 5: clitic-stack form (one-or-more clitics on a vos-imperative
    # stem resolved via the explicit table or by the `-á`/`-é`/`-í` suffix
    # rule). Catches `Transferíselo`, `Dámelo`, `Dáselo`, etc.
    stack_call = _parse_clitic_stack_imperative(first)
    if stack_call is not None:
        return stack_call
    raise SyntaxError(
        f"Unrecognised imperative form {first.text!r}. Phase 5 supports "
        f"vos-imperatives of: {sorted(set(_VOS_IMPERATIVE_LEMMAS.values()))} "
        f"plus regular `-ar`/`-er`/`-ir` infinitives reconstructible from "
        f"a vos-imperative stem with one or more enclitic clitics."
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


def _is_function_def_opening(sentence: list[Token]) -> bool:
    """True if the sentence opens with `La función …` (Phase 5 function definition)."""
    return (
        len(sentence) >= 3
        and sentence[0].lower == "la"
        and sentence[1].lower == "función"
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
        elif _is_function_def_opening(sentence):
            # Phase 5: function definitions take precedence over the plain
            # singular-binding shape, since both open with `La …`.
            statements.append(_parse_function_def(sentence, strings))
        elif first.lower in _PLURAL_ARTICLES:
            statements.append(_parse_plural_binding(sentence, strings))
        elif first.lower in _SINGULAR_ARTICLES:
            statements.append(_parse_singular_binding(sentence, strings))
        elif _is_hace_imperative(first):
            statements.append(_parse_mutation(sentence, strings))
        else:
            statements.append(_parse_decir(sentence, strings))
    return Program(statements=tuple(statements))
