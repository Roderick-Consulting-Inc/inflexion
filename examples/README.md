# Inflexión — Example Programs

Fourteen `.infl` programs covering the full grammatical-semantic mapping curriculum of the paper (§3.1–§3.6) plus the Phase 7 extensions. Programs are listed in curriculum order; the mapping columns name the paper sections each exercise.

| File | Output | Mappings demonstrated | Notes |
|------|--------|----------------------|-------|
| `hello-mundo.infl` | `Hola, mundo` | ser/estar (§3.1), imperative mood (§3.2), singular number (§3.6) | Minimal: ser-binding + single-clitic vos imperative |
| `contador.infl` | `1` | estar mutable (§3.1), imperative mutation, indicative mood (§3.2) | estar bind + hacé mutation |
| `contador-listo.infl` | `listo` | subjunctive deferred binding (§3.2), estar (§3.1) | Cuando-triggered observer |
| `contador-cuenta.infl` | `0` | Mientras loop (§3.2), negated condition, estar (§3.1) | Simple countdown loop |
| `precios.infl` | `[90.0, 180.0, 270.0, 360.0]` | plural/collection (§3.6), scalar broadcast, ser immutable (§3.1) | APL-style element-wise arithmetic |
| `funcion-descontar.infl` | `[90.0, 180.0, 270.0, 360.0]` | function definition (§3.4), clitic argument routing, plural (§3.6) | Relative-clause function + positional args |
| `sumita.infl` | `900.0` then `450.0` | diminutive scaling (§3.5), reduction, plural (§3.6) | sumita = suma × ½ |
| `transferir.infl` | transfer record | clitic stack se-lo (§3.4), imperative (§3.2) | Multi-clitic vos imperative |
| `potencias.infl` | stream | aspect eager/lazy (§3.3) | Imperfective lazy stream vs perfective eager |
| `fizzbuzz.infl` | 100 lines, 1–100 | Si conditional dispatch (Phase 7a), divisibility, Si-in-Mientras compound body | Classic FizzBuzz; Si chain + trailing y-que increment |
| `fibonacci-iterativo.infl` | `55` | multi-mutation y-que (Phase 7a), estar (§3.1), Mientras (§3.2) | F(10) via sequential-semantics swap trick: b←a+b, a←b−a |
| `fibonacci-recursivo.infl` | `55` | recursion (Phase 7b), si-entonces-sino expression (Phase 7b), ser (§3.1) | F(10) via double recursion; non-infinitive function name `fib` |
| `sieve.infl` | 15 primes ≤ 50 | variable-indexed list get+set (Phase 7c), estar mutable list, Si-in-Mientras | Eratosthenes sieve; outer loop unrolled for primes ≤ √50 |
| `brainfuck.infl` | `Hello World!` (1 char/line) | all Phase 7 features, mutual recursion, string char access, variable list index | BF interpreter running the canonical 106-char Hello-World program |

## Running an example

```bash
python -m inflexion run examples/<file>.infl
```

Or from Python:

```python
import inflexion
print(inflexion.run_file("examples/hello-mundo.infl"))
```

## Grammatical-semantic mapping legend

| Code | Paper section | Feature |
|------|--------------|---------|
| §3.1 | ser vs estar | immutable vs mutable binding |
| §3.2 | Mood | indicative (now), subjunctive (deferred), imperative (effect) |
| §3.3 | Aspect | perfective eager vs imperfective lazy |
| §3.4 | Clitic ordering | argument routing |
| §3.5 | Diminutive/augmentative | numeric and function-cost scaling |
| §3.6 | Number | scalar vs collection |
