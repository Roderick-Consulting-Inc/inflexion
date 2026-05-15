# Changelog

All notable changes to the Inflexión runtime are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The runtime is pre-1.0; the API and surface syntax may change between minor versions.

## [0.0.12] — 2026-05-15

### Added — CLI stdin forwarding + two classic esolang examples

The CLI (`python -m inflexion run <file.infl>`) now forwards `sys.stdin`
to the runtime when stdin is not a TTY. Piping input through the CLI
(`echo "hola" | python -m inflexion run gato.infl`) now feeds `Escuchá`
correctly. Interactive (TTY) use is unaffected — programs that don't
read stdin still work fine.

Two new example programs, both classic esolang-wiki traditions:

- **`examples/gato.infl`** — Cat program. Reads a line from stdin and
  echoes it. Two lines: `Escuchá una línea en la entrada.` /
  `Decí la entrada.`
- **`examples/verdad.infl`** — Truth machine. If input is 0, prints
  `0` and halts; if non-zero, prints `1` until the 100,000-iteration
  `Mientras` safety cap fires (the runtime's design choice to bound
  unbounded iteration; documented in the esolang wiki entry).

### Added — esolang wiki article draft

`wiki/esolangs-org-inflexion.mediawiki` — a MediaWiki-formatted article
draft for submission to esolangs.org. Includes infobox, six-mapping
overview, five example programs (Hello World, cat, truth machine,
FizzBuzz, recursive Fibonacci, quicksort, BF-interpreter pointer),
computational class with the safety-cap caveat, lineage citations,
external resource links.

### Tests

- +5 tests across `tests/test_{gato,verdad}.py`.
- 281 → 286 passing.

## [0.0.11] — 2026-05-15

### Added — `módulo`, list operations, dynamic list literals, multi-mutation Si arms

A cluster of runtime extensions to close the named feature gaps from
v0.0.10 (true D&C sorting, expression interpreter, modulo arithmetic):

- **`módulo` / `modulo` arithmetic operator** — Spanish mathematical
  register, *siete módulo tres es uno*. Multiplicative precedence (same
  as `por` / `entre`). Modulo by zero raises `InflexionRuntimeError`.
  Enables the canonical Euclidean `gcd(a,b) = gcd(b, a mod b)`.
- **`el largo de` extended to collections** — was string-only; now
  returns the length of a list/tuple too, matching the natural Spanish
  reading.
- **`unir A y B`** — list concatenation. Spanish *unir* (to unite, to
  join). Distinct from `más` on collections (which is elementwise
  addition by Phase 4 broadcasting).
- **`los primeros N de` / `los últimos N de`** — prefix / suffix
  slicing on lists.
- **Dynamic list literals** — list literals now accept any value
  expression as elements (identifiers, arithmetic, function calls,
  indexed access), so `[la x]`, `[el primero de la xs, la y más 1]`
  parse correctly. Previously only numeric literals were allowed.
- **Multi-mutation Si-arm bodies** — Si-branch bodies (in both `Si …`
  statements and Si-inside-Mientras compound bodies) now accept the
  same `y que …` multi-clause mutation syntax as Mientras bodies. A
  single conditional arm can now carry several effects in sequence —
  natural Spanish ("si X, hacé A y que B y que C"). Required by the
  RPN calculator (each operator dispatch needs multiple stack
  mutations) and by any iterative algorithm with conditional
  multi-step state updates.
- **Negated comparisons in Si conditions** — `no es mayor que N`
  (≤) and `no es menor que N` (≥). Required to keep all of `<`, `≤`,
  `>`, `≥` available; previously only `>` and `<` were directly
  expressible.

### Added — Quicksort + RPN calculator

Two new example programs demonstrate the new primitives:

- **`quicksort.infl`** — Functional 3-way quicksort. Recursive D&C
  using `unir` + dynamic list literals (`[el idx-ésimo de la xs]`)
  + recursive predicate helpers (`pequeños` keeps elements `< pivote`;
  `grandes` keeps elements `no es menor que pivote`, so duplicates
  land on the right side). Three lines of Inflexión. Pure-functional,
  no mutation. Handles duplicates, already-sorted, reverse-sorted,
  singleton, empty.
- **`calculadora.infl`** — Postfix (RPN) calculator. Tokenizes a
  single string of single-digit operands + `+`, `-`, `*`, `/` ops
  separated by spaces, evaluates via a stack (estar-bound list with
  a `top` pointer). Demonstrates the small-DSL-interpreter pattern in
  Inflexión: char-by-char scan, dispatch on character, multi-mutation
  per operator (aux ← top; top--; stack[top] ← stack[top] OP aux).
  Default expression `"5 1 2 + 4 * + 3 -"` evaluates to 14.

### Changed — `gcd.infl` rewritten

The previous subtractive Euclidean now uses the canonical modulo form:
`gcd(a, b) = if b == 0: a else gcd(b, a mod b)`. Recursive function call
form, one line.

### Tests

- +32 tests across `tests/test_{quicksort,calculadora,runtime_extensions}.py`
  plus the `gcd` test updates.
- 249 → 281 passing.

## [0.0.10] — 2026-05-15

### Added — `entre` (division) arithmetic operator

Spanish casual register uses *entre* for division: *cuatro entre dos es
dos*. Joins *más* (+) / *menos* (−) / *por* (×) in the arithmetic
operator set. Same multiplicative precedence as *por*. Division by zero
raises `InflexionRuntimeError`.

### Added — Rosetta-comparable benchmark cluster (4 programs)

Four new example programs expand the corpus for cross-language token /
character / morpheme comparison (the empirical lever for Installment 07's
LLM-prompting cascade) and add classical recursive / iterative
demonstrations beyond the original six-mapping curriculum:

- **`gcd.infl`** — Subtractive Euclidean algorithm. Demonstrates
  conditional dispatch (Si la a es mayor que la b) inside a Mientras
  body with variable-to-variable comparison. `gcd(48, 18) = 6`.
- **`palindromo.infl`** — Recursive palindrome check via two-pointer
  descent. Demonstrates string char access, recursion, character
  comparison, and the `largo de` string-length op. Tests: *neuquen* →
  1, *hola* → 0, *abcba* → 1.
- **`pi.infl`** — Pi approximation via the Leibniz series
  (4 × (1 − 1/3 + 1/5 − 1/7 + …)). Demonstrates the new `entre`
  division operator, float arithmetic, a signed accumulator (sign flips
  via `el signo esté en 0 menos el signo`), and a long iterative
  summation. 10,000 terms gives ~4 decimal digits of π.
- **`seleccion-sort.infl`** — In-place selection sort via a recursive
  `indice_min` helper plus a 4-clause swap inside the outer Mientras
  body (aux ← list[i]; list[i] ← list[m]; list[m] ← aux; i ← i + 1).
  Demonstrates nested recursive helper + sequential y-que mutation +
  variable-indexed list set.

### Tests

- +11 program-level tests across `tests/test_{gcd,palindromo,pi,seleccion_sort}.py`.
- 249 passing (238 → 249).

## [0.0.9] — 2026-05-14

### Added — `Hablá` imperative (streaming output, no auto-newline)

Spanish distinguishes *decir* (to say — committed content, terminated
utterance) from *hablar* (to speak — ongoing activity, sound-by-sound, no
inherent termination). The runtime had mapped only the first half: `Decí`
is the sole output imperative, and it appends `\n` after every utterance.
This release adds `Hablá` as the streaming-output sibling, parallel in
every other respect.

- **Lemma:** `hablá` / `habla` join `decí` / `hacé` in the vos-imperative
  table. Both surface forms are accepted.
- **AST:** four new dataclasses parallel the Decir-family:
  `HablarCommand` (named binding), `HablarPluralCommand` (collection),
  `HablarExpr` (arbitrary expression), `HablarLiteral` (string literal).
- **Interpreter:** each new node emits its value with no trailing newline,
  the only behavioural difference from the Decir counterparts.
- **Brainfuck interpreter** (examples/brainfuck.infl) now uses `Hablá`
  for BF's `.` operator. `Hello World!` renders on a single line —
  matching the standard BF host behaviour. The trailing `\n` in the
  output comes from the BF program itself emitting chr(10), not from
  Inflexión.

### Changed — Article–noun concord + single-letter convention

Article–noun concord pass on the benchmark programs. Variables with
feminine nouns now carry feminine articles (`el cinta` → `la cinta`,
`el celda` → `la celda`, `el instruccion` → `la instruccion`). Function
parameters declared with feminine nouns now use `una` instead of `un`.

Single-letter variable names follow Spanish convention that letters of
the alphabet are feminine (*la letra i*, *la letra n*): `el i`, `el j`,
`el n`, `el a`, `el b` → `la i`, `la j`, `la n`, `la a`, `la b`.

The compiler remains silent on gender (per the §3 design choice); these
are prose-quality improvements, not semantic changes.

### Changed — Domestic-register vocabulary

Two benchmark programs renamed variables to match the everyday Argentine
register the language has been settling into:

- `examples/sieve.infl`: `la criba` → `el colador` (the kitchen
  colander). *Criba* is the academic-canonical name for the algorithm
  ("Criba de Eratóstenes") and remains correct; *colador* is what
  Spanish-speakers actually keep at home.
- `examples/brainfuck.infl`: `la cinta` → `la tira` (the strip).
  *Cinta* (tape/ribbon, the canonical Turing-machine substrate)
  remains a valid synonym; *tira* matches a more everyday register.

### Tests

- 11 tests in `tests/test_phase8_hablar.py` cover all four `Hablá`
  variants, mixed Decí/Hablá streams, BF-style char-from-code
  streaming, and the distinction-from-Decir regression.
- `tests/test_brainfuck.py` updated to expect single-line
  `Hello World!\n` output.
- 238 passing.

## [0.0.8] — 2026-05-14

### Added — Phase 7: Conditional dispatch, recursion, strings, indexed lists, stdin (commits `bb441df`, `e5d90cc`, `ee51822`)

Extends the runtime with three sub-phases spanning the final elements of the design space in paper §3:

- **Phase 7a (conditional dispatch):** Si-entonces-sino expression form. Multi-clause mientras body with y-que chaining for sequential effects. Integer string conversion and basic character output.
- **Phase 7b (recursion):** Parenthesised function-call arguments `fact (el n menos 1)` disambiguate recursive invocations. Si-entonces-sino expression (extended from 7a). Full clitic-routed argument passing (Phase 5 logged shapes; Phase 7b binds values).
- **Phase 7c (strings, collections, I/O):** String operations (length, char access, concatenation, downcase). Indexed mutable lists with `el X en índice I`. Stdin reading via `leer`. Public API adds `run_source(source, *, stdin="")` with stdin kwarg.

Five benchmark programs demonstrate the complete design:
- `fizzbuzz.infl` — Si-entonces-sino conditional dispatch with modular arithmetic (Phase 7a).
- `fibonacci-iterativo.infl` — Multi-clause mientras loop with y-que chaining (Phase 7a/b).
- `fibonacci-recursivo.infl` — Recursive factorial-style definition with parenthesised arguments (Phase 7b).
- `sieve.infl` — Indexed mutable lists and conditional loops (Phase 7c).
- `brainfuck.infl` — Brainfuck interpreter: recursion + strings + indexed lists + stdin (Phase 7a/b/c complete proof of Turing completeness from §4.3).

The Brainfuck interpreter serves as the witness for Turing-completeness promised in §4.3. Note: this initial 0.0.8 BF interpreter rendered output one character per line because `decí` appends a newline after each call. v0.0.9 closes this gap by adding `hablá` as the streaming-output sibling of `decí`, and the BF interpreter now produces standard single-line `Hello World!\n` output.

### Tests

- 206 passing (cumulative across all phases; exact final count pending test-writer's sieve + brainfuck test completion).

### Out of scope (deferred to future phases / operational-semantics installment)

- Full Unicode string operations (Phase 7c handles ASCII/Latin-1).
- Mutable-list operations beyond indexed read/write (append, slice assignment, etc. deferred).
- BF interpreter optimizations and runtime stack depth limits.

## [0.0.7] — 2026-05-13

### Added — Phase 6: diminutive / augmentative scaling + aspect-marked lazy (commit `1671465`)

Closes the six-mapping curriculum of paper §3 — the implementation phase for the present series is complete.

- Diminutive / augmentative scaling at value-position via a lookup-time fallback (no new AST node, no parser surface change in value position). Identifier resolution falls through to a suffix table when the bound name is absent; if the stripped base resolves (binding or Spanish-numeral table `cero`-`diez`), the scaled value is returned.
- Scaling factors (paper §3.5): `-ito` / `-ita` → ×½, `-illo` / `-illa` → ×¼, `-ón` / `-ona` → ×2, `-azo` / `-aza` → ×4. Integer-preserving where possible (`sumita` over 1000 → 500, not 500.0). Tuples scale element-wise.
- Diminutive function-variant invocation surfaces a clear "variant not registered" error naming the cheap / thorough convention, rather than silently dispatching.
- AspectMarkedOperation: top-level `<calculó | calculaba> <art> <op-noun> del <base>.` parses as an aspect-marked statement. `Tense=Past` → perfective (eager). `Tense=Imp` → imperfective (lazy stream, prints first six terms with `, ...`).
- Dispatch table wires `(calcular, potencia)` → powers-of-N generator; extensible without re-touching the parser.
- Aspect-marked base accepts numeric literal (`del 2`) or articled identifier (`del contador`); both `del` and explicit `de el` accepted.
- `DecirCommand` / `DecirPluralCommand` route through `_eval_expr` so the diminutive lookup fallback fires for `Decí la sumita.`.

### Tests

- 82 passing (60 baseline + 22 new: 13 in `tests/test_sumita.py`, 9 in `tests/test_potencias.py`).

### Out of scope (deferred to Phase 7 / operational semantics installment)

- Binding-target capture for aspect-marked operations (`la s es calculó las potencias del 2`).
- Diminutive-marked function variants with bodies (Phase 6 surfaces "register the variant" error rather than dispatching to an implicit rewrite).
- Less regular diminutive numeral forms (`cinquito` requires multi-step reverse-derivation; `cincón` works via the numeral table + vowel restoration).

## [0.0.6] — 2026-05-13

### Added — Phase 5: function definitions, clitic stacks, reductions (commit `c22c8d7`)

- Relative-clause function definition: `La función X, que toma <params>, es <body>.` (paper §3.4, §5 Example 3).
- Elided-body sentinel `...` for record-of-call function shape.
- Positional function call form: `<verb-infinitive> <arg> <arg> …`. Args parsed greedily until an arithmetic operator or non-arg-shaped token.
- Multi-clitic vos imperative parsing (`Dámelo`, `Dáselo`, `Transferíselo`): right-to-left longest-suffix-first stripping, capped at 3 clitics. Irregular bare-stem resolution via override table (`decí`, `hacé`); regulars resolved by `-á` / `-é` / `-í` suffix rule.
- Reduction operator: `el resultado de <op> los X` (paper §5 Example 4). Phase 5 wires `sumar`; the dispatch table is extensible.
- Lexical scope: environment gains a `parent` pointer and a root-level `functions` registry; function calls push a child scope and bind formal params as fresh *ser* cells.
- Phase 4 plural-binding RHS check extended to treat `FunctionCall` as collection-producing and `Reduction` as scalar-producing.

### Tests

- 60 passing (36 baseline + 24 new: 16 in `tests/test_funcion_descontar.py`, 8 in `tests/test_transferir.py`).

### Out of scope (deferred to Phase 6+)

- Diminutive / augmentative numeric scaling and diminutive function-variant invocation.
- Aspect-marked lazy evaluation.
- Full positional clitic-value routing (Phase 5 logs call shape rather than binding clitic argument values).
- Nested arithmetic at the function-call arg position (parenthesisation deferred).

## [0.0.5] — 2026-05-13

### Added — Phase 4: number agreement + collections + broadcasting (commit `cde49d2`)

- `por` multiplication; decimal literals.
- Scalar↔collection and collection↔collection broadcasting.
- Operator precedence: `por` > `más` / `menos`.
- Number-agreement parse errors.
- Runs `examples/precios.infl` → `[90.0, 180.0, 270.0, 360.0]`. 36 tests passing.

## [0.0.4] — 2026-05-13

### Added — Phase 3b: *Mientras* iteration + arithmetic (commit `6f02f41`)

- `Mientras` loop construct; basic arithmetic (`más`, `menos`).
- Runs `examples/contador-cuenta.infl`. 23 tests passing.

## [0.0.3] — 2026-05-12

### Added — Phase 3a: *Cuando* subjunctive deferred binding (commit `443d6ef`)

- `Cuando` subjunctive deferred-binding shape.
- Runs `examples/contador-listo.infl`. 15 tests passing.

## [0.0.2] — 2026-05-12

### Added — Phase 2: *estar* binding + imperative mutation (commit `d66f698`)

- `estar` mutable-binding semantics; imperative mutation.
- Runs `examples/contador.infl`. 8 tests passing.

## [0.0.1] — 2026-05-12

### Added — Phase 1: *ser* binding + 1-clitic vos imperative (commit `a13cb1f`)

- `ser` immutable-binding semantics; single-clitic vos imperative.
- spaCy `es_core_news_sm` morphology + custom-rule layer for irregulars.
- Runs `examples/hello-mundo.infl`. 3 tests passing.
