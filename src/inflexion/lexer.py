# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión lexer — Phase 1.

Strategy:
    1. Pre-process source: replace every "..."-quoted string with a placeholder
       token (__STR0__, __STR1__, ...) so spaCy doesn't fragment string contents.
    2. Tokenise the placeholdered source with spaCy's Spanish model
       (es_core_news_sm).
    3. Return a list of lightweight `Token` records and the captured string
       literal table for the parser to substitute back.

The token record carries the surface form, lowercased form, POS, lemma, and
morphological feature string — enough for the Phase 1 parser to recognise
articles (`el`, `la`), the *ser* copula (`es`), vos-imperatives, periods, and
string-literal placeholders.
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


@dataclass(frozen=True)
class Token:
    """A lexer token. `text` is the surface form (or string placeholder)."""

    text: str
    lower: str
    pos: str
    lemma: str
    morph: str
    is_punct: bool

    @property
    def is_string_placeholder(self) -> bool:
        return _PLACEHOLDER_RE.match(self.text) is not None

    @property
    def placeholder_index(self) -> int:
        match = _PLACEHOLDER_RE.match(self.text)
        if match is None:
            raise ValueError(f"Not a string placeholder: {self.text!r}")
        return int(match.group(1))


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
    """Replace each "..." literal with __STRi__ and return (new_source, strings)."""
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


def lex(source: str) -> tuple[list[Token], list[str]]:
    """Tokenise Inflexión source. Returns (tokens, string_literal_table)."""
    placeholdered, strings = _extract_strings(source)
    doc = _nlp()(placeholdered)
    tokens: list[Token] = []
    for tok in doc:
        if tok.is_space:
            continue
        tokens.append(
            Token(
                text=tok.text,
                lower=tok.text.lower(),
                pos=tok.pos_,
                lemma=tok.lemma_.lower(),
                morph=str(tok.morph),
                is_punct=tok.is_punct,
            )
        )
    return tokens, strings
