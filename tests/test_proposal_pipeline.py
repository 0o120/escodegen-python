"""Preserve extension semantics through native and mapping generation."""
import copy
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from escodegen import FORMAT_MINIFY, generate

try:
    import esprima
except ImportError:
    esprima = None


EXTENSIONS = {'resourceManagement': True, 'decorators': True,
              'deferredImportEvaluation': True, 'sourcePhaseImports': True, 'exportDefaultFrom': True}
PARSER_OPTIONS = {'explicitResourceManagement': True, 'decorators': True,
                  'deferredImportEvaluation': True, 'sourcePhaseImports': True,
                  'ecmaVersion': 2026, 'exportDefaultFrom': True}
HERE = Path(__file__).resolve().parent
OWN_REFERENCE = HERE.parent / 'tools' / 'reference' / 'node_modules'
SHARED_REFERENCE = HERE.parents[1] / 'esprima-python' / 'tools' / 'reference' / 'node_modules'
REFERENCE = Path(os.environ.get('ESCODEGEN_REFERENCE_NODE_MODULES',
    str(OWN_REFERENCE if OWN_REFERENCE.exists() else SHARED_REFERENCE)))
SOURCES = [
    'using x=resource, y=other; await using z=asyncResource;',
    r'for (using \u006ff of xs) {} for (await using of of xs) {}',
    ('async function f(){for(using x of xs){} for(await using x of xs){} '
    'for await(using x of xs){} for await(await using x of xs){} '
    'for(using x=resource;x;x=null){} for(await using x=resource;x;x=null){}}'),
    ('@first @second(1) class C extends Base {@member field=1; '
    '@factory(2) static method(x){return x} @getDec get value(){return 1} '
    '@setDec set value(v){} @accessorDec accessor x=2; '
    '@privateDec static accessor #x; @((a,b)) [key]=value;}'),
    'const C=@(factory()) class {accessor x; static accessor [key]=value;};',
    '@dec export class C{} export default @dec class D{}',
    'export @dec class C{} @dec export default class {}',
    'const value=(@dec class {}).name; const result=new (@dec class {});',
    ('import defer * as ns from "m" with {type:"json"}; '
    'const value=import.defer("m",{with:{type:"json"}});'),
    ('import source wasm from "m" with {type:"wasm"}; '
    'const value=import.source("m",{with:{type:"wasm"}});'),
    ('import defer from "m"; import source from "m"; '
    'import * as ns from "m"; const x=import("m");'),
    'export value from "m"; export default from "other"; export await from "last";',
    'export value, {x as y} from "m"; export other, * as ns from "other" with {type:"json"};',
    'export value, * as "a b" from "m";',
]


def normalize(value):
    if isinstance(value, list):
        return [normalize(child) for child in value]
    if isinstance(value, dict):
        return {key: normalize(child) for key, child in value.items()
                if key not in ('range', 'loc', 'raw', 'start', 'end', 'comments', 'tokens',
                               'leadingComments', 'trailingComments', 'innerComments')}
    return value


def identifier(name):
    return {'type': 'Identifier', 'name': name}


def declaration(kind='using', init=True):
    return {'type': 'VariableDeclaration', 'kind': kind, 'declarations': [
        {'type': 'VariableDeclarator', 'id': identifier('x'),
         'init': identifier('resource') if init else None}]}


def reference_many(jobs):
    if not shutil.which('node') or not (REFERENCE / '@babel/parser').exists():
        raise unittest.SkipTest('pinned Babel reference parser required')
    process = subprocess.run(['node', str(Path(__file__).with_name('proposal_reference.mjs'))],
                             input=json.dumps(jobs), text=True, encoding='utf-8',
                             capture_output=True, check=False,
                             env=dict(os.environ, ESCODEGEN_REFERENCE_NODE_MODULES=str(REFERENCE)))
    if process.returncode:
        raise AssertionError(process.stderr)
    return json.loads(process.stdout)


class ProposalMappingOracleTests(unittest.TestCase):
    def test_independent_babel_mapping_asts_roundtrip_without_mutation(self):
        expected = reference_many([{'source': source} for source in SOURCES])
        jobs = []
        for tree in expected:
            original = copy.deepcopy(tree)
            for format_options in ({}, {'format': FORMAT_MINIFY}):
                jobs.append({'source': generate(tree, dict(format_options, extensions=EXTENSIONS))})
                self.assertEqual(tree, original)
        actual = reference_many(jobs)
        for index, tree in enumerate(actual):
            self.assertEqual(tree, expected[index // 2], SOURCES[index // 2])


class ProposalValidationTests(unittest.TestCase):
    def test_default_reexports_preserve_both_native_and_legacy_shapes_with_an_explicit_gate(self):
        for field in ('exported', 'local'):
            specifier = {'type': 'ExportDefaultSpecifier', field: identifier('value')}
            node = {'type': 'ExportNamedDeclaration', 'specifiers': [specifier],
                    'source': {'type': 'Literal', 'value': 'm'}}
            with self.assertRaisesRegex(ValueError, 'extensions.exportDefaultFrom'):
                generate(node)
            self.assertEqual(generate(node, {'extensions': EXTENSIONS}), "export value from 'm';")
            node['source'] = None
            with self.assertRaisesRegex(ValueError, 'require a source'):
                generate(node, {'extensions': EXTENSIONS})
        specifier['exported'] = identifier('different')
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            generate(specifier, {'extensions': EXTENSIONS})

    def test_resource_loop_binding_of_retains_required_escape(self):
        node = {'type': 'ForOfStatement', 'left': declaration(init=False),
                'right': identifier('xs'), 'body': {'type': 'BlockStatement', 'body': []}}
        node['left']['declarations'][0]['id']['name'] = 'of'
        self.assertIn(r'using \u006ff of xs', generate(node, {'extensions': EXTENSIONS}))
        node['left']['kind'] = 'await using'
        self.assertIn('await using of of xs', generate(node, {'extensions': EXTENSIONS}))

    def test_resource_gate_covers_each_loop_header(self):
        for kind in ('using', 'await using'):
            for asynchronous in (False, True):
                node = {'type': 'ForOfStatement', 'await': asynchronous,
                        'left': declaration(kind, False), 'right': identifier('xs'),
                        'body': {'type': 'BlockStatement', 'body': []}}
                original = copy.deepcopy(node)
                with self.assertRaisesRegex(ValueError, 'extensions.resourceManagement'):
                    generate(node)
                code = generate(node, {'extensions': EXTENSIONS})
                self.assertIn(kind + ' x of xs', code)
                self.assertEqual('for await' in code, asynchronous)
                self.assertEqual(node, original)

    def test_invalid_resource_headers_are_not_silently_truncated(self):
        node = {'type': 'ForOfStatement', 'left': declaration(init=False),
                'right': identifier('xs'), 'body': {'type': 'EmptyStatement'}}
        node['left']['declarations'].append(copy.deepcopy(node['left']['declarations'][0]))
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            generate(node, {'extensions': EXTENSIONS})
        node['left'] = declaration(init=True)
        with self.assertRaisesRegex(ValueError, 'initializer'):
            generate(node, {'extensions': EXTENSIONS})
        node['type'] = 'ForInStatement'
        with self.assertRaisesRegex(ValueError, 'for-in'):
            generate(node, {'extensions': EXTENSIONS})
        with self.assertRaisesRegex(ValueError, 'initializer'):
            generate(declaration(init=False), {'extensions': EXTENSIONS})

    def test_decorators_and_accessors_are_explicit_and_well_formed(self):
        node = {'type': 'ClassDeclaration', 'id': identifier('C'),
                'decorators': [{'type': 'Decorator', 'expression': identifier('dec')}],
                'body': {'type': 'ClassBody', 'body': []}}
        with self.assertRaisesRegex(ValueError, 'extensions.decorators'):
            generate(node)
        self.assertIn('@(dec)', generate(node, {'extensions': EXTENSIONS}))
        node['decorators'] = [identifier('dec')]
        with self.assertRaisesRegex(ValueError, 'Decorator nodes'):
            generate(node, {'extensions': EXTENSIONS})
        node['decorators'] = 'dec'
        with self.assertRaisesRegex(ValueError, 'must be a list'):
            generate(node, {'extensions': EXTENSIONS})
        accessor = {'type': 'AccessorProperty', 'key': identifier('x'), 'value': None}
        with self.assertRaisesRegex(ValueError, 'extensions.decorators'):
            generate(accessor)

    def test_import_phases_are_gated_and_cannot_disappear(self):
        for phase, flag, specifier in [('defer', 'deferredImportEvaluation', 'ImportNamespaceSpecifier'),
                                       ('source', 'sourcePhaseImports', 'ImportDefaultSpecifier')]:
            node = {'type': 'ImportDeclaration', 'phase': phase,
                    'source': {'type': 'Literal', 'value': 'm'},
                    'specifiers': [{'type': specifier, 'local': identifier('binding')}]}
            with self.assertRaisesRegex(ValueError, flag):
                generate(node)
            self.assertIn('import ' + phase, generate(node, {'extensions': EXTENSIONS}))
            node['specifiers'] = []
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                generate(node, {'extensions': EXTENSIONS})
            expression = {'type': 'ImportExpression', 'phase': phase,
                          'source': {'type': 'Literal', 'value': 'm'}, 'options': identifier('options')}
            self.assertEqual(generate(expression, {'extensions': EXTENSIONS}),
                             'import.' + phase + "('m', options)")
        expression['phase'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'phase'):
            generate(expression, {'extensions': EXTENSIONS})


@unittest.skipUnless(esprima is not None, 'coordinated parser required')
class ProposalPipelineTests(unittest.TestCase):
    def test_proposal_identifier_names_follow_export_names_rather_than_binding_rules(self):
        for name in ('default', 'await', 'yield', 'static', 'enum', 'async', 'if'):
            source = 'export ' + name + ' from "m";'
            tree = esprima.parseModule(source, PARSER_OPTIONS)
            original = tree.toDict()
            for format_options in ({}, {'format': FORMAT_MINIFY}):
                options = dict(format_options, extensions=EXTENSIONS)
                code = generate(tree, options)
                self.assertEqual(code, generate(original, options))
                self.assertEqual(normalize(esprima.parseModule(code, PARSER_OPTIONS).toDict()),
                                 normalize(original))

    def test_standard_default_export_of_from_binding_survives_proposal_gate(self):
        source = 'const from=1; export default from;'
        generated = []
        for options in ({}, PARSER_OPTIONS):
            tree = esprima.parseModule(source, options)
            self.assertEqual(tree.body[1].type, 'ExportDefaultDeclaration')
            generated.append({'source': generate(tree), 'exportDefaultFrom': False})
        # Babel's proposal plugin has the same ambiguity bug that this test
        # guards against. Its base ECMAScript parser provides the core oracle.
        result = reference_many([{'source': source, 'exportDefaultFrom': False}] + generated)
        self.assertEqual(result[1:], [result[0], result[0]])

    def test_native_mapping_and_reparsed_trees_preserve_every_extension(self):
        for source in SOURCES:
            with self.subTest(source=source):
                tree = esprima.parseModule(source, PARSER_OPTIONS)
                original = tree.toDict()
                for format_options in ({}, {'format': FORMAT_MINIFY},
                                       {'format': {'space': '', 'newline': '', 'semicolons': False}},
                                       {'sourceMap': 'proposal.js', 'sourceMapWithCode': True}):
                    options = dict(format_options, extensions=EXTENSIONS)
                    native = generate(tree, options)
                    mapping = generate(original, options)
                    code = native.code if options.get('sourceMapWithCode') else native
                    self.assertEqual(code, mapping.code if options.get('sourceMapWithCode') else mapping)
                    self.assertEqual(normalize(esprima.parseModule(code, PARSER_OPTIONS).toDict()),
                                     normalize(original))
                    self.assertEqual(tree.toDict(), original)

    def test_independent_babel_trees_match_before_and_after_generation(self):
        if not shutil.which('node') or not (REFERENCE / '@babel/parser').exists():
            self.skipTest('pinned Babel reference parser required')
        generated = []
        for source in SOURCES:
            tree = esprima.parseModule(source, PARSER_OPTIONS)
            for options in ({'extensions': EXTENSIONS}, {'extensions': EXTENSIONS, 'format': FORMAT_MINIFY}):
                generated.append({'source': generate(tree, options)})
        jobs = [{'source': source} for source in SOURCES] + generated
        result = reference_many(jobs)
        expected = result[:len(SOURCES)]
        for index, actual in enumerate(result[len(SOURCES):]):
            self.assertEqual(actual, expected[index // 2], SOURCES[index // 2])

    def test_comments_positions_and_sourcemaps_are_preserved(self):
        source = '// class note\n@dec class C { // member note\n@field accessor x=1; }'
        tree = esprima.parseModule(source, dict(PARSER_OPTIONS, comment=True, attachComment=True,
                                               loc=True, range=True))
        original = tree.toDict()
        result = generate(tree, {'extensions': EXTENSIONS, 'comment': True,
                                 'sourceMap': 'proposal.js', 'sourceMapWithCode': True})
        self.assertIn('class note', result.code)
        self.assertIn('member note', result.code)
        self.assertEqual(result.map.toJSON()['sources'], ['proposal.js'])
        self.assertTrue(result.map.toJSON()['mappings'])
        self.assertEqual(tree.toDict(), original)
        self.assertEqual(normalize(esprima.parseModule(result.code, PARSER_OPTIONS).toDict()),
                         normalize(original))


if __name__ == '__main__':
    unittest.main()
