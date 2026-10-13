# Performance status

The second performance pass was measured on clean source commit
`d3aa6866e4fc988c729e0c0dc5d551e8ad47b4da` (source SHA256
`fc06dde6910c15042bfbd0024c4faf089d6a8f43849dccb0c19726ed85b006f9`).
These final measurements supersede the earlier modernization checkpoint;
they do not claim parity with the original native generator.

Windows Python 3.12.0, default formatting, median milliseconds per AST:

| Workload | Original master | Modern starting checkpoint | Final |
|---|---:|---:|---:|
| Small native ES2017 | 0.323 | 1.047 | 0.707 |
| Medium native ES2017 | 17.53 | 57.28 | 34.68 |
| Native attached comments | 2.98 | 13.85 | 7.44 |
| Native ES2017 classes | 3.35 | 9.66 | 6.20 |
| Native source maps | — | 4.18 | 2.39 |
| Native modern classes | — | 15.39 | 9.39 |
| Native JSX | — | 13.64 | 7.26 |
| Varied native batch, per AST | 17.83 | 57.29 | 34.91 |
| Medium mapping ES2017 | 70.73 | 52.51 | 43.62 |
| Source-only cold import | 46.00 | 59.29 | 47.10 |

Medium native generation improved 39.5% relative to the starting checkpoint;
comments improved 46.3%, source maps 42.9%, JSX 46.8%, and varied batches 39.1%.
Medium native peak allocation fell from 2,586,960 to 623,656 bytes (75.9%);
comments fell from 990,776 to 160,352 bytes (83.8%). Mapping generation
retains its gains over original master. Tiny native generation is 0.088 ms,
about 23% above original; medium native generation remains about 1.98 times
original, with peak allocation 3.45 times original. Native baseline overhead
has therefore been reduced substantially, but has not been eliminated.

Generation now reads compatible native attribute graphs directly. It checks
raw class declarations and all fields first, and retains snapshot adaptation
for mappings, descriptors, operator overloads, class proxies, alias conversion,
hashbang normalization, verbatim data and parser callbacks. Public
`SimpleObj.fromDict` continues to copy. Shape/value validation, active child
cycle checks, UTF-16 behavior, input immutability and per-call formatting state
remain enabled. Dispatch/context overhead and duplicate statement flattening
were reduced; scalar-only metadata avoids unnecessary visited-node storage;
HTML support loads when JSX needs it. Optional private utility helpers are
used only for code points produced by `ord`, with public predicate fallbacks.

The residual cost includes compatibility traversal, live node validation and
cycle checks absent from the unchecked original. A lazy native-view prototype
was slower. Moving shape checks into preflight and retaining identity proofs
was approximately neutral and increased allocation, so it was discarded.
These are measured tradeoffs; the remaining gap is not asserted to be
irreducible. Source maps and modern classes/JSX have no original comparison
because the original does not implement their tested feature contract.

The harness compares original master `a396adbc`, modern starting generator
`84f94b9`, and final source. Starting utilities are `6e32e20`; final utilities
are `1e85352`. AST construction is pinned separately and excluded from timing.
Old-compatible cases use identical legacy native ASTs or legacy-field
mappings; modern cases use pinned parser `618be2b`. Workers are fresh isolated
processes, generation is warmed, version order alternates, and all adaptation,
validation and emission work is timed. Allocation measures one warmed call
with ASTs already built. Cold import uses source-only compilation. Fixtures
are parsed for semantic comparison and are never executed by this harness.

The final 20-case timing matrix passes 54 independent Acorn comparisons, and
all current code/source-map outputs equal the modern starting outputs. A
separate 48-case semantic probe matrix also passes. All 71 generator methods
and seven native parser/generator pipeline methods pass with warnings as
errors. Descriptor binding, spoofed function metadata, mapping class proxies,
custom truthiness/equality, shared graphs, callbacks and concurrency have
focused regressions.

Reproducible scripts, snapshots, profiles and raw measurements are in the
the development workspace outside this repository at
`implementation-artifacts/performance-round2/generator/`; the final matrix is
`final.json`. They are not included in the public source archive or wheel.
Measurements describe these workloads and this machine; interpreter, AST
representation and application options affect the results. Current release
checks and publishing instructions are documented in [RELEASING.md](RELEASING.md).
