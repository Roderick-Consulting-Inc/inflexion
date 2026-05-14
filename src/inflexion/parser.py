# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión parser — Phase 6.

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
    12. Aspect-marked operation (Phase 6):  `Calculó las potencias del N.`
                                            (perfective, eager) /
                                            `Calculaba las potencias del N.`
                                            (imperfective, lazy stream)

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


# Diminutive / augmentative suffixes used by Phase 6 — duplicated here
# (rather than imported from the interpreter) so the parser stays
# import-cycle-free. Kept in lockstep with `interpreter._DIMINUTIVE_SUFFIXES`.
_DIMINUTIVE_SUFFIX_FORMS = (
    "illa",
    "illo",
    "ita",
    "ito",
    "ona",
    "aza",
    "azo",
    "ón",
)


def _is_infinitive(tok: Token) -> bool:
    """True if `tok` is morphologically a Spanish infinitive (POS=VERB, VerbForm=Inf)."""
    return tok.pos == "VERB" and "VerbForm=Inf" in tok.morph


def _looks_like_diminutive_function_head(tok: Token) -> bool:
    """True if `tok`'s surface form carries a Phase-6 diminutive / augmentative suffix.

    Used by the function-call parser to accept call heads like
    `busquito` (cheap variant of `buscar`) or `buscazo` (thorough
    variant) — spaCy tags them as NOUN / PROPN rather than VERB
    because they are coinages and not in the model's vocabulary. The
    runtime is the layer that determines whether the variant resolves;
    the parser's job is only to recognise the *shape* so the call
    parses and the runtime can raise a meaningful "variant not
    registered" error.
    """
    surf = tok.lower
    if tok.is_punct:
        return False
    for suffix in _DIMINUTIVE_SUFFIX_FORMS:
        if surf.endswith(suffix) and len(surf) > len(suffix) + 1:
            return True
    return False


def _is_arg_starter(tok: Token) -> bool:
    """True if `tok` can start a function-call argument.

    A function-call argument is one of:
        - `<article> <noun>`         (articled identifier)
        - `[ ... ]`                  (list literal)
        - `( <expr> )`               (parenthesised expression, Phase 7b)
        - a numeric / string literal
        - a bare identifier that is NOT an arithmetic operator, a clitic
          pronoun, punctuation, an article on its own, or another verb.

    Phase 5 is conservative — when in doubt, an unrecognised token ends
    the arg loop rather than being adopted as a bare-identifier arg.
    """
    if tok.is_punct and tok.text not in {"(", "["}:
        return False
    if tok.text in {"[", "("}:
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


import re as _re

# Ordinal pattern for `el N-ésimo de <list>` (Phase 7c list indexing).
# Matches: `5-ésimo`, `3esimo`, `1ésima` etc.
_ORDINAL_RE = _re.compile(r"^(\d+)[-–]?[eé]simo$", _re.IGNORECASE)

# Variable-identifier ordinal: `i-ésimo`, `puntero-ésimo`, etc.
# The captured group is the variable/identifier stem (not a digit sequence).
# Distinguished from _ORDINAL_RE by requiring a non-digit first character.
_VAR_ORDINAL_RE = _re.compile(r"^([^\d\W]\w*)[-–]?[eé]simo$", _re.IGNORECASE | _re.UNICODE)

# Named ordinal shortcuts (Phase 7c).
_NAMED_ORDINALS: dict[str, int] = {
    "primero": 1,
    "primera": 1,
    "segundo": 2,
    "segunda": 2,
}

# Keywords that mark Phase 7c `el`-phrase operations (singular article opens).
_LARGO = "largo"
_CARACTER = "carácter"
_CODIGO = "código"
_CARACTERES = "caracteres"


def _try_parse_el_phrase(
    tokens: list[Token], strings: list[str]
) -> "tuple[Expr, int] | None":
    """Try to parse a Phase 7c `el`-opened special phrase.

    Returns ``(expr, tokens_consumed)`` if a special form is matched,
    ``None`` if the token sequence is not a Phase 7c phrase (so the caller
    falls through to the generic article handler which produces an Identifier).

    Special phrases (all start with `el`):
        ``el largo de <expr>``               → StringLen
        ``el carácter N de <expr>``          → StringCharAt (1-indexed)
        ``el código de <expr>``              → CharCode
        ``el carácter del código <expr>``    → CodeToChar
        ``el N-ésimo de <expr>``             → ListIndexGet (literal 1-indexed)
        ``el i-ésimo de <expr>``             → ListIndexGet (variable 1-indexed)
        ``el primero de <expr>``             → ListIndexGet(1, ...)
        ``el segundo de <expr>``             → ListIndexGet(2, ...)
    """
    # Must begin with `el` followed by at least one more token.
    if len(tokens) < 2:
        return None
    # el largo de <expr>
    if tokens[1].lower == _LARGO and len(tokens) >= 3 and tokens[2].lower == "de":
        target, consumed = _parse_arith_atom(tokens[3:], strings)
        return StringLen(target=target), 3 + consumed
    # el código de <expr>
    if tokens[1].lower == _CODIGO and len(tokens) >= 3 and tokens[2].lower == "de":
        target, consumed = _parse_arith_atom(tokens[3:], strings)
        return CharCode(target=target), 3 + consumed
    # el carácter del código <expr>
    if (
        tokens[1].lower == _CARACTER
        and len(tokens) >= 4
        and tokens[2].lower == "del"
        and tokens[3].lower == _CODIGO
    ):
        code_expr, consumed = _parse_arith_atom(tokens[4:], strings)
        return CodeToChar(code=code_expr), 4 + consumed
    # el carácter N de <expr>  — where N is a value expression (typically
    # numeric literal or identifier).  We look for the word `de` to delimit
    # the index from the string target.
    if tokens[1].lower == _CARACTER and len(tokens) >= 4:
        # find `de` after the index expression — greedy: we try to parse the
        # index as a single atom, then expect `de`.
        try:
            idx_expr, idx_consumed = _parse_arith_atom(tokens[2:], strings)
        except (SyntaxError, InflexionParseError):
            return None
        de_pos = 2 + idx_consumed
        if de_pos >= len(tokens) or tokens[de_pos].lower != "de":
            return None
        target, tgt_consumed = _parse_arith_atom(tokens[de_pos + 1 :], strings)
        return StringCharAt(index=idx_expr, target=target), de_pos + 1 + tgt_consumed
    # el N-ésimo / el i-ésimo de <expr>  — ordinal form (single token).
    # Handles both literal-integer ordinals (`5-ésimo` → IntLit) and
    # variable ordinals (`i-ésimo`, `puntero-ésimo` → Identifier, resolved
    # at runtime).
    if len(tokens) >= 4 and tokens[2].lower == "de":
        idx_tok = tokens[1]
        # Numeric literal ordinal: `5-ésimo`
        m_num = _ORDINAL_RE.match(idx_tok.text)
        if m_num:
            index_expr: "Expr" = IntLit(int(m_num.group(1)))
            target, consumed = _parse_arith_atom(tokens[3:], strings)
            return ListIndexGet(index=index_expr, target=target), 3 + consumed
        # Named ordinal shortcut: `primero`, `segundo`
        if idx_tok.lower in _NAMED_ORDINALS:
            index_expr = IntLit(_NAMED_ORDINALS[idx_tok.lower])
            target, consumed = _parse_arith_atom(tokens[3:], strings)
            return ListIndexGet(index=index_expr, target=target), 3 + consumed
        # Variable ordinal: `i-ésimo`, `puntero-ésimo` — variable resolved at runtime.
        m_var = _VAR_ORDINAL_RE.match(idx_tok.text)
        if m_var:
            index_expr = Identifier(m_var.group(1).lower())
            target, consumed = _parse_arith_atom(tokens[3:], strings)
            return ListIndexGet(index=index_expr, target=target), 3 + consumed
    # Ordinal split by spaCy into [<ordinal-tok>, -, ésimo, de, ...].
    # Handles both integer (`5`, `-`, `ésimo`) and variable (`i`, `-`, `ésimo`) forms.
    _ESIMO_FORMS = ("ésimo", "esimo", "ésima", "esima")
    if (
        len(tokens) >= 6
        and tokens[2].text == "-"
        and tokens[3].lower in _ESIMO_FORMS
        and tokens[4].lower == "de"
    ):
        idx_tok_split = tokens[1]
        if idx_tok_split.is_integer_literal:
            index_expr_split: "Expr" = IntLit(int(idx_tok_split.text))
        else:
            # Treat as an identifier (variable name).
            index_expr_split = Identifier(idx_tok_split.lower)
        target, consumed = _parse_arith_atom(tokens[5:], strings)
        return ListIndexGet(index=index_expr_split, target=target), 5 + consumed
    return None


def _find_matching_paren(tokens: list[Token], start: int = 0) -> int:
    """Return the index of the `)` that matches the `(` at `tokens[start]`.

    Raises `InflexionParseError` if the parenthesis is unmatched.
    """
    if tokens[start].text != "(":
        raise InflexionParseError(  # pragma: no cover
            f"Expected `(` at position {start}; got {tokens[start].text!r}"
        )
    depth = 0
    for i in range(start, len(tokens)):
        if tokens[i].text == "(":
            depth += 1
        elif tokens[i].text == ")":
            depth -= 1
            if depth == 0:
                return i
    raise InflexionParseError(
        f"Unmatched `(` in expression: {[t.text for t in tokens[start:]]}"
    )


def _parse_if_expression(
    tokens: list[Token], strings: list[str]
) -> tuple[IfExpression, int]:
    """Parse `si <cond>, entonces <then>; sino, <else>` in expression position.

    Phase 7b: distinct from the statement form (`IfStatement`) — the keyword
    `entonces` marks the then-branch and signals expression context. Returns
    ``(IfExpression, tokens_consumed)``.

    The if-expression is greedy: it consumes all tokens from `si` to the end
    of the token slice supplied by the caller.  This means the if-expression
    must be the outermost (last) construct in a value context — nesting
    requires chaining in the `sino` branch (the common recursive pattern).

    **Separator policy (relaxed — Phase 7a fix):**
    The `,` after the condition is required (natural Spanish: "si COND, entonces …").
    The separator *between* `entonces`-branch and `sino` is flexible: `;`, `,`,
    or bare (no separator before `sino`) are all accepted. Likewise, the `,`
    after `sino` is optional. This lets users write the natural form
    ``si el n es 0, entonces 1 sino 0`` as well as the more punctuated
    ``si el n es 0, entonces 1; sino, 0``. The parser detects `sino` as the
    keyword delimiter regardless of surrounding punctuation.

    Grammar (informal):
        si-expr ::= `si` cond `,` `entonces` then [`;`|`,`] `sino` [`,`] else
    """
    # tokens[0] is `si`.
    # Find the first `,` — it terminates the condition (required).
    comma_idx = next(
        (j for j, t in enumerate(tokens) if t.text == ","), None
    )
    if comma_idx is None:
        raise InflexionParseError(
            "If-expression: expected `,` after condition (before `entonces`). "
            "Form: `si COND, entonces THEN sino ELSE`."
        )
    cond_tokens = tokens[1:comma_idx]  # skip `si`

    # tokens[comma_idx + 1] must be `entonces`.
    entonces_pos = comma_idx + 1
    if entonces_pos >= len(tokens) or tokens[entonces_pos].lower != "entonces":
        _got = repr(tokens[entonces_pos].text) if entonces_pos < len(tokens) else "'<eof>'"
        raise InflexionParseError(
            f"If-expression: expected `entonces` after `,`; got {_got}. "
            f"Form: `si COND, entonces THEN sino ELSE`."
        )

    # Locate `sino` — the keyword delimiter for the then/else boundary.
    # Accept it preceded by `;`, `,`, or nothing (bare). Do NOT require a
    # specific separator so that `si … entonces X sino Y` (no punctuation),
    # `si … entonces X, sino Y` (comma), and the strict `si … entonces X;
    # sino, Y` form are all valid.
    sino_idx = next(
        (j for j in range(entonces_pos + 1, len(tokens)) if tokens[j].lower == "sino"),
        None,
    )
    if sino_idx is None:
        raise InflexionParseError(
            "If-expression: missing `sino` branch. "
            "Form: `si COND, entonces THEN sino ELSE`."
        )

    # then-tokens: everything between `entonces` and `sino`, stripping any
    # trailing `;` or `,` separator.
    then_raw = tokens[entonces_pos + 1 : sino_idx]
    while then_raw and then_raw[-1].text in (";", ","):
        then_raw = then_raw[:-1]

    # else-tokens: everything after `sino`, stripping an optional leading `,`.
    after_sino = tokens[sino_idx + 1 :]
    if after_sino and after_sino[0].text == ",":
        after_sino = after_sino[1:]

    if not then_raw:
        raise InflexionParseError("If-expression: `entonces` branch is empty.")
    if not after_sino:
        raise InflexionParseError("If-expression: `sino` branch is empty.")

    condition = _parse_comparison_condition(cond_tokens, strings)
    then_value = _parse_value(then_raw, strings)
    else_value = _parse_value(after_sino, strings)

    return IfExpression(condition=condition, then_value=then_value, else_value=else_value), len(tokens)


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

    # Phase 7b: if-then-else expression — `si COND, entonces THEN; sino, ELSE`.
    # Must be checked before article / identifier handling so `si` is never
    # accidentally treated as a variable name in value position.
    if first.lower == "si":
        return _parse_if_expression(tokens, strings)

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

    # Phase 7c: string / list index operations that open with `el` — checked
    # before the generic article handler so the multi-keyword patterns win.
    # These are handled in `_parse_arith_atom_el_phrase` to keep this
    # function readable.
    if first.lower == "el" and len(tokens) >= 2:
        el_result = _try_parse_el_phrase(tokens, strings)
        if el_result is not None:
            return el_result

    # Phase 7c: `los caracteres de <expr>` — string-to-list conversion.
    if (
        first.lower == "los"
        and len(tokens) >= 3
        and tokens[1].lower == "caracteres"
        and tokens[2].lower == "de"
    ):
        target, consumed = _parse_arith_atom(tokens[3:], strings)
        return StringChars(target=target), 3 + consumed

    if first.text == "[":
        return _parse_list_literal(tokens, strings)

    # Phase 7b: parenthesised expression — `( <expr> )`.
    # Enables `fact (el n menos 1)` and `(el a más el b)` grouping.
    if first.text == "(":
        end_idx = _find_matching_paren(tokens, 0)
        inner = tokens[1:end_idx]
        if not inner:
            raise InflexionParseError("Empty parenthesised expression `()`.")
        return _parse_value(inner, strings), end_idx + 1

    # Function call: a verb in infinitive form heads a positional arg list.
    # Detected at the atom level so it can appear anywhere a value can.
    if _is_infinitive(first):
        return _parse_function_call(tokens, strings)
    # Phase 6: a diminutive / augmentative-suffixed token at the head of
    # what looks like a function call (i.e. followed by at least one
    # arg-starter) is parsed as a function call so the runtime can
    # surface the "variant not registered" error. We require an
    # arg-starter to avoid mis-parsing a bare-identifier read like
    # `Decí la sumita.` as a zero-arg function call.
    if (
        _looks_like_diminutive_function_head(first)
        and len(tokens) >= 2
        and _is_arg_starter(tokens[1])
    ):
        return _parse_function_call(tokens, strings)

    # Phase 7b: identifier followed by an argument-starter — function call
    # for names that spaCy does NOT tag as a Spanish infinitive (PROPN / NOUN
    # heads like `fact`, `fib`, `sign`).
    #
    # Guard: we require the next token to be a genuine arg-starter (article,
    # numeric, string, `[`, `(`) but NOT an arithmetic operator so that
    # `el r más 1` or bare-identifier arithmetic stays unaffected.
    if (
        not first.is_punct
        and not first.is_string_placeholder
        and not first.is_numeric
        and first.lower not in _SINGULAR_ARTICLES
        and first.lower not in _PLURAL_ARTICLES
        and first.lower not in _ARITHMETIC_OPS
        and first.lower != "si"   # already handled as if-expression
        and first.lower != "entonces"
        and first.lower != "sino"
        and len(tokens) >= 2
        and _is_arg_starter(tokens[1])
    ):
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
    if isinstance(expr, StringChars):
        # Phase 7c: `los caracteres de <str>` yields a tuple of single-char strings.
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


def _parse_comparison_condition(
    tokens: list[Token], strings: list[str]
) -> ComparisonCondition:
    """Parse an indicative comparison: `el <subject-expr> <op> <value>`.

    Phase 7a condition forms (all indicative, not subjunctive):
        - `el x es N`                     equality        → op ``"es"``
        - `el x no es N`                  inequality      → op ``"no_es"``
        - `el x es mayor que N`           strictly greater → op ``"mayor_que"``
        - `el x es menor que N`           strictly less   → op ``"menor_que"``
        - `el x es divisible por N`       divisibility    → op ``"divisible_por"``

    The subject may be a simple identifier (`el x`) OR a complex `el`-phrase
    such as a list-index (`el i-ésimo de la criba`). The parser tries
    ``_try_parse_el_phrase`` first; if it matches, the consumed tokens
    are used as the subject expression and the operator is parsed from
    what follows. If not, the classic 2-token `el <noun>` form is used.
    """
    if len(tokens) < 3:
        raise InflexionParseError(
            f"Comparison condition expects `<article> <noun> <op> <value>`; "
            f"got {[t.text for t in tokens]}"
        )
    if tokens[0].lower not in _SINGULAR_ARTICLES:
        raise InflexionParseError(
            f"Comparison condition expects a singular article; got {tokens[0].text!r}"
        )

    # Try parsing the subject as a complex el-phrase first (e.g. `el i-ésimo de la criba`).
    el_result = _try_parse_el_phrase(tokens, strings)
    if el_result is not None:
        subject_expr, subject_consumed = el_result
        rest = tokens[subject_consumed:]
        _subject_desc = f"<el-phrase>"
    else:
        # Simple form: `el <noun>` (2 tokens).
        noun = tokens[1]
        subject_expr = Identifier(noun.lower)
        rest = tokens[2:]
        _subject_desc = f"el {noun.text}"

    if not rest:
        raise InflexionParseError(
            f"Comparison condition: missing operator and value after `{_subject_desc}`."
        )

    # Dispatch on the operator form.
    head = rest[0].lower

    # `no es` — inequality.
    if head == "no" and len(rest) >= 2 and rest[1].lower == "es":
        value_tokens = rest[2:]
        if not value_tokens:
            raise InflexionParseError(
                f"`{_subject_desc} no es` is missing its comparison value."
            )
        return ComparisonCondition(
            subject=subject_expr, op="no_es", value=_parse_value(value_tokens, strings)
        )

    # `es` — various forms.
    if head == "es":
        remainder = rest[1:]  # tokens after `es`
        # `es mayor que N`
        if (
            len(remainder) >= 3
            and remainder[0].lower == "mayor"
            and remainder[1].lower == "que"
        ):
            return ComparisonCondition(
                subject=subject_expr,
                op="mayor_que",
                value=_parse_value(remainder[2:], strings),
            )
        # `es menor que N`
        if (
            len(remainder) >= 3
            and remainder[0].lower == "menor"
            and remainder[1].lower == "que"
        ):
            return ComparisonCondition(
                subject=subject_expr,
                op="menor_que",
                value=_parse_value(remainder[2:], strings),
            )
        # `es divisible por N`
        if (
            len(remainder) >= 3
            and remainder[0].lower == "divisible"
            and remainder[1].lower == "por"
        ):
            return ComparisonCondition(
                subject=subject_expr,
                op="divisible_por",
                value=_parse_value(remainder[2:], strings),
            )
        # Plain `es N` — equality.
        if not remainder:
            raise InflexionParseError(
                f"`{_subject_desc} es` is missing its comparison value."
            )
        return ComparisonCondition(
            subject=subject_expr, op="es", value=_parse_value(remainder, strings)
        )

    raise InflexionParseError(
        f"Unrecognised comparison operator after `{_subject_desc}`: "
        f"{rest[0].text!r}. Expected `es`, `no es`, `es mayor que`, "
        f"`es menor que`, or `es divisible por`."
    )


def _split_on_semicolon(tokens: list[Token]) -> list[list[Token]]:
    """Split a token list on `;` boundaries (Phase 7a Si-chain separator)."""
    parts: list[list[Token]] = []
    current: list[Token] = []
    for tok in tokens:
        if tok.text == ";":
            parts.append(current)
            current = []
        else:
            current.append(tok)
    parts.append(current)
    return parts


def _split_y_que(tokens: list[Token]) -> list[list[Token]]:
    """Split on `y que` boundaries (Phase 7a mutation-sequence separator).

    The split is conservative: only `y` immediately followed by `que`
    triggers a split. In value expressions, `y` does not appear (the
    arithmetic operators are `más`, `menos`, `por`), so this split is
    unambiguous in the mutation-body context where it is called.
    """
    segments: list[list[Token]] = []
    current: list[Token] = []
    i = 0
    while i < len(tokens):
        if (
            tokens[i].lower == "y"
            and i + 1 < len(tokens)
            and tokens[i + 1].lower == "que"
        ):
            segments.append(current)
            current = []
            i += 2  # skip `y que`
        else:
            current.append(tokens[i])
            i += 1
    segments.append(current)
    return segments


def _parse_mutation_continuation(
    tokens: list[Token], strings: list[str]
) -> MutationCommand:
    """Parse the `y que` continuation form: `el <noun> esté en <value>`.

    The leading `hacé` and `que` are absent — the first mutation in a
    sequence carries them; subsequent ones start directly with the article.
    """
    if len(tokens) < 5:
        raise InflexionParseError(
            f"`y que` continuation expects `<article> <noun> esté en <value>`; "
            f"got {[t.text for t in tokens]}"
        )
    article, noun, este, en, *value_tokens = tokens
    if article.lower not in _SINGULAR_ARTICLES:
        raise InflexionParseError(
            f"`y que` continuation expects a singular article; got {article.text!r}"
        )
    if not _is_estar_subjunctive(este):
        raise InflexionParseError(
            f"`y que` continuation expects subjunctive `esté`; got {este.text!r}"
        )
    if en.lower != "en":
        raise InflexionParseError(
            f"`y que` continuation expects `en`; got {en.text!r}"
        )
    if not value_tokens:
        raise InflexionParseError(
            f"`y que el {noun.text} esté en` is missing its value."
        )
    return MutationCommand(name=noun.lower, value=_parse_value(value_tokens, strings))


_ESIMO_CONTINUATIONS = ("ésimo", "esimo", "ésima", "esima")


def _try_parse_continuation_indexed_set(
    tokens: list[Token], strings: list[str]
) -> "ListIndexSet | None":
    """Try to parse a `y que` indexed-set continuation:
    `el i-ésimo de <list> esté en <value>`.

    This is the continuation form (without `hacé que`) of an indexed-list
    mutation. Returns a `ListIndexSet` if the tokens match, else ``None``.

    Handles the single-token ordinal (`i-ésimo`) and the spaCy-split form
    (`i`, `-`, `ésimo`).  Both numeric and variable ordinals are accepted.
    """
    if not tokens or tokens[0].lower not in _SINGULAR_ARTICLES:
        return None

    ordinal_tok = tokens[1] if len(tokens) > 1 else None
    if ordinal_tok is None:
        return None

    index_expr: "Expr"

    # --- Single-token ordinal: `5-ésimo`, `i-ésimo` ---
    m_num = _ORDINAL_RE.match(ordinal_tok.text)
    if m_num:
        index_expr = IntLit(int(m_num.group(1)))
        de_idx = 2
    elif ordinal_tok.lower in _NAMED_ORDINALS:
        index_expr = IntLit(_NAMED_ORDINALS[ordinal_tok.lower])
        de_idx = 2
    else:
        m_var = _VAR_ORDINAL_RE.match(ordinal_tok.text)
        if m_var:
            index_expr = Identifier(m_var.group(1).lower())
            de_idx = 2
        # --- Split-token ordinal: [tok, -, ésimo] ---
        elif (
            len(tokens) >= 4
            and tokens[2].text == "-"
            and tokens[3].lower in _ESIMO_CONTINUATIONS
        ):
            if ordinal_tok.is_integer_literal:
                index_expr = IntLit(int(ordinal_tok.text))
            else:
                index_expr = Identifier(ordinal_tok.lower)
            de_idx = 4
        else:
            return None

    # After ordinal: `de <article> <list-name>`
    if de_idx + 2 >= len(tokens):
        return None
    if tokens[de_idx].lower != "de":
        return None
    if tokens[de_idx + 1].lower not in {*_SINGULAR_ARTICLES, *_PLURAL_ARTICLES}:
        return None
    list_name = tokens[de_idx + 2].lower

    # Then: `esté en <value>`
    este_idx = de_idx + 3
    if este_idx + 1 >= len(tokens):
        return None
    if not _is_estar_subjunctive(tokens[este_idx]):
        return None
    if tokens[este_idx + 1].lower != "en":
        return None
    value_tokens = tokens[este_idx + 2 :]
    if not value_tokens:
        return None
    value = _parse_value(value_tokens, strings)
    return ListIndexSet(index=index_expr, list_name=list_name, value=value)


def _parse_any_mutation_segment(
    segment: list[Token], strings: list[str]
) -> "Statement":
    """Parse one full `hacé que …` segment as either an indexed-list set
    or a plain `MutationCommand`.

    The indexed-set form is tried first via `_try_parse_list_index_set`
    (which handles `hacé que el i-ésimo de el lista esté en V`). If that
    returns ``None``, the regular `_parse_mutation` path is used.
    """
    list_set = _try_parse_list_index_set(segment, strings)
    if list_set is not None:
        return list_set
    return _parse_mutation(segment, strings)


def _parse_any_continuation_segment(
    segment: list[Token], strings: list[str]
) -> "Statement":
    """Parse one `y que …` continuation segment as either an indexed-list
    set or a plain `MutationCommand`.

    The indexed-set form is tried first via
    `_try_parse_continuation_indexed_set` (handles `el i-ésimo de el lista
    esté en V`). If that returns ``None``, the regular
    `_parse_mutation_continuation` path is used.
    """
    list_set = _try_parse_continuation_indexed_set(segment, strings)
    if list_set is not None:
        return list_set
    return _parse_mutation_continuation(segment, strings)


def _parse_mutation_sequence(
    tokens: list[Token], strings: list[str]
) -> "Statement":
    """Parse `hacé que el X esté en V [y que el Y esté en W ...]`.

    Returns a single mutation Statement when there is one clause, or a
    `MutationSequence` when there are two or more `y que`-joined clauses.
    Sequential semantics: each RHS is evaluated with the current
    (post-prior-mutations) environment.

    Phase 7c: each clause may be either a plain `MutationCommand`
    (`el X esté en V`) or a `ListIndexSet` (`el i-ésimo de el lista esté
    en V`). The first segment opens with `hacé que`; subsequent segments
    start directly with `el` (the `y que` having been stripped by the
    caller).
    """
    segments = _split_y_que(tokens)
    first = _parse_any_mutation_segment(segments[0], strings)
    if len(segments) == 1:
        return first
    rest = [_parse_any_continuation_segment(seg, strings) for seg in segments[1:]]
    return MutationSequence(mutations=(first, *rest))


def _parse_body_imperative(
    tokens: list[Token], strings: list[str]
) -> "Statement":
    """Parse a single imperative for use as a `Si`-branch or loop body.

    Handles both the mutation form (`Hacé que …`) and the decir/enclitic
    forms handled by `_parse_imperative_tokens`.
    """
    if not tokens:
        raise InflexionParseError("Empty imperative body.")
    if _is_hace_imperative(tokens[0]):
        # Note: Si-branch bodies do NOT get the y-que sequence extension
        # (that is reserved for Mientras bodies per Phase 7a spec).
        return _parse_mutation(tokens, strings)
    return _parse_imperative_tokens(tokens, strings)


def _parse_si_from_parts(
    parts: list[list[Token]], strings: list[str]
) -> IfStatement:
    """Parse a Si chain from already-split (by `;`) token-list segments.

    This is the core logic for `_parse_si`. It accepts the `;`-separated
    parts directly so that `_parse_mientras_body` can filter out trailing
    `y que` segments before handing the Si-chain parts here.

    `parts[0]` must start with `si`; subsequent parts start with `sino`.
    """
    # Use tok.text.lower() (calling str.lower() on the text field) rather than
    # tok.lower (the pre-computed string field on Token) to make the intent
    # unambiguous to readers who might confuse the field name with str.lower().
    if not parts or not parts[0] or parts[0][0].text.lower() != "si":
        _got_si = parts[0][0].text if parts and parts[0] else "<empty>"
        raise InflexionParseError(  # pragma: no cover — caller filters
            f"Expected first Si part to start with `si`; got {_got_si!r}"
        )

    arms: list[tuple[ComparisonCondition, Statement]] = []
    else_body: Statement | None = None

    # --- First arm: `si COND, BODY` ---
    first_part = parts[0][1:]  # drop the leading `si`
    comma_idx = next(
        (j for j, t in enumerate(first_part) if t.text == ","), None
    )
    if comma_idx is None:
        raise InflexionParseError("`Si` branch requires `,` after condition.")
    cond_tokens = first_part[:comma_idx]
    body_tokens = first_part[comma_idx + 1 :]
    arms.append(
        (
            _parse_comparison_condition(cond_tokens, strings),
            _parse_body_imperative(body_tokens, strings),
        )
    )

    # --- Remaining parts: `sino, si COND, BODY` or `sino, BODY` ---
    for part in parts[1:]:
        if not part:
            continue
        if part[0].lower != "sino":
            raise InflexionParseError(
                f"Expected `sino` after `;` in `Si`-chain; got {part[0].text!r}"
            )
        # Expect a comma immediately after `sino`.
        if len(part) < 2 or part[1].text != ",":
            _got = repr(part[1].text) if len(part) > 1 else "'<eof>'"
            raise InflexionParseError(
                f"Expected `,` after `sino`; got {_got}"
            )
        after_sino = part[2:]  # tokens after `sino,`
        if not after_sino:
            raise InflexionParseError("`sino` has no body.")

        if after_sino[0].lower == "si":
            # elif arm: `sino, si COND, BODY`
            inner = after_sino[1:]  # drop the inner `si`
            comma_idx2 = next(
                (j for j, t in enumerate(inner) if t.text == ","), None
            )
            if comma_idx2 is None:
                raise InflexionParseError(
                    "`sino, si` branch requires `,` after condition."
                )
            cond_tokens2 = inner[:comma_idx2]
            body_tokens2 = inner[comma_idx2 + 1 :]
            arms.append(
                (
                    _parse_comparison_condition(cond_tokens2, strings),
                    _parse_body_imperative(body_tokens2, strings),
                )
            )
        else:
            # else branch: `sino, BODY`
            else_body = _parse_body_imperative(after_sino, strings)

    return IfStatement(arms=tuple(arms), else_body=else_body)


def _parse_si(sentence: list[Token], strings: list[str]) -> IfStatement:
    """Parse `Si <cond>, <body>; sino, si <cond>, <body>; sino, <body>`.

    The sentence is already split from the global token stream at `.`;
    internal `;` delimit the arms. The first token is `si`.

    Grammar summary:
        Si-stmt ::= `si` cond `,` body (`;` `sino` `,` (`si` cond `,` body | body))*
    """
    parts = _split_on_semicolon(sentence)
    return _parse_si_from_parts(parts, strings)


def _parse_mientras_body(
    tokens: list[Token], strings: list[str]
) -> "Statement":
    """Parse a `Mientras` loop body that may be:

    1. A single mutation / decir imperative (existing behaviour).
    2. A `Si` chain: `si COND, BODY; sino, …`.
    3. A compound body: `Si COND, BODY; sino, …; y que EL X esté en V` —
       a Si chain followed by one or more `y que` mutation clauses.

    The `y que` clauses are separated from the Si chain by `;`. Inside the
    `;`-split parts, `sino`-starting segments belong to the Si chain and
    `y que`-starting segments are trailing mutations. Any other segment
    after the Si chain is a parse error.

    Returns:
        - `IfStatement` when only a Si chain.
        - `BodySequence(statements=(IfStatement, mut1, mut2, …))` when
          trailing mutations are present.
        - `MutationSequence` / `MutationCommand` / imperative (existing
          paths) when the body does not start with `si`.
    """
    if not tokens:
        raise InflexionParseError("Empty `Mientras` body.")

    first = tokens[0]

    # Body starts with `si` → conditional (possibly with trailing y-que muts).
    if first.lower == "si":
        parts = _split_on_semicolon(tokens)
        si_parts: list[list[Token]] = []
        yque_tails: list[list[Token]] = []
        for part in parts:
            if not part:
                continue
            if part[0].lower in ("si", "sino"):
                si_parts.append(part)
            elif (
                part[0].lower == "y"
                and len(part) > 1
                and part[1].lower == "que"
            ):
                yque_tails.append(part[2:])  # strip `y que`
            else:
                raise InflexionParseError(
                    f"Unexpected segment after Si chain in `Mientras` body: "
                    f"{[t.text for t in part]}. Expected `sino, …` or "
                    f"`y que el <noun> esté en <value>`."
                )
        if not si_parts:
            raise InflexionParseError("`Mientras` body starts with `si` but has no Si arms.")
        if_stmt = _parse_si_from_parts(si_parts, strings)
        if not yque_tails:
            return if_stmt
        mutations = [_parse_mutation_continuation(tail, strings) for tail in yque_tails]
        return BodySequence(statements=(if_stmt, *mutations))

    # Existing paths: mutation or imperative.
    if _is_hace_imperative(first):
        return _parse_mutation_sequence(tokens, strings)
    return _parse_imperative_tokens(tokens, strings)


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
    # Phase 7a: use _parse_mientras_body so Si chains, y-que multi-clause
    # mutations, AND compound Si + y-que bodies are all accepted.
    body: Statement = _parse_mientras_body(tail, strings)
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


# Phase 6 aspect-marker dispatch. Maps the lemma of the marker verb to
# the set of operations it can drive. Phase 6 wires the canonical
# `calcular las potencias del N` form from paper §5 Example 2; future
# phases can extend the table without re-touching the parse shape.
_ASPECT_MARKER_LEMMAS = {"calcular"}
_ASPECT_OPERATIONS = {"potencia", "potencias"}


def _is_aspect_marker(tok: Token) -> bool:
    """True if `tok` is a past-tense form of a Phase-6 aspect-marker verb.

    Phase 6 recognises preterite (Tense=Past) → perfective and imperfect
    (Tense=Imp) → imperfective. Both must combine with the explicit
    aspect-marker verb lemma (currently only `calcular`) — otherwise
    a sentence starting with `Calculó` would shadow ordinary
    past-tense uses of unrelated verbs.
    """
    if tok.lemma not in _ASPECT_MARKER_LEMMAS:
        return False
    return "Tense=Past" in tok.morph or "Tense=Imp" in tok.morph


def _parse_aspect_marked(
    sentence: list[Token], strings: list[str]
) -> AspectMarkedOperation:
    """Parse `<verb-past> <plural-article> <op-noun> del <base>.` (Phase 6).

    Layout (token by token):
        0. verb form (`calculó` / `calculaba`)
        1. plural article (`las` / `los`)
        2. operation noun (`potencias`)
        3. preposition (`del`, a contraction of `de + el`)
        4. base expression (1-or-more tokens; Phase 6 supports a single
           numeric literal or articled-identifier here)

    The aspect is derived from the verb's `Tense` morphology:
    `Tense=Past` → perfective (eager); `Tense=Imp` → imperfective (lazy).
    """
    if len(sentence) < 5:
        raise InflexionParseError(
            f"Aspect-marked operation expects "
            f"`<calculó|calculaba> <art> <op> del <base>`; got "
            f"{[t.text for t in sentence]}"
        )
    verb, art, op_noun, prep, *rest = sentence
    if art.lower not in _PLURAL_ARTICLES and art.lower not in _SINGULAR_ARTICLES:
        raise InflexionParseError(
            f"Aspect-marked operation expects an article after the verb; "
            f"got {art.text!r}."
        )
    if op_noun.lemma not in _ASPECT_OPERATIONS and op_noun.lower not in _ASPECT_OPERATIONS:
        raise InflexionParseError(
            f"Phase 6 aspect-marked operations: {sorted(_ASPECT_OPERATIONS)}. "
            f"Got: {op_noun.text!r}."
        )
    if prep.lower not in ("del", "de"):
        raise InflexionParseError(
            f"Aspect-marked operation expects `del` (or `de`) before the "
            f"base; got {prep.text!r}."
        )
    # `de el N` (two tokens) would prepend an extra article to `rest`;
    # `del N` (one ADP token) leaves `rest` starting at the base. Both
    # are accepted — Spanish convention is the contraction, but the
    # explicit form is no less grammatical.
    base_tokens = rest
    if prep.lower == "de" and base_tokens and base_tokens[0].lower in _SINGULAR_ARTICLES:
        # Strip the article so `_parse_value` sees just the base token.
        base_tokens = base_tokens[1:]
    if not base_tokens:
        raise InflexionParseError(
            "Aspect-marked operation is missing its base expression."
        )
    base_expr = _parse_value(base_tokens, strings)
    if "Tense=Imp" in verb.morph:
        aspect = "imperfective"
    elif "Tense=Past" in verb.morph:
        aspect = "perfective"
    else:  # pragma: no cover - filtered by `_is_aspect_marker`
        raise InflexionParseError(
            f"Aspect-marked verb {verb.text!r} has neither perfective "
            f"nor imperfective tense morphology."
        )
    # Normalise operation name to a canonical singular ('potencias' → 'potencia').
    operation = op_noun.lemma if op_noun.lemma in _ASPECT_OPERATIONS else op_noun.lower
    if operation == "potencias":
        operation = "potencia"
    return AspectMarkedOperation(
        verb_lemma=verb.lemma,
        aspect=aspect,
        operation=operation,
        base=base_expr,
    )


def _try_parse_list_index_set(
    sentence: list[Token], strings: list[str]
) -> "ListIndexSet | None":
    """Try to parse `Hacé que el N-ésimo de <list-name> esté en <value>`.

    Returns a `ListIndexSet` when the sentence is an indexed-list mutation,
    or ``None`` when it is a regular `MutationCommand`-shaped sentence.

    Handles both the single-token ordinal form (``5-ésimo``, ``i-ésimo``) and
    the spaCy-split form (``5``, ``-``, ``ésimo`` / ``i``, ``-``, ``ésimo``),
    as well as named shortcuts (``primero``, ``segundo``). When the ordinal
    contains a variable identifier, the index is an ``Identifier`` node
    resolved at runtime.

    Phase 7c addition; variable-ordinal support added in Phase 7c fix.
    """
    # Layout (single-token ordinal):
    #   [hacé, que, el, <ordinal>, de, <art>, <list-name>, esté, en, <value…>]
    # Layout (split-token ordinal):
    #   [hacé, que, el, <ord-tok>, -, ésimo, de, <art>, <list-name>, esté, en, <value…>]
    if len(sentence) < 10:
        return None
    if not _is_hace_imperative(sentence[0]):
        return None
    if sentence[1].lower != "que":
        return None
    if sentence[2].lower not in _SINGULAR_ARTICLES:
        return None

    ordinal_tok = sentence[3]
    index_expr_set: "Expr"

    # --- Single-token ordinal forms ---
    m_num_set = _ORDINAL_RE.match(ordinal_tok.text)
    if m_num_set:
        # Numeric: `5-ésimo`
        index_expr_set = IntLit(int(m_num_set.group(1)))
        de_idx = 4
    elif ordinal_tok.lower in _NAMED_ORDINALS:
        # Named: `primero`, `segundo`
        index_expr_set = IntLit(_NAMED_ORDINALS[ordinal_tok.lower])
        de_idx = 4
    else:
        m_var_set = _VAR_ORDINAL_RE.match(ordinal_tok.text)
        if m_var_set:
            # Variable: `i-ésimo`, `puntero-ésimo`
            index_expr_set = Identifier(m_var_set.group(1).lower())
            de_idx = 4
        # --- Split-token ordinal forms: [<tok>, -, ésimo] ---
        elif (
            len(sentence) >= 11
            and sentence[4].text == "-"
            and sentence[5].lower in ("ésimo", "esimo", "ésima", "esima")
        ):
            if ordinal_tok.is_integer_literal:
                index_expr_set = IntLit(int(ordinal_tok.text))
            else:
                index_expr_set = Identifier(ordinal_tok.lower)
            de_idx = 6
        else:
            return None  # not an indexed-list mutation

    # After the ordinal: `de <article> <list-name>`
    if de_idx + 2 >= len(sentence):
        return None
    if sentence[de_idx].lower != "de":
        return None
    if sentence[de_idx + 1].lower not in {*_SINGULAR_ARTICLES, *_PLURAL_ARTICLES}:
        return None
    list_name = sentence[de_idx + 2].lower
    # Then: `esté en <value>`
    este_idx = de_idx + 3
    if este_idx + 2 >= len(sentence):
        return None
    if not _is_estar_subjunctive(sentence[este_idx]):
        return None
    if sentence[este_idx + 1].lower != "en":
        return None
    value_tokens = sentence[este_idx + 2 :]
    if not value_tokens:
        return None
    value = _parse_value(value_tokens, strings)
    return ListIndexSet(index=index_expr_set, list_name=list_name, value=value)


def _parse_escucha(sentence: list[Token], strings: list[str]) -> "Statement":
    """Parse `Escuchá una línea en el <name>` or `Escuchá un número en el <name>`.

    Phase 7c stdin binding. Returns `StdinReadLine` or `StdinReadNumber`.
    Layout: [escuchá, una/un, línea/número, en, el, <name>]
    """
    if len(sentence) < 6:
        raise InflexionParseError(
            f"Phase 7c `Escuchá` expects `Escuchá una línea en el <name>` or "
            f"`Escuchá un número en el <name>`; got {[t.text for t in sentence]}"
        )
    _esc, art, kind, en, article, name_tok = sentence[:6]
    if art.lower not in _SINGULAR_ARTICLES:
        raise InflexionParseError(
            f"`Escuchá` expects indefinite article (`una`/`un`); got {art.text!r}"
        )
    if en.lower != "en":
        raise InflexionParseError(
            f"`Escuchá … en el <name>`: expected `en`; got {en.text!r}"
        )
    if article.lower not in _SINGULAR_ARTICLES:
        raise InflexionParseError(
            f"`Escuchá … en el <name>`: expected singular article; got {article.text!r}"
        )
    kind_lower = kind.lower
    if kind_lower in {"línea", "linea"}:
        return StdinReadLine(name=name_tok.lower)
    if kind_lower in {"número", "numero"}:
        return StdinReadNumber(name=name_tok.lower)
    raise InflexionParseError(
        f"`Escuchá` expects `línea` or `número`; got {kind.text!r}"
    )


def parse(tokens: list[Token], strings: list[str]) -> Program:
    """Parse a token stream + string table into a Program."""
    statements: list[Statement] = []
    for sentence in _split_sentences(tokens):
        first = sentence[0]
        if first.lower == "si":
            # Phase 7a: conditional dispatch `Si … , … ; sino, …`
            statements.append(_parse_si(sentence, strings))
        elif first.lower == "cuando":
            statements.append(_parse_cuando(sentence, strings))
        elif first.lower == "mientras":
            statements.append(_parse_mientras(sentence, strings))
        elif _is_function_def_opening(sentence):
            # Phase 5: function definitions take precedence over the plain
            # singular-binding shape, since both open with `La …`.
            statements.append(_parse_function_def(sentence, strings))
        elif _is_aspect_marker(first):
            # Phase 6: top-level aspect-marked operation (eager preterite
            # or lazy imperfect). The lemma + tense check is strict so
            # ordinary past-tense uses of unrelated verbs are not captured.
            statements.append(_parse_aspect_marked(sentence, strings))
        elif first.lower in _PLURAL_ARTICLES:
            statements.append(_parse_plural_binding(sentence, strings))
        elif first.lower in _SINGULAR_ARTICLES:
            statements.append(_parse_singular_binding(sentence, strings))
        elif first.lower in {"escuchá", "escucha"}:
            # Phase 7c: stdin read — `Escuchá una línea en el <name>.`
            statements.append(_parse_escucha(sentence, strings))
        elif _is_hace_imperative(first):
            # Phase 7c: check for list-index-set form before regular mutation.
            list_set = _try_parse_list_index_set(sentence, strings)
            if list_set is not None:
                statements.append(list_set)
            else:
                statements.append(_parse_mutation(sentence, strings))
        else:
            statements.append(_parse_decir(sentence, strings))
    return Program(statements=tuple(statements))
