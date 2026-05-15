---
title: "Inflexión: Operational Semantics"
subtitle: "Second Installment — Formal Description of the Runtime"
author:
  - Ramon Rodriguez
affiliation: RCI
date: 2026-05-15
abstract: |
  Inflexión [@rodriguez_inflexion_2026] is a Spanish-grammar esoteric programming language whose surface syntax flows from the morphological features of Rioplatense Argentine Spanish — the *ser*/*estar* split, mood, aspect, clitic ordering, diminutive and augmentative morphology, and number agreement — used as semantic primitives. The first installment described the design move, the mappings, and a hypothesis about LLM prompting density. The runtime — a Python interpreter built phase-by-phase against the design paper — shipped under build-first sequencing: code first, formal write-up afterwards. This second installment is that write-up. It describes the lexer (a spaCy + custom-rule layer for Rioplatense morphology), the grammar (a partial BNF over the surface language), the abstract machine (an environment of named cells with two binding kinds), and the evaluation rules for each of the six grammatical-semantic mappings plus the control-flow, data, and I/O extensions added between the design paper and the present version (v0.0.11). The Turing-completeness argument from the design paper's §4.3 is realised as a working Brainfuck interpreter written in Inflexión, and is briefly formalised here. The paper is intended to be readable both as a specification of what the runtime does and as an independent contribution to the question of how a programming language whose surface is natural-language prose can be given precise execution semantics.
bibliography: ../../Babel/references.bib
csl: ../../Babel/csl/chicago-author-date.csl
link-citations: true
---

> *White paper, third installment of the Babel / Inflexión series, companion to `04-whitepaper-babel.md` (Babel methodology) and `05-whitepaper-inflexion.md` (Inflexión design). Style: Chicago author-date via pandoc + BibTeX. Voice: precise for the technical audience, but the prose register stays continuous with the design paper. Citations are BibTeX keys (`[@key]`) and resolve through the shared `references.bib` in the Babel repository.*

## 1. Introduction

This paper is the formal companion to *Inflexión: A Spanish-Grammar Esoteric Language* [@rodriguez_inflexion_2026]. The design paper presents the language as a design move; this paper presents what the language actually does when it runs. The two readings are independent. A reader interested in Inflexión as a contribution to esoteric programming language design can stay with the design paper; a reader interested in implementing Inflexión, or in checking whether the design described in §3 of the design paper has a precise execution semantics, should read this one.

The sequencing of the project has been deliberate. The design paper was written first; the runtime was built second, in phases that each track one section of the design paper's §3; this paper is written third, from the runtime back to its specification. The motivation for that ordering is documented in the design paper's §10: building forces precision the prose can elide, and the rigour the formal write-up needs is supplied by working code rather than predicted from the design alone. Most of what this paper says, the implementation already enforces. A reader who wishes to verify a claim against running code is welcome to: the implementation lives in `src/inflexion/` on the public Inflexión repository, and every claim in this paper has a corresponding test in `tests/`.

The runtime described here is version `0.0.11`, the latest at time of writing. The phase numbers are an internal artefact of the project's own development sequence and are not load-bearing for the formal semantics; they are mentioned briefly in §3 only to give the reader a way to navigate the test suite. A future reader, after this paper has shipped, may treat the runtime as a single artefact without reference to the phase history.

### 1.1 What "operational semantics" means here

We follow [@plotkin_structural_2004] in taking operational semantics to be a precise description of execution as a sequence of state transitions on an abstract machine. The state is an *environment* of named cells; the abstract machine reads a parsed program (an abstract syntax tree, AST) and produces, by structural recursion over the tree, a new state plus an output stream. The transition rules are presented in big-step form (relation `(stmt, env) ⇓ (env', output)`) rather than small-step, because the runtime is implemented in Python and a big-step model maps more naturally to a recursive-descent interpreter. Small-step semantics could be derived from these by trace-decomposing each rule, but we do not present them.

The presentation style is somewhere between Plotkin-style structural rules and the prose-paragraph form of more recent practical-language specifications (e.g., the Lua reference manual [@ierusalimschy_lua_2024]). We use natural-deduction-style rules where the structure is clean (binding, evaluation, control flow); we use prose where the rule would require notation that is more verbose than the explanation it replaces (the diminutive lookup fallback, the clitic-ordering dispatch).

We do not give a denotational semantics. The runtime is not a partial function in the classical sense — *Cuando* deferred bindings create observers that fire on future state, and the imperfective aspect of an operation creates a stream that produces values on demand — both of which are awkward to denote without committing to a particular underlying domain theory. The operational form sidesteps this.

### 1.2 The shape of the rest of the paper

§2 describes the lexer — how Inflexión source text becomes a stream of tokens. This is where the dependence on Spanish morphology is most concentrated: a Rioplatense imperative verb (*decí*, *hacé*) with a stack of enclitic clitics (*decímelo*, *transferíselo*) is one token in the surface, but resolves to a (verb-lemma, clitic-stack) pair after lexing.

§3 describes the grammar — the surface forms the parser recognises and the AST nodes they produce.

§4 describes the abstract machine — the environment model, the binding kinds, the cell types.

§5 is the bulk of the paper: the evaluation rules. There is one subsection per grammatical-semantic mapping from the design paper's §3, plus one subsection each for the extensions added during runtime development. The rules in this section, taken together, are the operational semantics.

§6 sketches the Turing-completeness argument by reference to the Brainfuck interpreter that lives in the example corpus. We do not prove Turing-completeness formally; the witness is sufficient.

§7 discusses the type discipline, which is dynamic and unforgiving: every operation can fail at runtime with a specific error, and no type-check is performed before execution. §8 enumerates the error model.

§9 covers implementation notes: the Python interpreter, the spaCy morphological layer, the test corpus, the example corpus. §10 names open questions and future work.

## 2. The lexer

### 2.1 Character-level pre-processing

Inflexión source files use the `.infl` extension (resolved 2026-05-10 per the design paper's open-items). Source is UTF-8 throughout; the language depends on accented characters (*á*, *é*, *í*, *ó*, *ú*, *ñ*) and on the inverted-question-mark and inverted-exclamation-mark Spanish conventions are not currently used by the syntax but are reserved.

The lexer first identifies string literals — runs of characters enclosed in `"` double-quotes — and replaces them with placeholder tokens (`Strliteral0`, `Strliteral1`, …) keyed against a side-array `strings`. This allows the rest of the lexer to operate on a stream where every token is whitespace-separated without worrying about whether spaces are inside strings.

Numeric literals — runs of digits, optionally with a decimal point — are recognised next. Integer and floating-point literals are distinguished by the presence of the decimal point.

Punctuation tokens (`.`, `,`, `;`, `(`, `)`, `[`, `]`) are separated from adjacent identifiers by inserting spaces. The period `.` deserves a note: it is *both* a statement terminator and (potentially, in some constructs) a decimal point. The lexer treats a `.` adjacent to digits as a decimal point and a `.` followed by whitespace or end-of-input as a statement terminator.

### 2.2 Morphological dispatch

Once the source has been pre-processed into a stream of identifiers, numeric literals, string placeholders, and punctuation, each identifier is run through a morphological analyser that produces a `Token` carrying:

- `text` — the original surface form
- `lower` — the surface form lowercased
- `lemma` — the canonical dictionary form
- `pos` — part-of-speech tag
- `is_numeric` — boolean
- `is_string_placeholder` — boolean

The analyser is layered. The base layer is spaCy [@honnibal_spacy_2020] with the `es_core_news_sm` Spanish model. spaCy handles regular morphology — noun and adjective inflection, indicative-present verb conjugation, common irregular forms. Above spaCy, a custom rule layer handles the cases where spaCy's tagger is unreliable or absent for our purposes:

1. **Vos imperatives.** Rioplatense uses *vos* in the second-person singular instead of *tú*, with distinctive imperative forms (*decí*, *hacé*, *hablá*). spaCy's Spanish models are trained predominantly on peninsular Spanish and tag *decí* inconsistently. The custom layer maintains an explicit override table mapping known vos-imperative surface forms (with and without orthographic accent) to their lemmas: `decí` / `deci` → *decir*; `hacé` / `hace` → *hacer*; `hablá` / `habla` → *hablar*; `escuchá` / `escucha` → *escuchar*.

2. **Vos imperatives with enclitic clitic stacks.** Forms like *transferíselo*, *dámelo*, *decílo* (also written *decilo*) are single tokens in the surface but represent a verb plus one or more enclitic pronouns. The lexer applies a regular-expression-based stripping rule: longest-suffix-first, against the closed set of Spanish clitics `{se, te, me, le, lo, la, les, los, las, nos, os}`. After stripping, the bare stem is matched against the vos-imperative override table, and (if matched) the token is annotated with the recovered clitic stack as a tuple in fixed Spanish order: *se* (impersonal/3rd-person reflexive) before *te*/*me* (2nd/1st object) before *lo*/*la*/*les* (3rd object). The grammatical order is canonical Spanish and is documented in standard reference grammars; the lexer enforces it implicitly by attempting strippings in that order.

3. **Ordinal positional suffix.** Phase 7c introduced the construction *el N-ésimo de la lista* as a positional list reference. The suffix *-ésimo* (Spanish ordinal suffix: *cuadragésimo*, *centésimo*, *milésimo*) is a productive morpheme that combines with cardinal numbers. We extend it to combine with *any identifier whose value is currently bound to a positive integer*: *el i-ésimo de la lista* is the *i*-th element when *i* is bound, where *i* might be a single-letter variable, a multi-letter name, or any other identifier. The lexer recognises the suffix via a regex (`/.*-ésimo$/`) and produces a special token type `VariableOrdinal` carrying the prefix (the variable name) as a field; the parser handles it.

4. **Diminutive and augmentative suffixes.** Words ending in *-ito*/*-ita* (diminutive), *-ón*/*-ona*, *-azo*/*-aza* (augmentatives) and a small closed set of related forms are recognised at lookup time, not at lex time. The lexer produces these as ordinary identifiers; the diminutive resolution rule in §5.5 (numeric scaling on lookup) does the work.

### 2.3 The token type, formally

A token is a record:

```
Token = (
    text:                 str,
    lower:                str,
    lemma:                str,
    pos:                  PartOfSpeech,
    is_numeric:           bool,
    is_string_placeholder: bool,
    placeholder_index:    int | none,
    variable_ordinal:     str | none,    # the prefix when ordinal-suffixed
    clitic_stack:         (str ...) | none,
)
```

A `PartOfSpeech` is one of `{noun, verb, adjective, article, conjunction, preposition, pronoun, numeral, ordinal, punctuation, unknown}`. The lexer's responsibility is to populate this record exactly. The parser, from this point on, deals only in `Token` records.

## 3. The grammar

### 3.1 Notational conventions

We present the grammar in extended BNF: lowercase italics for non-terminals, monospace for terminal surface forms, vertical bar for alternation, square brackets for optional, asterisk for zero-or-more. We omit some auxiliary productions (whitespace handling, escape sequences in strings) where they are uninteresting and would only lengthen the presentation.

### 3.2 Programs and statements

A program is a sequence of statements:

```
program     ::= statement*
statement   ::= binding "." | mutation "." | imperative "." | control "."
binding     ::= ser-binding | estar-binding | plural-ser-binding | function-def
mutation    ::= "hacé que" mutation-sequence
imperative  ::= decir | hablar | imperative-call | clitic-imperative
control     ::= mientras | cuando | si-statement
```

Statements terminate with a `.` (period). The four classes — binding, mutation, imperative, control — are mutually exclusive in their entry shape, and the parser dispatches on the leading tokens.

### 3.3 Bindings

A `ser`-binding creates an immutable binding from a name to a value:

```
ser-binding ::= article identifier "es" value-expression
article     ::= "el" | "la" | "un" | "una"
```

The leading article is a definite or indefinite singular article; the parser treats all four as equivalent for the purpose of binding. Per the project's standing rule (design paper §3.6 footnote), the compiler is silent on gender, so *el* and *la* are interchangeable from the runtime's point of view — the choice is the writer's.

An `estar`-binding creates a mutable cell:

```
estar-binding ::= article identifier "está en" value-expression
```

The grammatical difference between `es` (third-person indicative of *ser*, "is" in the essential sense) and `está` (third-person indicative of *estar*, "is" in the situational sense) is the syntactic marker of the binding kind. The semantic difference is the design paper's §3.1.

A plural `ser`-binding creates an immutable collection:

```
plural-ser-binding ::= plural-article plural-identifier "son" list-literal
plural-article     ::= "los" | "las"
```

The plural-noun discipline is enforced by spaCy's tagger: a noun ending in *-s* (or one of the irregular plurals) is recognised as plural, and only plural nouns can be bound through *son*.

A function definition uses a relative clause to declare the parameter list:

```
function-def    ::= "La función" identifier "," "que toma" parameters "," "es" expression
parameters      ::= parameter ("," parameter)* | parameter ("y" parameter)
parameter       ::= ("un" | "una") identifier
```

The parameter-list grammar is forgiving: comma-separated, comma-and-*y* hybrid, or *y*-separated are all accepted. The relative-clause syntax (*que toma una a y una b, es ...*) is the Spanish-prose-natural form documented in the design paper's §3.4.

### 3.4 Expressions

The expression grammar is layered for operator precedence. Additive operators bind less tightly than multiplicative operators; both bind less tightly than primary expressions.

```
value-expression ::= add-expr
add-expr         ::= mult-expr (("más" | "menos") mult-expr)*
mult-expr        ::= primary (("por" | "entre" | "módulo") primary)*
primary          ::= integer-literal
                   | float-literal
                   | string-literal
                   | list-literal
                   | "(" value-expression ")"
                   | identifier-expr
                   | indexed-access
                   | function-call
                   | if-expression
                   | string-op
                   | list-op
                   | reduction
                   | stdin-read
identifier-expr  ::= article identifier
list-literal     ::= "[" (value-expression ("," value-expression)*)? "]"
```

Indexed access uses the ordinal-positional suffix:

```
indexed-access   ::= article (cardinal | variable-ordinal | named-ordinal) "de" article identifier
cardinal         ::= integer "-ésimo"
variable-ordinal ::= identifier "-ésimo"
named-ordinal    ::= "primero" | "segundo" | "tercero" | "último" | ...
```

The named ordinals (*primero*, *segundo*, …) are equivalent to *1-ésimo*, *2-ésimo*, etc.; the lexer normalises them.

Function calls are positional, with arguments separated by spaces (or by parentheses for arguments that would otherwise look like continuations):

```
function-call ::= identifier (function-arg)+
function-arg  ::= article identifier
                | integer-literal
                | float-literal
                | "(" value-expression ")"
```

The if-expression is the value-form counterpart of the if-statement:

```
if-expression ::= "si" condition ("," "entonces" | "entonces" | ";" "entonces") value-expression
                  ((";" | ",") "sino" ("si" condition ...)*)? 
                  ((";" | ",") "sino" value-expression)?
condition     ::= article identifier comparison-op value-expression
comparison-op ::= "es" | "no es" | "es mayor que" | "es menor que"
                | "no es mayor que" | "no es menor que" | "es divisible por"
```

The if-expression's punctuation is forgiving: the original strict form `si COND, entonces X; sino, Y` is accepted, as are the comma-only and bare-separator variants `si COND, entonces X, sino Y` and `si COND entonces X sino Y`. The parser locates *sino* by keyword scan and accepts whichever separators sit around it.

String and list operations are presented as their own productions:

```
string-op ::= "el largo de" value-expression
            | "el carácter" value-expression "de" value-expression
            | "el código de" value-expression
            | "el carácter del código" value-expression
            | "los caracteres de" value-expression
list-op   ::= "unir" value-expression "y" value-expression
            | "los primeros" value-expression "de" value-expression
            | "los últimos" value-expression "de" value-expression
```

*El largo de* dispatches on type: a string operand returns its character count; a list operand returns its element count.

(More of the grammar — the imperative forms, the control structures, and the reduction syntax — is presented in §5 alongside their evaluation rules, where the surface and semantics travel together.)

> *Drafted to this point — this is roughly the first eight pages of the eventual paper. Sections 4 (abstract machine), 5 (evaluation rules per mapping, the bulk of the paper), 6 (Turing completeness), 7 (type discipline), 8 (error model), 9 (implementation notes), 10 (open questions) remain. Each is a contained piece of work and can land separately.*
