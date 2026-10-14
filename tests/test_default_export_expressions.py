"""Default-export expressions must retain expression binding/hoisting rules."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

import escodegen
try:
    import esprima
except ImportError:
    esprima = None


HERE = Path(__file__).resolve().parent
OWN_REFERENCE = HERE.parent / 'tools/reference/node_modules'
SHARED_REFERENCE = HERE.parents[1] / 'esprima-python/tools/reference/node_modules'
REFERENCE = Path(os.environ.get('ESCODEGEN_REFERENCE_NODE_MODULES',
    str(OWN_REFERENCE if OWN_REFERENCE.exists() else SHARED_REFERENCE)))
EXPRESSIONS = ('function(){}', 'function Hidden(){}', 'function* Hidden(){}',
               'async function Hidden(){}', 'async function* Hidden(){}',
               'class {}', 'class Hidden {}')


def normalized(value):
    if isinstance(value, list):
        return [normalized(item) for item in value]
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items()
                if key not in ('loc', 'range', 'raw', 'comments', 'leadingComments',
                               'trailingComments', 'innerComments')}
    return value


@unittest.skipUnless(esprima is not None, 'optional coordinated parser required')
class DefaultExportExpressionTests(unittest.TestCase):
    def test_native_and_mapping_expression_roundtrips(self):
        formats = ({}, {'format': escodegen.FORMAT_MINIFY},
                   {'format': {'parentheses': False, 'semicolons': False}},
                   {'sourceMap': 'input.mjs', 'sourceMapWithCode': True})
        for expression in EXPRESSIONS:
            for suffix in ('', '()', '.name', '?.name', ' ? 1 : 2', '`tag`'):
                source = 'export default (' + expression + ')' + suffix + ';'
                original = esprima.parseModule(source, range=True, loc=True)
                mapping = original.toDict()
                expected = normalized(mapping)
                for options in formats:
                    for tree in (original, mapping):
                        with self.subTest(source=source, options=options, native=tree is original):
                            result = escodegen.generate(tree, options)
                            code = result if isinstance(result, str) else result.code
                            self.assertEqual(normalized(esprima.parseModule(code).toDict()), expected)
                self.assertEqual(original.toDict(), mapping)

    def test_default_export_declarations_keep_their_binding_kind(self):
        for source, kind in (('export default function Hidden(){}', 'FunctionDeclaration'),
                             ('export default async function Hidden(){}', 'FunctionDeclaration'),
                             ('export default class Hidden{}', 'ClassDeclaration')):
            for options in ({}, {'format': escodegen.FORMAT_MINIFY}):
                with self.subTest(source=source, options=options):
                    tree = esprima.parseModule(source)
                    result = esprima.parseModule(escodegen.generate(tree, options))
                    self.assertEqual(result.body[0].declaration.type, kind)

    def test_leading_comments_do_not_hide_the_expression_kind(self):
        for expression in EXPRESSIONS:
            source = 'export default (/*keep*/' + expression + ');'
            tree = esprima.parseModule(source, comment=True, attachComment=True, range=True, loc=True)
            for representation in (tree, tree.toDict()):
                for compact in (False, True):
                    code = escodegen.generate(representation, {'comment': True, 'format': {'compact': compact}})
                    with self.subTest(expression=expression, compact=compact):
                        self.assertEqual(code.count('keep'), 1)
                        self.assertEqual(esprima.parseModule(code).body[0].declaration.type,
                                         tree.body[0].declaration.type)

    @unittest.skipUnless(shutil.which('node') and (REFERENCE / 'acorn').exists(), 'pinned Acorn required')
    def test_independent_parser_agrees_for_expression_and_declaration_exports(self):
        jobs = []
        for expression in EXPRESSIONS:
            for suffix in ('', '()', '.name', '?.name', ' ? 1 : 2', '`tag`'):
                source = 'export default (' + expression + ')' + suffix + ';'
                tree = esprima.parseModule(source)
                for options in ({}, {'format': escodegen.FORMAT_MINIFY}):
                    jobs.extend([{'source': source, 'module': True, 'normalized': True},
                                 {'source': escodegen.generate(tree, options), 'module': True, 'normalized': True}])
        env = dict(os.environ, ESCODEGEN_REFERENCE_NODE_MODULES=str(REFERENCE))
        result = subprocess.run(['node', str(HERE / 'reference.js')], input=json.dumps(jobs),
                                capture_output=True, text=True, encoding='utf-8', env=env, check=True)
        asts = json.loads(result.stdout)
        for index in range(0, len(asts), 2):
            with self.subTest(source=jobs[index]['source']):
                self.assertEqual(asts[index], asts[index + 1])

    @unittest.skipUnless(shutil.which('node'), 'Node required for trusted, self-contained module probes')
    def test_named_expressions_do_not_leak_or_hoist_module_bindings(self):
        sources = []
        for expression in EXPRESSIONS:
            source = ('export const before=typeof Hidden; export default (' + expression +
                      '); export const after=typeof Hidden;')
            tree = esprima.parseModule(source)
            sources.append(source)
            sources.append(escodegen.generate(tree))
            sources.append(escodegen.generate(tree.toDict(), {'format': escodegen.FORMAT_MINIFY}))
        # These are the small fixtures above, never downloaded Test262 programs.
        script = ('import fs from "node:fs"; const results=[]; let i=0;'
                  'for(const source of JSON.parse(fs.readFileSync(0,"utf8"))){'
                  'const mod=await import("data:text/javascript,"+encodeURIComponent(source)+"#"+(i++));'
                  'results.push([mod.before,mod.after,typeof mod.default]);}'
                  'console.log(JSON.stringify(results));')
        process = subprocess.run(['node', '--input-type=module', '-e', script], input=json.dumps(sources),
                                 capture_output=True, text=True, encoding='utf-8', check=True)
        self.assertEqual(json.loads(process.stdout), [['undefined', 'undefined', 'function']] * len(sources))


if __name__ == '__main__':
    unittest.main()
