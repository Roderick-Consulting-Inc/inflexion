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

> *White paper, third installment of the Babel / Inflexión series, companion to [`04-whitepaper-babel.md`](https://github.com/Roderick-Consulting-Inc/babel/blob/main/plans/04-whitepaper-babel.md) (Babel methodology) and [`05-whitepaper-inflexion.md`](https://github.com/Roderick-Consulting-Inc/inflexion/blob/main/plans/05-whitepaper-inflexion.md) (Inflexión design). Style: Chicago author-date via pandoc + BibTeX. Voice: precise for the technical audience, but the prose register stays continuous with the design paper. Citations are BibTeX keys (`[@key]`) and resolve through the shared [`references.bib`](https://github.com/Roderick-Consulting-Inc/babel/blob/main/references.bib) in the [Babel repository](https://github.com/Roderick-Consulting-Inc/babel).*

## 1. Introduction

This paper is the formal companion to *Inflexión: A Spanish-Grammar Esoteric Language* [@rodriguez_inflexion_2026]. The design paper presents the language as a design move; this paper presents what the language actually does when it runs. The two readings are independent. A reader interested in Inflexión as a contribution to esoteric programming language design can stay with the design paper; a reader interested in implementing Inflexión, or in checking whether the design described in §3 of the design paper has a precise execution semantics, should read this one.

The sequencing of the project has been deliberate. The design paper was written first; the runtime was built second, in phases that each track one section of the design paper's §3; this paper is written third, from the runtime back to its specification. The motivation for that ordering is documented in the design paper's §10: building forces precision the prose can elide, and the rigour the formal write-up needs is supplied by working code rather than predicted from the design alone. Most of what this paper says, the implementation already enforces. A reader who wishes to verify a claim against running code is welcome to: the implementation lives in `src/inflexion/` on the public Inflexión repository, and every claim in this paper has a corresponding test in `tests/`.

The runtime described here is version `0.0.11`. The implementation has been built incrementally, but the increments are an artefact of the development process rather than load-bearing for the semantics: a reader can treat the runtime as a single artefact, and the rules below are stated against that whole.

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

Inflexión source files use the `.infl` extension. Source is UTF-8 throughout; the language depends on accented characters (*á*, *é*, *í*, *ó*, *ú*, *ñ*) and on the inverted-question-mark and inverted-exclamation-mark Spanish conventions are not currently used by the syntax but are reserved.

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

3. **Ordinal positional suffix.** The construction *el N-ésimo de la lista* serves as a positional list reference. The suffix *-ésimo* (Spanish ordinal suffix: *cuadragésimo*, *centésimo*, *milésimo*) is a productive morpheme that combines with cardinal numbers. We extend it to combine with *any identifier whose value is currently bound to a positive integer*: *el i-ésimo de la lista* is the *i*-th element when *i* is bound, where *i* might be a single-letter variable, a multi-letter name, or any other identifier. The lexer recognises the suffix via a regex (`/.*-ésimo$/`) and produces a special token type `VariableOrdinal` carrying the prefix (the variable name) as a field; the parser handles it.

4. **Diminutive and augmentative suffixes.** Words ending in *-ito*/*-ita* (diminutive), *-ón*/*-ona*, *-azo*/*-aza* (augmentatives) and a small closed set of related forms are recognised at lookup time, not at lex time. The lexer produces these as ordinary identifiers; the diminutive resolution rule in §5.7 (numeric scaling on lookup) does the work.

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

## 4. The abstract machine

### 4.1 Values

A value in Inflexión is one of:

```
Value ::= IntValue(int)
        | FloatValue(float)
        | StringValue(str)
        | CollectionValue(Value ...)         // ordered, finite
        | StreamValue(generator)              // lazy, possibly infinite
        | FunctionValue(FunctionDef)
        | DeferredValue(condition, action)    // one-shot observer
        | Unit
```

Integers and floats are unboxed Python `int` and `float` respectively; arithmetic between them follows Python's promotion rules. Strings are immutable. Collections are ordered finite sequences of values; they are heterogeneous (a single collection may mix integers, floats, and strings — see §5.6). Streams are lazy generators produced by imperfective aspect-marked operations (§5.4) and consumed on demand. Function values represent function definitions captured at definition time. Deferred values represent registered observers from *cuando* bindings (§5.9). The unit type — produced by mutations and other side-effecting statements that have no useful return — is rendered as `Unit` and is never observed by user code.

### 4.2 Cells

The environment is a mapping from names to *cells*. A cell carries a value plus a binding kind:

```
Cell  ::= (kind: BindingKind, value: Value)
BindingKind ::= Ser | Estar | PluralSer
```

A `Ser` cell is immutable: any attempt to mutate it (via *hacé que ... esté en ...*) raises a runtime error. An `Estar` cell is mutable: `Hacé que ...` rebinds its value in place. A `PluralSer` cell holds a `CollectionValue` and is treated by plural-imperative dispatch (*Decí los precios*, *Hablá los precios*) as syntactically distinct from a `Ser` cell holding the same collection — the plural article on the lookup side enforces the symmetry. The runtime does not allow re-binding *any* cell through the `ser` / `estar` / plural-ser surface forms (`El x es ...`, `La x está en ...`): a name, once bound, is owned by its first binding statement for the lifetime of the enclosing scope. Re-assignment happens through the imperative *Hacé que* form, which mutates an existing `Estar` cell but raises on `Ser` cells.

### 4.3 Environments

An environment is a stack of *scopes*, where each scope is a mapping from names to cells. The bottom of the stack is the root scope, established at program start. Function-call evaluation pushes a child scope (§5.8); function return pops it. Scope lookup walks the stack from top to bottom and returns the first matching cell.

```
Env   ::= [Scope, Scope, ...]
Scope ::= { name → Cell }
```

The environment also carries two auxiliary structures that do not fit the cell model:

- A *function registry*, populated by function-definition statements (§5.8). This is a flat namespace rather than a scoped one; function names are global within the program.
- A *deferred-observer list*, populated by *cuando* statements (§5.9). Each observer carries a trigger condition and an action to fire when the condition becomes true.

Both are global in scope — they do not nest with function calls.

### 4.4 The transition relation

The big-step relation has two shapes, one for statements and one for expressions:

```
(stmt, env) ⇓ (env', output)
(expr, env) ⇓ value
```

A statement transitions an environment to a (possibly updated) environment and emits zero or more characters of output. An expression evaluates against an environment to a value, without modifying the environment and without emitting output. The separation is enforced by the grammar: only statement-forms (mutations, imperatives, control) can emit output or modify environments; expression-forms cannot. *Functions are pure expressions.* They cannot have side effects. This is a deliberate restriction inherited from the design paper's §3.4 (functions as pure transformations) and is the reason the calculator and quicksort programs do their mutation outside function bodies.

The output stream is concatenated across the program: `output` for the program-as-a-whole is the textual concatenation of the per-statement outputs in source order.

## 5. Evaluation rules

We present the rules grouped by mapping (or by extension). Each subsection introduces the surface form, an example, and the formal rule. Auxiliary judgments are defined as they are used; we avoid forward references where possible.

### 5.1 *Ser* / *estar* binding

A `Ser` binding evaluates its right-hand side and installs an immutable cell:

```
              (expr, env) ⇓ v
─────────────────────────────────────────────  [Ser-Bind]
(El x es expr., env) ⇓ (env[x ↦ (Ser, v)], "")
```

The choice of indefinite vs definite article (*el* / *la* / *un* / *una*) is irrelevant to the rule; all four entry-shapes produce the same `Ser` cell. The plural article (*los* / *las*) requires a plural noun and a list-literal RHS:

```
              (list-expr, env) ⇓ v   v ∈ CollectionValue
──────────────────────────────────────────────────────────  [Plural-Ser-Bind]
(Los xs son list-expr., env) ⇓ (env[xs ↦ (PluralSer, v)], "")
```

An `Estar` binding installs a mutable cell:

```
                (expr, env) ⇓ v
───────────────────────────────────────────────  [Estar-Bind]
(El x está en expr., env) ⇓ (env[x ↦ (Estar, v)], "")
```

Attempting to bind a name that is already in scope is a runtime error (`InflexionRuntimeError: cannot rebind`). Re-binding must go through the *hacé que* mutation form (§5.2).

### 5.2 Mutation

Mutation requires an existing `Estar` cell. The shape is:

```
                (expr, env) ⇓ v   env[x] = (Estar, _)
─────────────────────────────────────────────────────  [Mut-Cell]
(Hacé que el x esté en expr., env) ⇓ (env[x ↦ (Estar, v)], "")
```

If `env[x]` is a `Ser` cell, the rule does not apply and the runtime raises an error. If `x` is not in scope, the runtime raises an error.

Indexed mutation, for an `Estar` cell holding a collection, has the shape:

```
   (index, env) ⇓ i   (expr, env) ⇓ v   env[xs] = (Estar, (v₁, ..., vₙ))
   1 ≤ i ≤ n
──────────────────────────────────────────────────────────────────────────  [Mut-Indexed]
(Hacé que el i-ésimo de el xs esté en expr., env) ⇓
  (env[xs ↦ (Estar, (v₁, ..., vᵢ₋₁, v, vᵢ₊₁, ..., vₙ))], "")
```

Indexing is 1-based; out-of-range indices raise an error. The cell must be `Estar`; indexed mutation of a `Ser` cell raises.

Multi-clause mutation bodies are introduced by *y que ...* continuations:

```
(mut₁, env) ⇓ (env₁, "")   (mut₂, env₁) ⇓ (env₂, "")   ...
────────────────────────────────────────────────────────────  [Mut-Seq]
(mut₁ y que mut₂ y que mut₃ ..., env) ⇓ (envₙ, "")
```

Sequential semantics: each later mutation observes the state produced by the earlier ones. This is the choice documented in the design paper's §3.4 footnote; it is the simpler model and the one Spanish-speakers tend to expect from a comma-separated sequence of imperatives.

### 5.3 Mood: indicative as immediate evaluation

The indicative mood is the eager-evaluation mode. A statement in indicative mood evaluates its right-hand-side immediately:

```
              (expr, env) ⇓ v
─────────────────────────────────────  [Mood-Indicative]
(El x es expr., env) ⇓ ([x ↦ (Ser, v)], "")
```

(This is the same rule as `[Ser-Bind]` above — we restate it here to make explicit that indicative mood is the binding shape, not a separate primitive.)

### 5.4 Mood: subjunctive as deferred evaluation

The subjunctive mood is the deferred-evaluation mode. The canonical surface is *Cuando ... esté en ..., ⟨action⟩*: the subjunctive *esté* on the condition marks the embedded clause as not-yet-asserted. The semantics is to register a one-shot observer on the named cell:

```
                  (trigger, env) ⇓ v
─────────────────────────────────────────────────────────────  [Cuando-Defer]
(Cuando el x esté en trigger, action., env) ⇓
  (env with observer (x, v, action) added, "")
```

When a subsequent mutation sets `env[x]` to the value `v`, the observer fires and the action is executed. The observer is removed after firing.

### 5.5 Mood: imperative as side effect

Imperative-mood statements perform side effects. The output-emitting imperatives are *Decí* (committed utterance, with newline) and *Hablá* (streaming, no newline); the mutation imperative is *Hacé*. The rules:

```
              (expr, env) ⇓ v
───────────────────────────────────────  [Imp-Decí]
(Decí expr., env) ⇓ (env, render(v) ++ "\n")

              (expr, env) ⇓ v
─────────────────────────────────────  [Imp-Hablá]
(Hablá expr., env) ⇓ (env, render(v))
```

`render(v)` is a value-to-string function that produces the canonical textual representation of `v` — for integers and floats their Python repr, for strings the string itself, for collections the bracketed comma-separated form. *Decí* appends a newline; *Hablá* does not. This is the only behavioural difference; the call shapes (`Decí "literal"`, `Decí el x`, `Decí los xs`, `Decí expr`) are duplicated identically for *Hablá*.

### 5.6 Number agreement

The number mapping is enforced at lookup. A singular article (*el* / *la* / *un* / *una*) on a noun phrase requires the cell at that name to hold a non-collection value; a plural article (*los* / *las*) requires a collection.

```
              env[x] = (_, v)   ¬is-collection(v)
─────────────────────────────────────────────────  [Lookup-Singular]
(el x, env) ⇓ v

              env[xs] = (_, (v₁, ..., vₙ))
─────────────────────────────────────────────────  [Lookup-Plural]
(los xs, env) ⇓ (v₁, ..., vₙ)
```

Article-noun number mismatch (*el precios* for a plural collection, *los x* for a scalar) raises a runtime error.

Arithmetic on collections broadcasts elementwise:

```
  (lhs, env) ⇓ (v₁, ..., vₙ)   (rhs, env) ⇓ (w₁, ..., wₙ)
─────────────────────────────────────────────────────────  [Broadcast-Elementwise]
(lhs op rhs, env) ⇓ (v₁ op w₁, v₂ op w₂, ..., vₙ op wₙ)

       (lhs, env) ⇓ (v₁, ..., vₙ)   (rhs, env) ⇓ s   ¬is-collection(s)
─────────────────────────────────────────────────────────────────────  [Broadcast-Scalar-Right]
(lhs op rhs, env) ⇓ (v₁ op s, v₂ op s, ..., vₙ op s)

       (lhs, env) ⇓ s   ¬is-collection(s)   (rhs, env) ⇓ (w₁, ..., wₙ)
─────────────────────────────────────────────────────────────────────  [Broadcast-Scalar-Left]
(lhs op rhs, env) ⇓ (s op w₁, s op w₂, ..., s op wₙ)
```

Two collections of unequal length raise a runtime error.

### 5.7 Diminutive and augmentative scaling

The diminutive-suffix rule fires at *lookup* of an unbound name. If the lexer produces a token `x` for which `env[x]` is undefined, the lookup rule attempts to decompose the name as `base + suffix`, where `suffix` is in a closed table of diminutive and augmentative endings, each mapped to a numeric scaling factor:

```
diminutive ↦ scale
-----------------
-ito       ↦ ½
-ita       ↦ ½
-cito      ↦ ½
-cita      ↦ ½
-ito_dim²  ↦ ¼     (e.g., "itito" — recursive diminutive)

augmentative ↦ scale
-------------------
-ón        ↦ 2
-ona       ↦ 2
-azo       ↦ 4
-aza       ↦ 4
```

(The table above is illustrative; the full set is defined in the runtime's `_DIMINUTIVE_SUFFIXES` constant.)

```
   env[x] is undefined   x = base + suffix   suffix → scale   env[base] = (_, n)   n is numeric
──────────────────────────────────────────────────────────────────────────────────────────────  [Diminutive-Scale]
(el x, env) ⇓ n × scale
```

When the lexer produces a name that has both a diminutive suffix and a function-definition match, the function-variant rule (§5.8) takes precedence over the scalar rule: *busquito* resolves to "a cheap variant of `buscar`" if `buscar` is defined as a function, and only falls through to scalar lookup if `buscar` is bound to a numeric value.

### 5.8 Functions

A function definition installs a `FunctionDef` in the function registry:

```
─────────────────────────────────────────────────────────────────────  [Function-Def]
(La función f, que toma p₁, ..., pₙ, es body., env) ⇓
  (env with registry[f] := (params=(p₁,...,pₙ), body=body), "")
```

A function call evaluates its arguments left-to-right, pushes a child scope binding the parameter names to the argument values as `Ser` cells, evaluates the body in that scope, then pops the scope:

```
       registry[f] = (params=(p₁,...,pₙ), body=body)
       (arg₁, env) ⇓ v₁   ...   (argₙ, env) ⇓ vₙ
       scope' = { p₁ ↦ (Ser, v₁), ..., pₙ ↦ (Ser, vₙ) }
       (body, env::scope') ⇓ v
────────────────────────────────────────────────────  [Function-Call]
(f arg₁ ... argₙ, env) ⇓ v
```

Functions are pure expressions. The body cannot perform side effects (no *Hacé*, no *Decí*, no *Hablá*); the parser rejects such bodies. A function's body is either an expression or an if-expression (§5.10); both are pure.

Recursion is supported via late binding: the call `f arg₁ ... argₙ` looks up `f` in the registry at *call* time, not at *definition* time, so a function body can refer to itself or to any other function defined elsewhere in the program.

Parenthesised arguments — `f (expr) (expr)` — are the disambiguation device for arguments that would otherwise be parsed as arithmetic continuations. *fact (la n menos 1)* binds the entire `la n menos 1` expression to the first argument; *fact la n menos 1* (without parens) parses as `(fact la n) menos 1` instead.

The clitic-routing surface — *Transferíselo*, *Dámelo* — applies positional argument routing through the lexer-recognised clitic stack. The clitics map to argument slots in the canonical Spanish order: *se* → indirect-object slot, *te*/*me* → second/first-person object, *lo*/*la*/*les* → third-person object. The mapping is defined in the design paper's §3.4 and not repeated formally here; we treat the resulting call as semantically equivalent to a positional call with the slots filled accordingly.

### 5.9 Control flow

The *mientras* (while) loop:

```
        (cond, env) ⇓ true    (body, env) ⇓ (env₁, o₁)
        (mientras cond, body., env₁) ⇓ (env₂, o₂)
──────────────────────────────────────────────────────────  [Mientras-Iter]
(mientras cond, body., env) ⇓ (env₂, o₁ ++ o₂)

        (cond, env) ⇓ false
─────────────────────────────────────  [Mientras-Stop]
(mientras cond, body., env) ⇓ (env, "")
```

The body of a *mientras* loop is either a single imperative or a *BodySequence* — a sequence of *y que* mutation clauses optionally prefixed by an `Si` (conditional) statement. The semantics of the *Si* prefix is the rule below; the *y que* tail evaluates left-to-right.

The *Si* (if) statement chains conditional arms:

```
   (cond₁, env) ⇓ true   (body₁, env) ⇓ (env', o)
─────────────────────────────────────────────────  [Si-First-Match]
(si cond₁, body₁; sino, si cond₂, body₂; ...; sino, else-body., env) ⇓ (env', o)

   (cond₁, env) ⇓ false   ...   (condₙ, env) ⇓ false   (else-body, env) ⇓ (env', o)
─────────────────────────────────────────────────────────────────────────────────────  [Si-Else-Match]
(si cond₁, body₁; sino, si cond₂, body₂; ...; sino, else-body., env) ⇓ (env', o)
```

If no arm matches and no *sino* (else) clause is present, the statement reduces to *(env, "")* (no-op).

The *cuando* deferred binding registers an observer (see §5.4). Observer firing happens during the *next* mutation that brings the trigger value into the cell:

```
   env[x] has observer (x, v, action)   (expr, env) ⇓ v
   (action, env[x ↦ (Estar, v)]) ⇓ (env', o)
───────────────────────────────────────────────────────────────  [Observer-Fire]
(Hacé que el x esté en expr., env) ⇓ (env' with observer removed, o)
```

If the new value `v'` does not equal the registered trigger `v`, the observer remains; the rule above does not fire.

### 5.10 The if-expression

The if-expression is the value-form companion to the if-statement. Its body is an *expression*, not a statement, and is evaluated for its value:

```
   (cond, env) ⇓ true   (then-expr, env) ⇓ v
─────────────────────────────────────────────  [IfExpr-Then]
(si cond entonces then-expr sino else-expr, env) ⇓ v

   (cond, env) ⇓ false   (else-expr, env) ⇓ v
──────────────────────────────────────────────  [IfExpr-Else]
(si cond entonces then-expr sino else-expr, env) ⇓ v
```

If-expressions chain: `sino si cond' entonces e' sino e''` is sugar for `sino (si cond' entonces e' sino e'')`. The chain terminates at a bare *sino*.

### 5.11 String operations

Strings are immutable sequences of Unicode characters. The five primitive string operations are evaluated as follows.

```
                  (s, env) ⇓ "c₁c₂...cₙ"
─────────────────────────────────────────────  [Str-Len]
(el largo de s, env) ⇓ n

       (i, env) ⇓ i   (s, env) ⇓ "c₁c₂...cₙ"   1 ≤ i ≤ n
─────────────────────────────────────────────────────────  [Str-CharAt]
(el carácter i de s, env) ⇓ "cᵢ"

       (s, env) ⇓ "c"   c is a single character
─────────────────────────────────────────────────  [Str-Code]
(el código de s, env) ⇓ unicode_codepoint(c)

       (n, env) ⇓ n   0 ≤ n ≤ 0x10FFFF
─────────────────────────────────────  [Str-FromCode]
(el carácter del código n, env) ⇓ chr(n)

                  (s, env) ⇓ "c₁c₂...cₙ"
─────────────────────────────────────────────  [Str-Chars]
(los caracteres de s, env) ⇓ ("c₁", "c₂", ..., "cₙ")
```

*El largo de* is overloaded between strings and collections: applied to a string it returns the character count; applied to a collection it returns the element count. The dispatch is on the type of the operand, not on a surface marker.

### 5.12 List operations

```
       (lhs, env) ⇓ (a₁,...,aₘ)   (rhs, env) ⇓ (b₁,...,bₙ)
───────────────────────────────────────────────────────────  [List-Concat]
(unir lhs y rhs, env) ⇓ (a₁,...,aₘ,b₁,...,bₙ)

       (n, env) ⇓ n   (xs, env) ⇓ (v₁,...,vₘ)   0 ≤ n ≤ m
─────────────────────────────────────────────────────────  [List-Prefix]
(los primeros n de xs, env) ⇓ (v₁, v₂, ..., vₙ)

       (n, env) ⇓ n   (xs, env) ⇓ (v₁,...,vₘ)   0 ≤ n ≤ m
─────────────────────────────────────────────────────────  [List-Suffix]
(los últimos n de xs, env) ⇓ (vₘ₋ₙ₊₁, ..., vₘ)

       (idx, env) ⇓ i   (xs, env) ⇓ (v₁,...,vₙ)   1 ≤ i ≤ n
─────────────────────────────────────────────────────────  [List-Index-Get]
(el i-ésimo de xs, env) ⇓ vᵢ
```

The list-mutation rule was given in §5.2. Note that all list operations except indexed mutation are *non-destructive*: they return a new list rather than modifying the operand. This matches the design paper's commitment to value-semantics for collections; mutation is reserved for indexed-set inside an explicit *Hacé que* form.

### 5.13 Aspect: eager vs lazy

The aspect mapping is the only place where the surface form selects between two distinct execution strategies. The perfective form of a reduction (*sumó*, *calculó*) is the [Reduction-Eager] rule:

```
   (xs, env) ⇓ (v₁, v₂, ..., vₙ)
─────────────────────────────────────────  [Reduction-Eager]
(sumó xs, env) ⇓ v₁ + v₂ + ... + vₙ
```

The imperfective form (*sumaba*, *calculaba*) is the [Reduction-Lazy] rule:

```
   (xs, env) ⇓ (v₁, v₂, ..., vₙ)
─────────────────────────────────────────────────  [Reduction-Lazy]
(sumaba xs, env) ⇓ Stream(v₁, v₁+v₂, ..., v₁+...+vₙ)
```

A `Stream` value is consumed lazily: rendering it via *Decí* or *Hablá* materialises it in full and emits the elements separated by commas with an ellipsis terminator (`"v₁, v₂, ..., vₙ, ..."`) to indicate the stream nature. Other operations on a `Stream` (arithmetic, indexed access) materialise as needed.

This is the only place where Inflexión performs *lazy* evaluation. Every other expression form (function bodies, indexed access, list operations) is strictly evaluated. The lazy aspect is the only opt-in, and the morpheme that selects it (*-aba* / *-ía* on the verb suffix) is the entire interface.

## 6. Turing-completeness

The design paper's §4.3 argues that *mientras* iteration combined with self-referential *ser* recursion is sufficient for Turing-completeness. We do not give a formal proof; we give a worked witness.

The example program `examples/brainfuck.infl` is an interpreter for Brainfuck written entirely in Inflexión, including bracket-matching helpers (*cierre1*, *buscar_cierre*, *apertura1*, *buscar_apertura*), an instruction-pointer dispatch loop, and a tape (*tira*) with cell-level indexed mutation. The dispatch loop uses a *Si* chain inside a *Mientras* body to switch on the current Brainfuck instruction; the bracket-matching helpers use mutual recursion and the indexed-set rule from §5.2. The interpreter runs the canonical 106-character "Hello World!" Brainfuck program through the test suite (`tests/test_brainfuck.py`) and produces the correct output, including a single trailing newline emitted by the source program itself (chr(10)) rather than by Inflexión.

Brainfuck is well-known to be Turing-complete [@mueller_brainfuck_1993]; a working interpreter establishes Inflexión as at least as expressive as Brainfuck. Combined with the design-paper §4.3 argument that the *mientras* + recursion subset is sufficient even without the rest of the language, we treat Turing-completeness as established.

## 7. Type discipline

Inflexión is *dynamically typed* with no checking before execution. Every operation can fail at runtime if its operands are of the wrong type; there is no static type checker, no type inference pass, and no type-annotation surface. The decision is driven by the project's commitment to Spanish-prose surface: Spanish-prose readers do not write or read type annotations, and adding them would dilute the contribution.

The type-check rules are stated implicitly throughout §5: arithmetic operators require numeric operands; *el carácter N de* requires a string operand and an integer index; *el i-ésimo de* requires a collection operand and an integer index; mutation requires an estar-bound cell; indexed mutation requires an estar-bound cell holding a collection; and so on. Each rule's premise that an operand "is numeric" or "is a collection" is a runtime check, and the failure mode is a runtime error (§8).

The one place where Inflexión's surface enforces a type-like discipline is *number*: a singular article on a name binds it to a non-collection value; a plural article binds it to a collection. The article-noun-number agreement is the syntactic marker of the type. This is the design paper's §3.6 mapping and the lookup rules of §5.6 above.

## 8. Error model

A runtime error in Inflexión is an instance of `InflexionRuntimeError`, raised by the interpreter and not catchable by user code (the language has no exception-handling surface). Each error carries a message identifying the rule that failed and, where possible, the surface form that triggered it.

The categories are:

1. **Lookup errors.** The name is not bound and no diminutive resolution applies. Message: "name not bound: x".
2. **Article-number mismatch.** A singular article on a plural cell, or a plural article on a singular cell.
3. **Type errors.** The operand of an operation is of the wrong type. (Examples: arithmetic on a string; *el carácter N de* on a non-string; indexed access on a non-collection.)
4. **Index errors.** Out-of-range indexed access or indexed mutation.
5. **Mutation errors.** Mutation attempted on a `Ser` cell; rebinding attempted on an already-bound name.
6. **Arity errors.** A function call with the wrong number of arguments.
7. **Division and modulo by zero.** Surfaces as a runtime error from the [Arith-Entre] and [Arith-Modulo] rules.
8. **Stream errors.** An attempt to consume a stream after its source has been mutated, or an out-of-range materialisation request.

A parse error — a syntactic violation of the grammar in §3 — is an instance of `InflexionParseError`, raised by the parser before any execution begins. Parse errors are not catchable.

## 9. Implementation notes

The interpreter is implemented in Python 3.11 in the `inflexion` package. The pipeline is:

1. `inflexion.lexer.lex(source: str)` returns a `(tokens, strings)` pair, where `tokens` is a list of `Token` records and `strings` is a side array of string-literal contents indexed by placeholder index.
2. `inflexion.parser.parse(tokens, strings)` returns a `Program` (an AST node defined in `inflexion.ast`).
3. `inflexion.interpreter.run(program, env)` executes the program against the supplied environment and returns the captured output as a string.

The public API `inflexion.run_source(source, *, stdin="")` composes these three steps, returning the captured stdout. The CLI `python -m inflexion run <file>` reads a `.infl` file, runs it, and writes the output to stdout.

The lexer uses spaCy [@honnibal_spacy_2020] with the `es_core_news_sm` Spanish model for the base morphological tagging. The custom rule layer (described in §2) is implemented in `inflexion.lexer._VOS_IMPERATIVE_LEMMAS`, `inflexion.lexer._strip_clitic_stack`, and `inflexion.lexer._VAR_ORDINAL_RE`. Future Spanish-language extensions to the lexer should follow the same pattern: extend the override table or the regex set, and add tests in `tests/`.

The test suite (`tests/`) has one file per example program and one per runtime feature group. The suite is run with `pytest tests/` and is the canonical correctness oracle: any claim in this paper that is contradicted by a test failure is wrong, and the test wins.

## 10. Open questions

The runtime as it stands is complete in the sense documented in this paper: every grammatical-semantic mapping from the design paper, plus the extensions listed in §3 and §5, has a corresponding evaluation rule and a corresponding implementation. There remain, however, a number of choices that are deliberately deferred to future installments and that this paper does not attempt to settle.

**Concurrency.** The language has no concurrency primitives. Spanish has rich morphological resources for marking habituality, reciprocity, and reflexivity, any of which could in principle map to a concurrency primitive (a reflexive verb form for self-spawning processes, for instance). We have not explored this.

**Pattern matching.** The conditional-dispatch surface in §5.9 is the *Si*-chain form, which is structurally a series of binary tests. Spanish has rich resources for nominal classification (definite vs indefinite article, masculine vs feminine, singular vs plural, animate vs inanimate, sometimes overtly marked, sometimes implicit) that could be borrowed for pattern matching on value shape. We have not designed this.

**Exception handling.** §8 notes that runtime errors are not catchable. Spanish has morphological resources for marking hypothetical / unrealized outcomes (the subjunctive, again) that could be borrowed for a *try ... if it goes wrong, do ...* surface. We have not designed this.

**A static type system.** §7 commits to dynamic typing. We are not certain this is permanent. The number-agreement enforcement (singular vs plural article on a cell) is a syntactic type-check by another name, and one could imagine extending it to (say) gender as a phantom type marker. Doing so would conflict with the standing rule that the compiler is silent on gender, so this would be a design departure, not just an extension.

**The empirical LLM-prompting study.** The design paper's §6 stated a hypothesis: that a programming language whose surface syntax mirrors a more grammatically dense natural language may be a denser substrate for LLM prompting and code generation than English-keyworded equivalents. This paper has not tested that hypothesis. A separate installment, with a measurement protocol, a controlled corpus, and a comparison against English-keyworded reference implementations, is required.

**A program corpus.** The example corpus (`examples/`) at the time of writing contains twenty programs, ranging from one-liners to the ~3000-character Brainfuck interpreter. A larger, more deliberate corpus — chosen to exercise specific evaluation rules in the most informative ways — would be useful both as a regression suite and as the input to the empirical study above.

The runtime is described; the choices remaining are design choices, not implementation gaps.

---

*Inflexión is a hand-built esoteric programming language whose semantics flow from the grammatical features of Rioplatense Argentine Spanish. The first installment (the design paper) is at <https://www.roderickc.com/inflexion>. The implementation lives at <https://github.com/Roderick-Consulting-Inc/inflexion>, and the language is catalogued on the esolangs.org wiki at <https://esolangs.org/wiki/Inflexión>. The companion methodology paper, on Babel — the runtime that generates esoteric programming languages from parameter sheets — is at <https://www.roderickc.com/babel>.*

