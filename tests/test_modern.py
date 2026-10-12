import json
import shutil
import subprocess
import unittest
from escodegen import generate


def identifier(name, private=False):
    return {'type': 'PrivateIdentifier' if private else 'Identifier', 'name': name}


def literal(value, **fields):
    return {'type': 'Literal', 'value': value, **fields}


def syntax_check(source, module=False):
    command = ['node', '--check']
    if module:
        command += ['--input-type=module']
    result = subprocess.run(command, input=source, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(source + '\n' + result.stderr)


@unittest.skipUnless(shutil.which('node'), 'Node required')
class ModernTests(unittest.TestCase):
    def test_resource_management_is_an_explicit_extension(self):
        ast = {'type': 'VariableDeclaration', 'kind': 'using', 'declarations': [
            {'type': 'VariableDeclarator', 'id': identifier('resource'), 'init': identifier('value')}]}
        with self.assertRaisesRegex(ValueError, 'extensions.resourceManagement'):
            generate(ast)
        self.assertEqual(generate(ast, {'extensions': {'resourceManagement': True}}), 'using resource = value;')
    def test_bigint_exact_value_and_invalid_descriptors(self):
        code = generate(literal(None, bigint='9007199254740993123456789'))
        result = subprocess.run(['node', '-e', 'console.log(String(' + code + '))'], text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), '9007199254740993123456789')
        self.assertEqual(generate(literal(None, bigint='0')), '0n')
        for invalid in ['1.5', '-1', '1n', '', '01', 12]:
            with self.assertRaisesRegex(ValueError, 'bigint'):
                generate(literal(None, bigint=invalid))

    def test_class_fields_private_methods_brand_checks_and_static_blocks(self):
        private = identifier('x', True)
        field = {'type': 'PropertyDefinition', 'key': private, 'value': literal(1), 'static': False, 'computed': False}
        method = {'type': 'MethodDefinition', 'kind': 'method', 'key': identifier('has'), 'computed': False,
                  'value': {'type': 'FunctionExpression', 'params': [identifier('obj')], 'body': {'type': 'BlockStatement',
                            'body': [{'type': 'ReturnStatement', 'argument': {'type': 'BinaryExpression', 'operator': 'in',
                                      'left': private, 'right': identifier('obj')}}]}}}
        static = {'type': 'StaticBlock', 'body': [{'type': 'ExpressionStatement', 'expression': {
            'type': 'AssignmentExpression', 'operator': '=', 'left': {'type': 'MemberExpression',
                'object': {'type': 'ThisExpression'}, 'computed': False, 'property': identifier('value')}, 'right': literal(2)}}]}
        ast = {'type': 'ClassDeclaration', 'id': identifier('C'), 'body': {'type': 'ClassBody', 'body': [field, method, static]}}
        for compact in [False, True]:
            source = generate(ast, {'format': {'compact': compact}})
            syntax_check(source)
            source += ';const c=new C;console.log(JSON.stringify([c.has(c),c.has({}),C.value]))'
            result = subprocess.run(['node', '-e', source], text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout), [True, False, 2])

    def test_canonical_async_and_await_fields(self):
        ast = {'type': 'FunctionDeclaration', 'async': True, 'generator': True, 'id': identifier('f'), 'params': [],
               'body': {'type': 'BlockStatement', 'body': [{'type': 'ForOfStatement', 'await': True,
                  'left': {'type': 'VariableDeclaration', 'kind': 'const', 'declarations': [{'type': 'VariableDeclarator', 'id': identifier('x')}]},
                  'right': identifier('xs'), 'body': {'type': 'BlockStatement', 'body': []}}]}}
        code = generate(ast)
        self.assertIn('async function*', code)
        self.assertIn('for await', code)
        syntax_check(code)

    def test_namespace_exports_string_names_and_module_attributes(self):
        attributes = [{'type': 'ImportAttribute', 'key': identifier('type'), 'value': literal('json')}]
        fixtures = [
            {'type': 'ExportAllDeclaration', 'exported': identifier('ns'), 'source': literal('m')},
            {'type': 'ExportAllDeclaration', 'exported': literal('arbitrary name'), 'source': literal('m')},
            {'type': 'ExportAllDeclaration', 'source': literal('m'), 'attributes': attributes},
            {'type': 'ExportNamedDeclaration', 'specifiers': [{'type': 'ExportSpecifier', 'local': literal('a b'), 'exported': literal('c d')}], 'source': literal('m'), 'attributes': attributes},
            {'type': 'ExportNamedDeclaration', 'specifiers': []},
            {'type': 'ImportDeclaration', 'specifiers': [{'type': 'ImportSpecifier', 'imported': literal('a b'), 'local': identifier('ab')}], 'source': literal('m'), 'attributes': attributes},
            {'type': 'ImportDeclaration', 'specifiers': [], 'source': literal('m'), 'attributes': attributes},
        ]
        for ast in fixtures:
            for compact in [False, True]:
                code = generate(ast, {'format': {'compact': compact}})
                syntax_check(code, module=True)
                if ast.get('attributes'):
                    self.assertIn('with', code)
                    self.assertIn('json', code)
                if ast.get('exported'):
                    self.assertIn('as', code)

    def test_dynamic_import_options(self):
        ast = {'type': 'ImportExpression', 'source': literal('m'), 'options': {
            'type': 'ObjectExpression', 'properties': [{'type': 'Property', 'key': identifier('with'),
                'kind': 'init', 'value': {'type': 'ObjectExpression', 'properties': [
                    {'type': 'Property', 'key': identifier('type'), 'kind': 'init', 'value': literal('json')} ]}}]}}
        code = generate(ast)
        self.assertIn('with:', code)
        syntax_check(code, module=True)


if __name__ == '__main__':
    unittest.main()
