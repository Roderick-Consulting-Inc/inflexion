# Copyright 2026 Roderick Consulting Inc. SPDX-License-Identifier: Apache-2.0
"""Inflexión AST — Phase 7 node types.

Phase 7a adds (conditional dispatch + multi-clause mientras body):
    - ComparisonCondition: indicative comparison head for `Si` branches.
      Supports `es` (==), `no es` (!=), `es mayor que` (>),
      `es menor que` (<), `es divisible por` (% == 0).
    - IfStatement: `Si <cond>, <body>; sino, si <cond>, <body>; sino, <body>`.
      Arms are tried in order; the first matching arm executes its body.
    - MutationSequence: `hacé que … y que … y que …`. A sequence of
      `MutationCommand` nodes executed sequentially. Sequential semantics:
      each mutation evaluates its RHS with the CURRENT environment, so
      prior mutations in the same sequence ARE visible to later ones.
      `y que el a esté en el b y que el b esté en el a` is therefore NOT
      an atomic swap. This matches Spanish imperative-list read order.

Phase 7b adds (recursion + if-expression):
    - IfExpression: `si <cond> entonces <then-expr> sino <else-expr>`.
      Distinct from IfStatement (statement form): the expression form
      appears in value position (function bodies, RHS of bindings).
      Uses `entonces` keyword to disambiguate from the statement form.

Phase 7c adds (string ops + indexed list + stdin):
    - StringLen, StringCharAt, CharCode, CodeToChar, StringChars:
      string operations — length, 1-indexed char-at, ord, chr,
      and string→list conversion.
    - ListIndexGet, ListIndexSet: 1-indexed get/set on estar-bound lists.
    - StdinReadLine, StdinReadNumber: bind a line (or parsed int) from stdin.

Phase 2 added:
    - BindingEstar: mutable binding via *estar* (El X está en Y)
    - MutationCommand: imperative mutation (Hacé que el X esté en Y)
    - IntLit: integer numeric literal
    - DecirCommand: vos-imperative `Decí <noun-phrase>` reading by name
      (the Phase 1 `Decilo` enclitic form remains an ImperativeCall)

Phase 3a added:
    - DeferredBinding: subjunctive deferred observer
      (`Cuando el X esté en Y, <imperative>`)

Phase 3b added:
    - BinaryOp: arithmetic (`el X más N`, `el X menos N`), with operands
      themselves drawn from `Expr` so bindings and literals can both
      appear in either slot
    - EstaCondition / NegatedCondition: subjunctive condition shapes
      (`el X esté en Y` / `el X no esté en Y`) — reused as the head
      of a `mientras` clause
    - WhileLoop: bounded iteration (`Mientras <cond>, hacé <imperative>`)

Phase 4 adds (number agreement → scalar / collection):
    - FloatLit: decimal-literal support (`0.10`, `3.14`). Distinct from
      `IntLit` so downstream consumers can keep scalar-int tests cheap.
    - ListLit: homogeneous numeric collection literal (`[100, 200, 300]`).
      Phase 4 restricts element type to int / float; strings and nested
      collections are deferred.
    - BindingSerPlural: plural ser binding (`Los X son <expr>`). Parser-
      and runtime-enforced: the RHS must evaluate to a collection, and
      `Los X son 5` is a parse error per the Phase 4 simplification of
      paper §3.6 (implicit-length scalar broadcast deferred to Phase 5+).
    - DecirPluralCommand: print a collection bound under a plural article
      (`Decí los X`). Distinct from `DecirCommand` so the singular path
      stays byte-for-byte unchanged.
    - `BinaryOp.op` is extended to accept `"por"` (multiplication).

Phase 5 adds (function abstraction + clitic argument routing + reduction):
    - FunctionDef: relative-clause function definition
      (`La función X, que toma una A, una B y un C, es <body>`). The
      body is an Expr or `None` when the source elides it with the
      sentinel `...` (paper §3.4 + §5 Example 3).
    - FunctionCall: positional call by infinitive head
      (`descontar los precios el descuento`). Args are parsed greedily
      until an arithmetic operator or non-arg-shaped token is reached.
    - CliticImperativeCall: vos-imperative carrying a stack of clitics
      (`Dámelo`, `Transferíselo`). The stack is preserved in fixed
      Spanish order. For Phase 5 the routing semantics on an
      elided-body function is a record-of-call side effect; full
      semantics will land with the ops-sem installment.
    - Reduction: fold a collection to a scalar
      (`el resultado de sumar los X`, paper §5 Example 4 line 4).

Phase 6 adds (diminutive / augmentative scaling + aspect-marked lazy):
    - AspectMarkedOperation: top-level aspect-marked verb call
      (`Calculó las potencias del N` eager, `Calculaba las potencias
      del N` lazy). Phase 6 wires the `calcular las potencias del N`
      operation; future phases will extend the dispatch table.
    - Diminutive / augmentative morphology is *not* a new AST node — it
      is a lookup-time fallback in the interpreter (an `Identifier`
      lookup that fails first tries the diminutive-base candidates;
      a `FunctionCall` to an unknown name tries the diminutive-base
      candidates before raising). Keeping it lookup-time means existing
      AST nodes and parser shapes stay unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class StringLit:
    """A string literal, e.g. "Hola, mundo"."""

    value: str


@dataclass(frozen=True)
class IntLit:
    """An integer literal, e.g. 0, 1, 100."""

    value: int


@dataclass(frozen=True)
class FloatLit:
    """A decimal literal, e.g. 0.10, 3.14. Phase 4 addition.

    Kept distinct from `IntLit` so the existing integer-only arithmetic
    paths can fast-path scalar-int cases without an isinstance(float) check.
    """

    value: float


@dataclass(frozen=True)
class Identifier:
    """A bare identifier — the noun in a binding or referent name."""

    name: str


@dataclass(frozen=True)
class ListLit:
    """A homogeneous numeric collection literal: `[100, 200, 300, 400]`.

    Phase 4 restricts element types to `IntLit` and `FloatLit`. Mixing the
    two within one literal is allowed (Python coerces under arithmetic);
    strings, identifiers, and nested collections are deferred.
    """

    elements: tuple["Expr", ...]


@dataclass(frozen=True)
class BinaryOp:
    """Numeric arithmetic on two `Expr` operands.

    Phase 3b wired `+` (*más*) and `−` (*menos*); Phase 4 adds `×` (*por*).
    Either operand may be an `Identifier`, an `IntLit` / `FloatLit`, a
    `ListLit`, or another `BinaryOp`. Scalar–collection and collection–
    collection broadcasting is handled at evaluation time (see the
    interpreter); the AST itself is shape-agnostic.
    """

    op: str  # "más", "menos", "por"
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True)
class FunctionCall:
    """Positional function call by infinitive head (Phase 5).

    Surface form: `<verb-infinitive> <arg1> <arg2> ...`, e.g.
    `descontar los precios el descuento`. The parser greedy-consumes
    arg-shaped token groups (`<article> <noun>`, numeric literal,
    bare identifier, list literal) until it hits an arithmetic
    operator, punctuation, or an unrecognised shape.

    Function lookup is by surface name (the lowered infinitive). At
    call time the interpreter pushes a child scope with the formal
    parameters bound to the evaluated argument values, evaluates the
    body, and pops the scope.
    """

    name: str
    args: tuple["Expr", ...]


@dataclass(frozen=True)
class Reduction:
    """Fold-a-collection-to-a-scalar (Phase 5, paper §5 Example 4).

    Surface form: `el resultado de <verb-infinitive> <article> <noun>`,
    where the verb names the binary operation to fold under. Phase 5
    wires `sumar` (sum); future installments can extend the dispatch
    table without re-touching the parse shape.
    """

    op: str
    target: "Expr"


Expr = Union[
    StringLit,
    IntLit,
    FloatLit,
    Identifier,
    ListLit,
    "BinaryOp",
    "FunctionCall",
    "Reduction",
    "IfExpression",   # Phase 7b
    "StringLen",      # Phase 7c
    "StringCharAt",   # Phase 7c
    "CharCode",       # Phase 7c
    "CodeToChar",     # Phase 7c
    "StringChars",    # Phase 7c
    "ListIndexGet",   # Phase 7c
]


@dataclass(frozen=True)
class BindingSer:
    """Immutable scalar binding via *ser*: `El <name> es <value>.`"""

    name: str
    value: Expr


@dataclass(frozen=True)
class BindingSerPlural:
    """Immutable plural binding via *ser*: `Los <name> son <collection-expr>.`

    Phase 4 addition. The RHS must evaluate to a collection at runtime;
    the parser rejects `Los X son <scalar-literal>` outright per the
    Phase 4 simplification of paper §3.6. Plural identifiers and
    plural-yielding arithmetic (broadcast / element-wise) are allowed
    on the RHS.
    """

    name: str
    value: Expr


@dataclass(frozen=True)
class BindingEstar:
    """Mutable binding via *estar*: `El <name> está en <value>.`

    The name is bound to a cell currently holding `value`; subsequent
    `Hacé que el <name> esté en <new_value>` mutates the cell.
    """

    name: str
    value: Expr


@dataclass(frozen=True)
class MutationCommand:
    """Imperative mutation: `Hacé que el <name> esté en <value>.`

    Vos imperative of *hacer* + subjunctive complement (*esté*). Sets the
    mutable (*estar*) binding `name` to `value`. Mutating a *ser* binding
    is a runtime error.
    """

    name: str
    value: Expr


@dataclass(frozen=True)
class DecirCommand:
    """Imperative read-and-print of a scalar: `Decí <singular-article> <noun>.`

    Phase 2 form that names its argument as a full noun phrase, as opposed
    to the Phase 1 `Decilo` form which dereferences the most-recent binding
    via the enclitic `lo`.
    """

    name: str


@dataclass(frozen=True)
class DecirPluralCommand:
    """Imperative read-and-print of a collection: `Decí los <noun>.`

    Phase 4 addition. Distinct from `DecirCommand` so the existing
    singular path is byte-for-byte unchanged; the plural form prints
    the collection using a Python-list repr (documented choice; see
    `interpreter._format_collection`).
    """

    name: str


@dataclass(frozen=True)
class DecirExpr:
    """Imperative print of an arbitrary expression: `Decí <expr>.`

    Phase 3b addition, motivated by arithmetic in print position
    (`Decí el total más 3`). The wrapped `Expr` is evaluated and the
    result printed with a trailing newline, like `DecirCommand`.
    Distinct from `DecirCommand` (Identifier-only, no arithmetic) so
    existing Phase 1+2+3a paths stay byte-for-byte unchanged.
    """

    value: "Expr"


@dataclass(frozen=True)
class DecirLiteral:
    """Imperative print of a string literal: `Decí "<text>".`

    Phase 3a addition, motivated by §5 Example 2's `decí "listo"` clause.
    Distinct from `DecirCommand` (which names a binding) and
    `ImperativeCall` (which carries an enclitic).
    """

    value: StringLit


@dataclass(frozen=True)
class HablarCommand:
    """Imperative streaming-output of a scalar: `Hablá <singular-article> <noun>.`

    Parallels `DecirCommand` but the output is written raw, with no trailing
    newline. The grammatical-semantic distinction is *decir* (to say —
    committed content, terminated utterance) vs *hablar* (to speak —
    ongoing activity, sound-by-sound, no inherent termination). Both are
    vos imperatives, both are side effects under the mood mapping; the
    verb choice selects the content-vs-activity axis.
    """

    name: str


@dataclass(frozen=True)
class HablarPluralCommand:
    """Imperative streaming-output of a collection: `Hablá los <noun>.`

    Parallel of `DecirPluralCommand`. No trailing newline; the formatted
    collection is emitted raw.
    """

    name: str


@dataclass(frozen=True)
class HablarExpr:
    """Imperative streaming-output of an arbitrary expression: `Hablá <expr>.`

    Parallel of `DecirExpr`. The wrapped `Expr` is evaluated and written
    without a trailing newline. Used by the worked Brainfuck interpreter
    (paper §4.3 Turing-completeness witness) so that BF's single-byte `.`
    operator can be expressed in Inflexión.
    """

    value: "Expr"


@dataclass(frozen=True)
class HablarLiteral:
    """Imperative streaming-output of a string literal: `Hablá "<text>".`

    Parallel of `DecirLiteral`. No trailing newline.
    """

    value: StringLit


@dataclass(frozen=True)
class ImperativeCall:
    """A vos-imperative verb (optionally with a single enclitic clitic).

    Phase 1 form — kept for `Decilo` and other single-clitic enclitic
    imperatives. `verb_lemma` is the dictionary form (e.g. "decir");
    `clitic` is one of: lo, la, le, los, las, les, me, te, se, nos, os.
    """

    verb_lemma: str
    clitic: str | None


@dataclass(frozen=True)
class FunctionDef:
    """Function definition via relative-clause (Phase 5, paper §3.4 + §5 Ex 3).

    Surface form: `La función <name>, que toma <param-list>, es <body>`,
    where `<param-list>` is a comma-and-y separated list of
    `<indef-article> <noun>` pairs (`un precio y un descuento`). The
    body is an `Expr`, OR `None` when the source uses the elision
    sentinel `...` — in which case the function may still be invoked
    (the clitic-stack imperative form prints a record-of-call line)
    but its return value is unspecified pending the ops-sem paper.
    """

    name: str
    params: tuple[str, ...]
    body: "Expr | None"


@dataclass(frozen=True)
class AspectMarkedOperation:
    """Aspect-marked top-level verb call (Phase 6, paper §3.3 + §5 Ex 2).

    Surface form: `<verb-past-tense> <plural-article> <operation-noun>
    del <base-expr>.`, where the verb's tense (preterite vs imperfect)
    selects aspect:

        - `Calculó las potencias del 2`   →  perfective, eager
        - `Calculaba las potencias del 2` →  imperfective, lazy stream

    `verb_lemma` is the dictionary form of the marker verb
    (Phase 6: `calcular`). `aspect` is one of `"perfective"` /
    `"imperfective"`. `operation` is the name of the operation invoked
    (Phase 6: `"potencias"`). `base` is the expression that parameterises
    the operation (e.g. `IntLit(2)`).

    Phase 6 semantics:
        - Imperfective form prints the first six terms of the operation
          stream followed by a truncation marker (`, ...`).
        - Perfective form computes the value eagerly but, in the
          absence of a binding-target, does *not* print — matching
          paper §5 Example 2's reading where the perfective form is
          a value-yielding action whose effect is visible elsewhere
          (e.g. via a `Cuando` observer on a related cell).
    """

    verb_lemma: str
    aspect: str
    operation: str
    base: "Expr"


@dataclass(frozen=True)
class CliticImperativeCall:
    """Vos-imperative with a clitic stack of one or more clitics (Phase 5).

    Surface form: a single token like `Dámelo`, `Dáselo`, `Transferíselo`.
    The lexer keeps it as one token; the parser strips the clitic stack
    from the right (longest-suffix-first) and records the clitics in the
    fixed Spanish order (`se` first, then 2nd/1st person, then 3rd-person
    direct). The verb stem is mapped to its dictionary infinitive via the
    explicit override table (for short / irregular forms) or by appending
    `r` to a vos-imperative stem ending in `á` / `é` / `í`.

    At interpretation time, `verb_lemma` is looked up in the function
    registry. For Phase 5, an elided-body function logs a record-of-call
    line; a defined-body function routes the clitics positionally
    (`se` → param 2, `lo` → param 3, etc.) — but Phase 5 does not yet
    bind clitic values, so it stops at logging the call shape. Full
    routing semantics are deferred to the ops-sem installment.
    """

    verb_lemma: str
    clitics: tuple[str, ...]


@dataclass(frozen=True)
class DeferredBinding:
    """Subjunctive deferred binding: `Cuando el <name> esté en <trigger>, <action>.`

    Registers a one-shot observer on the mutable cell `name`: when a
    subsequent mutation sets `name`'s value equal to `trigger_value`, the
    nested `action` (an imperative statement — `DecirCommand` or
    `ImperativeCall` in Phase 3a) fires exactly once and the observer is
    removed.

    The subjunctive *esté* is the grammatical carrier of the deferral
    (white-paper §3.2): the action is hypothetical until the trigger is
    realised, mirroring Spanish mood semantics.
    """

    name: str
    trigger_value: "Expr"
    action: "Statement"


@dataclass(frozen=True)
class EstaCondition:
    """Subjunctive equality test: `el <name> esté en <trigger_value>`.

    Phase 3b factoring of the condition-head shape that Phase 3a's
    `DeferredBinding` carried inline. Reused as the condition of a
    `mientras` loop. True iff `name`'s current value equals
    `trigger_value`.
    """

    name: str
    trigger_value: "Expr"


@dataclass(frozen=True)
class NegatedCondition:
    """Negated subjunctive equality: `el <name> no esté en <trigger_value>`.

    True iff `name`'s current value is NOT equal to `trigger_value`.
    Used as a `mientras` head — the canonical counter-loop reads
    `Mientras el contador no esté en 0, hacé …`. (Phase 3b does not
    fold negation into `Cuando`; observer-style negation is deferred.)
    """

    name: str
    trigger_value: "Expr"


Condition = Union[EstaCondition, NegatedCondition]


@dataclass(frozen=True)
class ComparisonCondition:
    """Phase 7a indicative comparison: `el <subject-expr> <op> <value>`.

    Used as the condition head of a `Si` branch — distinct from the
    subjunctive `EstaCondition` / `NegatedCondition` used by `Mientras`.

    `subject` is the left-hand-side expression. For simple variable tests
    it is an `Identifier`; for indexed-list conditions it is a
    `ListIndexGet` (or any other `Expr`).

    `op` is one of:
        ``"es"``            equality  (==)
        ``"no_es"``         inequality (!=)
        ``"mayor_que"``     strictly greater (>)
        ``"menor_que"``     strictly less (<)
        ``"divisible_por"`` divisibility (% == 0), essential for FizzBuzz
    """

    subject: "Expr"
    op: str
    value: "Expr"


@dataclass(frozen=True)
class IfStatement:
    """Phase 7a conditional dispatch: `Si … , … ; sino, …`.

    `arms` is an ordered tuple of ``(condition, body)`` pairs — the
    first arm whose condition is true executes its body; the rest are
    skipped. If no arm matches and `else_body` is not None, `else_body`
    executes. All bodies are imperative Statements (single-imperative
    convention matching the existing `mientras`-body shape).
    """

    arms: "tuple[tuple[ComparisonCondition, Statement], ...]"
    else_body: "Statement | None"


@dataclass(frozen=True)
class BodySequence:
    """Phase 7a: compound body — a Si statement followed by y-que mutations.

    Used when a `Mientras` loop body combines an `IfStatement` (the Si
    dispatch) with trailing `y que`-joined mutations (e.g. the counter
    increment in a FizzBuzz loop). The interpreter executes each statement
    in order within the same environment.

    Surface form:
        Mientras …, si el i es divisible por 3, decí "Fizz"; sino, decí el i;
                     y que el i esté en el i más 1.

    `statements` holds an ordered tuple: the first element is typically an
    `IfStatement`, followed by zero or more `MutationCommand` nodes.
    More generally, any Statement is valid.
    """

    statements: "tuple[Statement, ...]"


@dataclass(frozen=True)
class MutationSequence:
    """Phase 7a multi-clause mutation body: `hacé que … y que … y que …`.

    A non-empty sequence of `Statement` nodes executed left-to-right with
    sequential (not atomic) semantics: each mutation evaluates its RHS with
    the CURRENT environment, so prior mutations in the same sequence are
    visible to later ones. This means ``y que el a esté en el b y que el b
    esté en el a`` is *not* an atomic swap.

    Phase 7c allows indexed-list mutations (`hacé que el i-ésimo de el lista
    esté en V`) as entries in the sequence — hence the element type is the
    general ``Statement`` rather than the narrower ``MutationCommand``.
    """

    mutations: "tuple[Statement, ...]"


@dataclass(frozen=True)
class IfExpression:
    """Phase 7b if-then-else in value position: `si <cond> entonces <then> sino <else>`.

    Distinct from `IfStatement` (statement form). The `entonces` keyword
    marks the then-branch and signals to the parser that this is an
    expression, not a statement. The condition uses the same
    `ComparisonCondition` as `IfStatement`. `then_value` and
    `else_value` are arbitrary `Expr` nodes.
    """

    condition: "ComparisonCondition"
    then_value: "Expr"
    else_value: "Expr"


# --- Phase 7c string/IO nodes -------------------------------------------


@dataclass(frozen=True)
class StringLen:
    """Phase 7c: `el largo de <expr>` — string length (int)."""

    target: "Expr"


@dataclass(frozen=True)
class StringCharAt:
    """Phase 7c: `el carácter N de <expr>` — 1-indexed char-at (str)."""

    index: "Expr"
    target: "Expr"


@dataclass(frozen=True)
class CharCode:
    """Phase 7c: `el código de <expr>` — ord of single-char string (int)."""

    target: "Expr"


@dataclass(frozen=True)
class CodeToChar:
    """Phase 7c: `el carácter del código <expr>` — chr of int (str)."""

    code: "Expr"


@dataclass(frozen=True)
class StringChars:
    """Phase 7c: `los caracteres de <expr>` — list of single-char strings."""

    target: "Expr"


@dataclass(frozen=True)
class ListIndexGet:
    """Phase 7c: `el N-ésimo de <list-expr>` — 1-indexed get from list."""

    index: "Expr"
    target: "Expr"


@dataclass(frozen=True)
class ListIndexSet:
    """Phase 7c: `hacé que el N-ésimo de <list-name> esté en <value>` — 1-indexed set.

    `list_name` is the name of the estar-bound list cell to mutate.
    """

    index: "Expr"
    list_name: str
    value: "Expr"


@dataclass(frozen=True)
class StdinReadLine:
    """Phase 7c: `Escuchá una línea en el <name>.` — read a line from stdin."""

    name: str


@dataclass(frozen=True)
class StdinReadNumber:
    """Phase 7c: `Escuchá un número en el <name>.` — read an int from stdin."""

    name: str


@dataclass(frozen=True)
class WhileLoop:
    """Bounded while-loop: `Mientras <condition>, hacé <imperative>`.

    Phase 3b iteration construct. The condition is re-evaluated before
    each iteration; the body is any Phase-1/2/3a imperative statement.
    The interpreter enforces a safety cap on iteration count
    (currently 100,000) to keep runaway loops from hanging the
    interpreter — Phase 3b is intentionally not aiming for unbounded
    coinduction.
    """

    condition: "Condition"
    body: "Statement"


Statement = Union[
    BindingSer,
    BindingSerPlural,
    BindingEstar,
    MutationCommand,
    MutationSequence,      # Phase 7a
    BodySequence,          # Phase 7a (Si + y-que compound body)
    DecirCommand,
    DecirPluralCommand,
    DecirExpr,
    DecirLiteral,
    HablarCommand,
    HablarPluralCommand,
    HablarExpr,
    HablarLiteral,
    ImperativeCall,
    DeferredBinding,
    WhileLoop,
    IfStatement,           # Phase 7a
    FunctionDef,
    CliticImperativeCall,
    AspectMarkedOperation,
    ListIndexSet,          # Phase 7c
    StdinReadLine,         # Phase 7c
    StdinReadNumber,       # Phase 7c
]


@dataclass(frozen=True)
class Program:
    """An Inflexión program — an ordered list of statements."""

    statements: tuple[Statement, ...]
