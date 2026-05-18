# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión lexer — Phase 4.

Strategy:
    1. Pre-process source: replace every "..."-quoted string with a placeholder
       token (Strliteral0, Strliteral1, ...) so spaCy doesn't fragment string
       contents.
    2. Tokenise the placeholdered source with spaCy's Spanish model
       (es_core_news_sm).
    3. Post-process: split a trailing ASCII `.` off any non-numeric token
       (`Y.` → `Y` + `.`). spaCy's tagger occasionally glues sentence-final
       periods onto short or uppercase identifiers, which would otherwise
       break sentence splitting in the parser. Decimal numerics like
       `0.10` are deliberately left alone — the dot is intrinsic to the
       literal there.
    4. Return a list of lightweight `Token` records and the captured string
       literal table for the parser to substitute back.

The token record carries the surface form, lowercased form, POS, lemma,
morphological feature string, and (Phase 4) a `numeric_value` field that
is set for decimal-literal tokens so the parser can build `FloatLit` /
`IntLit` without re-parsing the surface form. The Phase 4 additions are
purely additive on top of the Phase 3b lexer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

# spaCy is a hard dependency for Phase 1; if the model is missing, surface a
# clear install hint rather than a cryptic OSError.
try:
    import spacy
except ImportError as exc:  # pragma: no cover - import-time safeguard
    raise ImportError(
        "Inflexión requires spaCy. Install with `pip install spacy>=3.7`."
    ) from exc


_STRING_PATTERN = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')

# Placeholder format chosen so spaCy treats it as a single token. Underscores
# and double-underscores get split by spaCy's tokenizer; a single Latin word
# `Strliteral<N>` does not. The capitalised `S` keeps it from colliding with
# any natural Spanish vocabulary and triggers PROPN tagging consistently.
_PLACEHOLDER_PREFIX = "Strliteral"
_PLACEHOLDER_RE = re.compile(rf"^{_PLACEHOLDER_PREFIX}(\d+)$")

# A token surface is "numeric" if it parses as an int or a decimal float.
# Used by the post-process pass to decide whether to strip a trailing `.`.
_NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


@dataclass(frozen=True)
class Token:
    """A lexer token. `text` is the surface form (or string placeholder).

    ``line`` is the 1-indexed line number in the *original* source where this
    token appears. Added in 0.0.19 to support the Babel Playground's Witness
    Mode source-pane highlighter (eliminates the v0.13.4 float-literal /
    sentence-splitter heuristic in the frontend).
    """

    text: str
    lower: str
    pos: str
    lemma: str
    morph: str
    is_punct: bool
    line: int = 1

    @property
    def is_string_placeholder(self) -> bool:
        return _PLACEHOLDER_RE.match(self.text) is not None

    @property
    def placeholder_index(self) -> int:
        match = _PLACEHOLDER_RE.match(self.text)
        if match is None:
            raise ValueError(f"Not a string placeholder: {self.text!r}")
        return int(match.group(1))

    @property
    def is_numeric(self) -> bool:
        """True if the surface form parses as an int or decimal float.

        Phase 4: used by the parser to recognise `IntLit` / `FloatLit`
        without depending on spaCy's POS tag, which is unreliable on
        bare digit strings inside list literals.
        """
        return bool(_NUMERIC_RE.match(self.text))

    @property
    def is_integer_literal(self) -> bool:
        """True if the surface form is a base-10 integer (no decimal point)."""
        return self.is_numeric and "." not in self.text


@lru_cache(maxsize=1)
def _nlp():
    """Load spaCy's es_core_news_sm model. Cached for the lifetime of the process."""
    try:
        return spacy.load("es_core_news_sm")
    except OSError as exc:  # pragma: no cover - environment-dependent
        raise OSError(
            "spaCy model `es_core_news_sm` is not installed. Run:\n"
            "    python -m spacy download es_core_news_sm"
        ) from exc


def _extract_strings(source: str) -> tuple[str, list[str]]:
    """Replace each "..." literal with Strliteral<i> and return (new_source, strings)."""
    strings: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        idx = len(strings)
        # Un-escape the captured group: \" -> ", \\ -> \. Phase 1 is minimal.
        raw = match.group(1)
        unescaped = raw.replace('\\"', '"').replace("\\\\", "\\")
        strings.append(unescaped)
        # Pad with spaces so the placeholder stands alone as one spaCy token.
        return f" {_PLACEHOLDER_PREFIX}{idx} "

    return _STRING_PATTERN.sub(_replace, source), strings


def _split_trailing_period(tokens: list[Token]) -> list[Token]:
    """Split a trailing `.` off any non-numeric token.

    spaCy occasionally glues a sentence-final period onto short or
    uppercase identifiers — e.g. `Y.` arrives as one token instead of
    two. We post-process the token stream to split such cases, but
    leave decimal numerics (where the dot is intrinsic, e.g. `0.10`)
    alone. Punctuation tokens and string-literal placeholders are also
    left untouched.
    """
    out: list[Token] = []
    for tok in tokens:
        if (
            not tok.is_punct
            and not tok.is_string_placeholder
            and not _NUMERIC_RE.match(tok.text)
            and tok.text.endswith(".")
            and len(tok.text) > 1
        ):
            head_text = tok.text[:-1]
            out.append(
                Token(
                    text=head_text,
                    lower=head_text.lower(),
                    pos=tok.pos,
                    lemma=tok.lemma,
                    morph=tok.morph,
                    is_punct=False,
                    line=tok.line,
                )
            )
            out.append(
                Token(
                    text=".",
                    lower=".",
                    pos="PUNCT",
                    lemma=".",
                    morph="PunctType=Peri",
                    is_punct=True,
                    line=tok.line,
                )
            )
            continue
        out.append(tok)
    return out


def lex(source: str) -> tuple[list[Token], list[str]]:
    """Tokenise Inflexión source. Returns (tokens, string_literal_table).

    Each Token carries a ``line`` field (1-indexed) for Witness Mode source
    highlighting. Computed by counting newlines in the placeholdered source
    up to spaCy's ``tok.idx``. This works exactly when string literals don't
    span multiple lines (the convention in every bundled example); a future
    multi-line string would mis-attribute the line number by however many
    newlines the string spans. Acceptable trade-off for v0.0.19.
    """
    placeholdered, strings = _extract_strings(source)
    doc = _nlp()(placeholdered)
    tokens: list[Token] = []
    for tok in doc:
        if tok.is_space:
            continue
        line = placeholdered.count("\n", 0, tok.idx) + 1
        tokens.append(
            Token(
                text=tok.text,
                lower=tok.text.lower(),
                pos=tok.pos_,
                lemma=tok.lemma_.lower(),
                morph=str(tok.morph),
                is_punct=tok.is_punct,
                line=line,
            )
        )
    return _split_trailing_period(tokens), strings
