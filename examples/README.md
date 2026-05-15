# Inflexión — Example Programs

Eighteen `.infl` programs covering the full grammatical-semantic mapping curriculum of the paper (§3.1–§3.6), the Phase 7 / 8 extensions, and a Rosetta-comparable benchmark cluster for cross-language token-comparison studies. Programs are listed in curriculum order; the mapping columns name the paper sections each exercise.

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
| `fizzbuzz.infl` | 100 lines, 1–100 | Si conditional dispatch, divisibility, Si-in-Mientras compound body | Classic FizzBuzz; Si chain + trailing y-que increment |
| `fibonacci-iterativo.infl` | `55` | multi-mutation y-que, estar (§3.1), Mientras (§3.2) | F(10) via sequential-semantics swap trick: b←a+b, a←b−a |
| `fibonacci-recursivo.infl` | `55` | recursion, si-entonces-sino expression, ser (§3.1) | F(10) via double recursion; non-infinitive function name `fib` |
| `sieve.infl` | 15 primes ≤ 50 | variable-indexed list get+set, estar mutable list, Si-in-Mientras | Eratosthenes sieve over `el colador`; outer loop unrolled for primes ≤ √50 |
| `brainfuck.infl` | `Hello World!\n` (single line) | mutual recursion, string char access, variable list index, `hablá` streaming output | BF interpreter running the canonical 106-char Hello-World program; tape called `la tira` |
| `gcd.infl` | `6` | conditional dispatch + variable-to-variable comparison, Mientras + Si compound body | Subtractive Euclidean gcd(48, 18); we use the older subtractive form because the canonical `a − ⌊a/b⌋·b` requires modulo |
| `palindromo.infl` | `1` / `0` / `1` | string char access + recursion, if-expression chains, function args with strings | Two-pointer recursive descent; tests *neuquen* (true), *hola* (false), *abcba* (true) |
| `pi.infl` | `3.14149...` | `entre` (division), float arithmetic, signed accumulator, long iterative summation | Leibniz series, 10,000 terms ≈ π to 4 decimals |
| `seleccion-sort.infl` | `[1, 2, …, 9]` | recursive `indice_min` helper + 4-clause swap inside Mientras body via y-que | Selection sort over a 9-element list; demonstrates nested recursion + indexed mutation |

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
