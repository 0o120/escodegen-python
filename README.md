# escodegen-python

Generate JavaScript from canonical [ESTree](https://github.com/estree/estree)
ASTs or native `esprima-fork` nodes. This Python port of
[escodegen](https://github.com/estools/escodegen) targets ECMAScript 2026 ASTs
and requires Python 3.11+. Runtime generation is pure Python with `esutils`;
Node and Acorn are development test oracles only.

```sh
python -m pip install "escodegen>=2,<3"
python -m pip install "escodegen[integration]>=2,<3"  # optional parser/walker
```

The 2.x release requires Python 3.11+ and `esutils` 2.x. Its integration extra
adds `esprima-fork` 5.x (imported as `esprima`) and `acornwalk` 2.x. For source
development, use sibling checkouts as described in the
[contributor instructions](https://github.com/0o120/escodegen-python/blob/master/CONTRIBUTING.md).
See the [migration notes](https://github.com/0o120/escodegen-python/blob/master/CHANGELOG.md)
for changes from 1.x.

```python
import escodegen
ast = {'type': 'BinaryExpression', 'operator': '+',
       'left': {'type': 'Literal', 'value': 20},
       'right': {'type': 'Literal', 'value': 2}}
assert escodegen.generate(ast) == '20 + 2'

import esprima  # distribution: esprima-fork
tree = esprima.parseScript('const x = 1;')
print(escodegen.generate(tree))
print(escodegen.generate(tree.toDict(), {'format': escodegen.FORMAT_MINIFY}))
```

## AST and language contract

Canonical `async`/`await` and native `isAsync`/`allowAwait` fields are accepted;
conflicts raise `ValueError`. Legacy `FieldDefinition` adapts to
`PropertyDefinition`. Nulls are retained. An attribute adapter copies inputs
without JSON conversion or mutating ASTs/options. Formatting state belongs
to each operation, including nested callbacks and concurrent generation.

Emitters cover ES5–ES2017 syntax, object rest/spread, async generators and
iteration, optional catch bindings/chains, nullish/logical assignments,
BigInt, public/private fields/methods, private brand checks, static blocks,
namespace exports, quoted module names, import/export attributes, dynamic
import options, top-level await and current regex descriptors. JSX has
element, fragment, namespace, attribute and spread-child emitters. A parser
must first validate grammar/early errors in its script/module/extension
context. TypeScript, Flow, decorators and unknown AST nodes are unsupported.
Legacy Mozilla comprehensions/guards are compatibility extensions rather
than part of the published ECMAScript target.
Resource declarations (`using`/`await using`) require
`extensions.resourceManagement=True`; they are outside the published target.

Number literals apply JavaScript binary64 rounding to Python/JSON integers.
Integers beyond the finite domain and NaN raise `ValueError`; infinity emits
`1e400` (JSON `null`). Negative values/zero are preserved with parentheses
where required. Exact integers use
`{'type':'Literal','value':None,'bigint':'9007199254740993'}` with canonical
nonnegative decimal digits; negative BigInts use UnaryExpression. Separators
and raw numeric spellings may normalize away. Regex descriptors contain JS
`pattern`/`flags` source. Flag validation rejects duplicates, unknown flags
and combined `u`/`v`; pattern grammar requires a JS-aware parser, not Python re.

For strict JSON interchange, nonfinite numbers use the small ESTree extension
`{'type':'Literal','value':None,'number':'Infinity','raw':'1e400'}` (or
`number:'-Infinity'`). This distinguishes infinity from actual `null` while
allowing `json.dumps(ast, allow_nan=False)`. Tags require a null value and
cannot conflict with BigInt/regex descriptors or raw numeric spelling.
Generation restores `1e400`/`-1e400`; JSON literal formatting emits `null`.
The serializer can also describe `number:'NaN'`, but generation retains its
explicit NaN rejection policy. Ordinary native float infinities remain supported.

## Options

Formatting options belong under `format`, including `escapeless`:

```python
code = escodegen.generate(tree, {
    'format': {'quotes': 'double', 'escapeless': True,
               'indent': {'style': '  ', 'base': 0}},
    'comment': True,
})
```

`format` keys: `indent` (`style`, `base`, `adjustMultilineComment`), `newline`,
`space`, `json`, `renumber`, `hexadecimal`, `quotes` (`single`, `double`, `auto`),
`escapeless`, `compact`, `parentheses`, `semicolons`, `safeConcatenation`,
`preserveBlankLines`. `FORMAT_DEFAULTS` and `FORMAT_MINIFY` are ready-made
format objects. `json` controls literal syntax, not AST JSON serialization.

Top-level keys: `comment`, `directive`, `raw`, `parse`, `verbatim`, `sourceCode`,
`sourceMap`, `sourceMapRoot`, `sourceMapWithCode`, `sourceContent`, `file`, plus
legacy `indent`/`base`. Raw reuse requires an equivalent literal from `parse`.
`verbatim` names an optional AST field containing a string or
`{content,precedence}` object; absent fields emit normally. Custom/verbatim
text is trusted JavaScript. Escaped strict directives retain non-strict
semantics. Inputs are not modified.

Ordinary native attribute ASTs are read directly after a compatibility check.
Custom properties, mixed mappings, alias normalization and parser callbacks
retain per-call snapshot adaptation. Both paths preserve shared references
and leave inputs unchanged. Public `SimpleObj.fromDict` always copies native
values. Identifier validation and adapter type information are cached only
within each call.

The final performance pass reduced medium native generation by 39.5% and
peak allocation by 75.9% from the modernization starting checkpoint. Mapping
generation retains its gains over the original port; native generation
remains slower than original in the measured legacy cases. See
[performance status](https://github.com/0o120/escodegen-python/blob/master/PERFORMANCE.md)
for exact revisions, workloads and limits.

Comments must be attached as `leadingComments`/`trailingComments` or block
`innerComments`; this package
does not expose upstream `attachComments`. `preserveBlankLines` requires
`sourceCode`, statement/comment `range` and comment `extendedRange` in UTF-16
units; invalid or split-surrogate ranges raise `ValueError`. `Program.hashbang`
excludes `#!`; `Line` comments with `hashbang=True` are deduplicated. Hashbangs
emit at byte zero, including compact output.

## Source maps

Source Map v3 uses Base64 VLQ and UTF-16 generated columns. Mappings describe
located node starts rather than every character; punctuation inherits node
context.

```python
tree = esprima.parseScript('const x = 1;', {'loc': True})
result = escodegen.generate(tree, {'sourceMap': 'input.js',
    'sourceMapWithCode': True, 'sourceContent': 'const x = 1;', 'file':'output.js'})
print(result.code)
print(result.map.toString())  # JSON; .toJSON() returns a mapping
```

`sourceMap=True` uses `loc.source`, falling back to `source.js`. A string uses
that filename. Without `sourceMapWithCode`, mapping returns JSON; normal
generation returns code. Sources, names, sourceRoot, file and sourcesContent
are supported. Original locations use one-based lines, zero-based UTF-16 columns.

## Tests and contributor reports

Tests use pinned Acorn 8.19.0/JSX 5.3.2, Node semantic checks and source-map
0.8.0. Coverage includes the upstream 2.1.0 corpus, every nested binary-operator
pair, Unicode/controls, directives/comments and concurrency. This is a tested
feature contract, not complete Test262 conformance.
Generation currently traverses nested expressions recursively. Very deep
ASTs can exceed Python's stack capacity and raise an actionable `ValueError`;
the exact threshold depends on the tree and interpreter recursion limit.
Generation does not change the process-wide recursion limit.

Reports by [wjsw1781 (PR #4)](https://github.com/0o120/escodegen-python/pull/4)
and [AugustineFulgur (PR #5)](https://github.com/0o120/escodegen-python/pull/5)
are regression-tested. General ECMAScript escaping supersedes the proposed
punctuation exception and Python repr replacements while preserving quote,
JSON and UTF-16 values. No PR was merged/closed automatically. Upstream BSD
copyrights and fixture notices remain preserved.

Release automation and version bumps are documented in [RELEASING.md](https://github.com/0o120/escodegen-python/blob/master/RELEASING.md).
