# Changelog

All notable changes to the Inflexión runtime are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The runtime is pre-1.0; the API and surface syntax may change between minor versions.

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
