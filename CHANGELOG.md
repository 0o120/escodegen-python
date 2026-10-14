# Changelog

## Unreleased

- Reduce fragment-flattening overhead and fix JSX source maps that contained
  AST objects instead of string symbol names, preventing JSON serialization.

- Add explicit extension generation for decorators, auto-accessors, source and
  deferred module phases, and default reexports, preserving native/mapping ASTs.
- Correct resource loop validation and escape ambiguous `using of` bindings
  without mutating caller nodes. Preserve async iteration/disposal independently.
- Add pinned Babel proposal comparisons and coordinated parser/walker roundtrips.

## 2.0.0 — 2026-10-13

- Generate compatible native attribute ASTs directly, preserving the public
  snapshot adapter and conservative fallback for custom behavior. Reduce
  dispatch/context/flattening costs, use verified ordinal character helpers
  with strict fallbacks, and load HTML support when JSX needs it. The final
  performance pass improves medium native generation 39.5% and peak allocation
  75.9% from the modern starting checkpoint; native original parity remains
  outstanding. See `PERFORMANCE.md` for measured limits and validation.
- Fix ECMAScript and JSON string escaping for punctuation, controls, astral
  code points and lone UTF-16 surrogates while preserving quote options.
  Regression reports credited to wjsw1781 (PR #4) and AugustineFulgur (PR #5).
  Their proposed range-specific and Python `repr` replacements are superseded
  by a general ECMAScript-aware implementation. No GitHub PR state is changed.
- Preserve escaped strict directives, return/throw/yield/postfix comment
  boundaries, dangling `else`, statement-leading `let[...]` and default imports.
- Isolate formatting state per operation and adapt mappings/native ASTs
  without JSON conversion or input mutation. Diagnose flag conflicts and
  unsupported nodes; verbatim properties are optional.
- Emit canonical async/await, BigInt, private/public classes, static blocks,
  namespace/quoted module exports, import attributes/options and JSX.
- Implement Source Map v3 with independent consumer tests and UTF-16 columns;
  validate source ranges and repair blank-line/comment preservation.
- Apply binary64 Number semantics, preserve negative zero/infinities and
  simplify verified numeric shortening. Remove Python regex validation.
- Preserve hashbangs at byte zero and upstream BSD fixture notices.
- Require Python 3.11+ and esutils 2.x; add integration extras, modern metadata,
  locked development oracles and Windows/Linux CI.
- Prepare stable PyPI metadata and absolute documentation links. The optional
  integration extra requires esprima-fork 5.x and acornwalk 2.x.

Migration from 1.x: use Python 3.11 or newer and upgrade `esutils` to 2.x.
Install `escodegen[integration]` for the coordinated parser and walker;
`esprima-fork` provides the `esprima` import. Keep formatting options under
`format`. Inputs must use documented ESTree/native fields; unsupported nodes,
conflicting async/await aliases and invalid literal metadata raise `ValueError`.
Source maps use UTF-16 columns, and source ranges must follow the same units.
