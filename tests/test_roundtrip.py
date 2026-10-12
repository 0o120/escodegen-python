import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import unittest
from escodegen import generate, FORMAT_MINIFY


HERE = Path(__file__).resolve().parent
OWN_REFERENCE = HERE.parent / 'tools' / 'reference' / 'node_modules'
SHARED_REFERENCE = HERE.parents[1] / 'esprima-python' / 'tools' / 'reference' / 'node_modules'
REFERENCE = Path(os.environ.get('ESCODEGEN_REFERENCE_NODE_MODULES',
    str(OWN_REFERENCE if OWN_REFERENCE.exists() else SHARED_REFERENCE)))


def parse_many(jobs):
    env = dict(os.environ, ESCODEGEN_REFERENCE_NODE_MODULES=str(REFERENCE))
    process = subprocess.run(['node', str(HERE / 'reference.js')], input=json.dumps(jobs),
                             capture_output=True, text=True, encoding='utf-8', env=env)
    if process.returncode:
        raise AssertionError(process.stderr)
    return json.loads(process.stdout)


SCRIPTS = [
    'var a=1,b=2; let c=3; const d=4;',
    'function f(a=1,...b){"use strictness"; return [a,...b]}',
    'function f(){"use\\u0020strict";"later";return this}',
    'function f(){"use strict";return this}',
    'async function* f(xs){for await(const x of xs){yield await x}}',
    'const f=async x=>({x}); const g=()=>({a:1});',
    'const {a:{b=1}, ...rest}=source; const [x,,...xs]=source;',
    '({a:obj.x=1,b:obj.y,...obj.rest}=source);',
    'class C extends B {x; y=1; [key]=2; static s=3; #p=4; static #q;'
    ' #m(){return this.#p} get #v(){return this.#p} set #v(v){this.#p=v}'
    ' static {this.s++} has(o){return #p in o} async *gen(){yield this.#m()}}',
    'class C {async;static;static(){} async(){} ["x"]=1; [1]=2}',
    'try{f()}catch{g()}finally{h()}',
    'outer: for(let x in xs){if(x)continue outer;else break outer}',
    'do x++;while(x<3); with(obj){name=1}',
    'switch(x){case 1:f();break;case 2:{g();break}default:h()}',
    'if(a){if(b)f()}else g(); while(a)if(b)f();',
    'const t=tag`x${a}y${b}`; const z=`${1}`;',
    'new (factory())(); (new C).x; (new C)(); (class{}).prototype;',
    'a?.b; a?.[x]; a?.(x); a?.b?.(x); (a?.b).c; (a?.b)(x);',
    '(a?.b)`template`; new (a?.b)();',
    'x??=y; x&&=y; x||=y; obj[x]??=f();',
    'const b=900719925474099312345n; const zero=0n; const n=1_000_000;',
    'const rounded=1000000000000000100; const hex=0x20000000000001;',
    'const a=/(?<x>a)\\k<x>/dgu; const b=/[\\p{ASCII}&&\\p{Letter}]/v;',
    '(let[a])=b; (let[a])(); async;',
    r'var async; for(\u0061sync of xs); for((let[a]);;); for((let[a]) of xs);',
    'const element=<><UI.Widget title="&quot;\\&amp;" enabled {...props}>text &amp;'
    '<ns:item>{x}</ns:item>{/*comment*/}</UI.Widget></>;',
]
MODULES = [
    'import x from "m"; import * as ns from "m"; import x2,{a,b as c} from "m";',
    'import {"a b" as ab} from "m"; export {ab as "c d"};',
    'import data from "m" with {type:"json"}; import "m" with {type:"json"};',
    'export * as ns from "m"; export * as "a b" from "m";',
    'export {"a b" as "c d"} from "m" with {type:"json"}; export * from "m" with {type:"json"};',
    'export {}; export default function(){}; export const x=1;',
    'export default async function*(){yield 1};',
    'const p=import("m",{with:{type:"json"}}); import.meta.url; await p;',
]


@unittest.skipUnless(shutil.which('node') and (REFERENCE / 'acorn').exists(), 'pinned reference parser required')
class RoundtripTests(unittest.TestCase):
    def test_pinned_upstream_syntax_corpus(self):
        files = sorted(path for path in (HERE / 'upstream').rglob('*.js') if '.expected.' not in path.name)
        self.assertEqual(len(files), 37)
        legacy_invalid = json.loads((HERE / 'upstream' / 'LEGACY_INVALID.json').read_text())
        jobs = [{'source': path.read_text(encoding='utf-8'),
                 'reportError': True,
                 'module': bool(re.search(r'\b(?:import|export)\b', path.read_text(encoding='utf-8')))} for path in files]
        asts = parse_many(jobs)
        valid = []
        for path, job, ast in zip(files, jobs, asts):
            name = path.relative_to(HERE / 'upstream').as_posix()
            if name in legacy_invalid:
                self.assertIn(legacy_invalid[name], ast.get('error', ''), name)
            else:
                self.assertNotIn('error', ast, name)
                valid.append((path, job, ast))
        self.assertEqual(len(valid), 28)
        files, jobs, asts = zip(*valid)
        expected = parse_many([dict(job, normalized=True) for job in jobs])
        generated = []
        for path, ast, job in zip(files, asts, jobs):
            for options in [{}, {'format': FORMAT_MINIFY}]:
                generated.append({'source': generate(ast, options), 'module': job['module'], 'normalized': True})
        actual = parse_many(generated)
        for index, result in enumerate(actual):
            self.assertEqual(result, expected[index // 2], str(files[index // 2]))

    def test_language_and_format_matrix(self):
        original_jobs = [{'source': source, 'module': module} for module, corpus in [(False, SCRIPTS), (True, MODULES)] for source in corpus]
        original = parse_many(original_jobs)
        expected = parse_many([dict(job, normalized=True) for job in original_jobs])
        jobs, expectations = [], []
        formats = [{}, {'format': FORMAT_MINIFY}, {'format': {'quotes': 'double', 'semicolons': False}},
                   {'format': {'space': '', 'newline': ''}}, {'sourceMap': 'input.js', 'sourceMapWithCode': True},
                   {'format': {'parentheses': False, 'safeConcatenation': True}},
                   {'format': {'newline': '\r\n', 'indent': {'style': '\t', 'base': 1}}}]
        for ast, job, normalized in zip(original, original_jobs, expected):
            for options in formats:
                try:
                    generated = generate(ast, options)
                except Exception as error:
                    self.fail(job['source'] + '\n' + repr(options) + '\n' + repr(error))
                code = generated.code if options.get('sourceMap') else generated
                jobs.append({'source': code, 'module': job['module'], 'normalized': True})
                expectations.append((job['source'], options, normalized))
        actual = parse_many(jobs)
        for result, (source, options, expected) in zip(actual, expectations):
            self.assertEqual(result, expected, source + '\n' + repr(options))

    def test_every_binary_operator_nested_on_both_sides(self):
        operators = ['??', '||', '&&', '|', '^', '&', '==', '!=', '===', '!==', '<', '>', '<=', '>=',
                     'in', 'instanceof', '<<', '>>', '>>>', '+', '-', '*', '/', '%', '**']
        jobs = []
        for outer in operators:
            for inner in operators:
                jobs.extend([{'source': f'(a {inner} b) {outer} c;', 'normalized': True},
                             {'source': f'a {outer} (b {inner} c);', 'normalized': True}])
        expected = parse_many(jobs)
        original = parse_many([dict(job, normalized=False) for job in jobs])
        generated_jobs = [{'source': generate(ast, {'format': FORMAT_MINIFY}), 'normalized': True} for ast in original]
        actual = parse_many(generated_jobs)
        for before, after, job in zip(expected, actual, jobs):
            self.assertEqual(before, after, job['source'])


if __name__ == '__main__':
    unittest.main()
