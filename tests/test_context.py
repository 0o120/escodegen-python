import copy
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from escodegen import generate


class ContextTests(unittest.TestCase):
    def test_nested_generation_does_not_leak_options(self):
        def parse(raw):
            self.assertEqual(generate({'type': 'Literal', 'value': 'inner'}, {
                'format': {'compact': True, 'quotes': 'double'}}), '"inner"')
            return SimpleNamespace(body=[SimpleNamespace(expression=SimpleNamespace(type='Literal', value=1))])
        ast = {'type': 'Program', 'body': [
            {'type': 'ExpressionStatement', 'expression': {'type': 'Literal', 'value': 1, 'raw': '1'}},
            {'type': 'ExpressionStatement', 'expression': {'type': 'Literal', 'value': 'outer'}}]}
        self.assertEqual(generate(ast, {'parse': parse}), "1;\n'outer';")

    def test_concurrent_options_and_inputs_are_isolated(self):
        ast = {'type': 'Program', 'body': [{'type': 'ExpressionStatement',
                                         'expression': {'type': 'Literal', 'value': 'x'}}]}
        saved = copy.deepcopy(ast)
        def run(i):
            quote = 'double' if i % 2 else 'single'
            options = {'format': {'quotes': quote, 'compact': bool(i % 3)}}
            before = copy.deepcopy(options)
            result = generate(ast, options)
            self.assertEqual(options, before)
            return result
        with ThreadPoolExecutor(max_workers=12) as pool:
            for i, result in enumerate(pool.map(run, range(600))):
                self.assertEqual(result, '"x";' if i % 2 else "'x';")
        self.assertEqual(ast, saved)

    def test_verbatim_is_optional_and_keeps_non_json_values(self):
        self.assertEqual(generate({'type': 'Literal', 'value': 1}, {'verbatim': 'custom'}), '1')
        self.assertEqual(generate({'type': 'Identifier', 'name': 'x', 'custom': {'content': '2 + 3', 'precedence': 12}},
                                  {'verbatim': 'custom'}), '2 + 3')

    def test_conflicting_canonical_and_legacy_flags_are_errors(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting async'):
            generate({'type': 'FunctionExpression', 'async': True, 'isAsync': False})

    def test_identifier_names_use_modern_unicode(self):
        self.assertEqual(generate({'type': 'Identifier', 'name': '\U00010400x'}), '\U00010400x')
        for name in ['', 'has space', '\ud800', '1start']:
            with self.assertRaisesRegex(ValueError, 'IdentifierName'):
                generate({'type': 'Identifier', 'name': name})

    def test_custom_metadata_cycles_are_preserved_but_child_cycles_fail(self):
        ast = {'type': 'Literal', 'value': 1}
        ast['metadata'] = ast
        self.assertEqual(generate(ast), '1')
        bad = {'type': 'UnaryExpression', 'operator': '!'}
        bad['argument'] = bad
        with self.assertRaisesRegex(ValueError, 'Cyclic AST child graph'):
            generate(bad)

    def test_raw_reuse_compares_semantic_types_regexes_and_negative_zero(self):
        def parse(raw):
            values = {'1': {'type': 'Literal', 'value': 1}, '0': {'type': 'Literal', 'value': 0},
                      '/x/g': {'type': 'Literal', 'value': None, 'regex': {'pattern': 'x', 'flags': 'g'}}}
            return {'type': 'Program', 'body': [{'type': 'ExpressionStatement', 'expression': values[raw]}]}
        self.assertEqual(generate({'type': 'Literal', 'value': True, 'raw': '1'}, {'parse': parse}), 'true')
        self.assertEqual(generate({'type': 'Literal', 'value': -0.0, 'raw': '0'}, {'parse': parse}), '-0')
        self.assertEqual(generate({'type': 'Literal', 'value': None, 'raw': '/x/g', 'regex': {'pattern': 'y', 'flags': 'g'}},
                                  {'parse': parse}), '/y/g')
        self.assertEqual(generate({'type': 'Literal', 'value': 1, 'raw': '1'}, {'parse': parse}), '1')

    def test_malformed_children_lists_and_missing_null_are_diagnosed(self):
        cases = [({'type': 'Literal'}, 'Literal.value'),
                 ({'type': 'Program', 'body': None}, 'Program.body'),
                 ({'type': 'VariableDeclaration', 'kind': 'const', 'declarations': []}, 'cannot be empty'),
                 ({'type': 'CallExpression', 'callee': {'type': 'Identifier', 'name': 'f'}, 'arguments': None}, 'CallExpression.arguments'),
                 ({'type': 'MemberExpression', 'object': None, 'property': {'type': 'Identifier', 'name': 'x'}}, 'MemberExpression.object')]
        for ast, message in cases:
            with self.assertRaisesRegex(ValueError, message):
                generate(ast)


if __name__ == '__main__':
    unittest.main()
