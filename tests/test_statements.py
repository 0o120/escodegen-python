import json
import shutil
import subprocess
import unittest
from escodegen import generate


def ident(name):
    return {'type': 'Identifier', 'name': name}


def lit(value):
    return {'type': 'Literal', 'value': value}


def statement(expression):
    return {'type': 'ExpressionStatement', 'expression': expression}


def execute(source):
    result = subprocess.run(['node', '-e', source], text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


class StatementTests(unittest.TestCase):
    def test_prefix_and_empty_boundaries(self):
        for name in ['async', 'classy', 'functionary', 'asyncx', 'let']:
            self.assertEqual(generate(statement(ident(name))), name + ';')
        for formatting in [{'compact': True}, {'newline': ''}, {'safeConcatenation': True}]:
            self.assertEqual(generate({'type': 'Program', 'body': []}, {'format': formatting}), '')

    def test_default_import_and_with(self):
        ast = {'type': 'ImportDeclaration', 'specifiers': [
            {'type': 'ImportDefaultSpecifier', 'local': ident('x')}], 'source': lit('m')}
        self.assertEqual(generate(ast), "import x from 'm';")
        self.assertIn('with (x)', generate({'type': 'WithStatement', 'object': ident('x'),
                                         'body': {'type': 'BlockStatement', 'body': []}}))

    def test_let_bracket_expression_starts(self):
        member = {'type': 'MemberExpression', 'object': ident('let'), 'computed': True, 'property': ident('a')}
        for expr in [member, {'type': 'AssignmentExpression', 'operator': '=', 'left': member, 'right': ident('b')},
                     {'type': 'CallExpression', 'callee': member, 'arguments': []}]:
            self.assertTrue(generate(statement(expr)).startswith('(let['))

    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_expression_statement_guards_work_with_leading_comments(self):
        function = {'type': 'FunctionExpression', 'params': [], 'leadingComments': [{'type': 'Block', 'value': 'inline'}],
                    'body': {'type': 'BlockStatement', 'body': [{'type': 'ReturnStatement', 'argument': lit(1)}]}}
        code = generate(statement({'type': 'CallExpression', 'callee': function, 'arguments': []}), {'comment': True})
        self.assertEqual(execute('console.log(JSON.stringify(eval(' + json.dumps(code) + ')))'), 1)

        member = {'type': 'MemberExpression', 'object': ident('let'), 'computed': True, 'property': ident('a'),
                  'leadingComments': [{'type': 'Block', 'value': 'inline'}]}
        self.assertTrue(generate(statement(member), {'comment': True}).startswith('('))

    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_restricted_return_and_throw_comments(self):
        argument = lit(1)
        argument['leadingComments'] = [{'type': 'Block', 'value': 'inline'}]
        for kind, tail in [('ReturnStatement', 'console.log(JSON.stringify(f()))'),
                           ('ThrowStatement', 'try{f()}catch(e){console.log(JSON.stringify(e))}')]:
            ast = {'type': 'FunctionDeclaration', 'id': ident('f'), 'params': [],
                   'body': {'type': 'BlockStatement', 'body': [{'type': kind, 'argument': argument}]}}
            code = generate(ast, {'comment': True})
            self.assertEqual(execute(code + ';' + tail), 1)

    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_dangling_else_keeps_original_branch(self):
        assign = lambda n: statement({'type': 'AssignmentExpression', 'operator': '=', 'left': ident('result'), 'right': lit(n)})
        inner = {'type': 'IfStatement', 'test': ident('b'), 'consequent': assign(1), 'alternate': None}
        for consequent in [inner, {'type': 'WhileStatement', 'test': ident('b'), 'body': inner},
                           {'type': 'LabeledStatement', 'label': ident('label'), 'body': inner}]:
            outer = {'type': 'IfStatement', 'test': ident('a'), 'consequent': consequent, 'alternate': assign(2)}
            self.assertEqual(execute('let result=0,a=false,b=true;' + generate(outer) +
                                     'console.log(JSON.stringify(result))'), 2)

    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_escaped_directive_does_not_enable_strict_mode(self):
        for directive in [None, r'use\u0020strict', 'use strict']:
            first = statement(lit('use strict'))
            if directive is not None:
                first['directive'] = directive
            body = {'type': 'BlockStatement', 'body': [first, {'type': 'ReturnStatement',
                    'argument': {'type': 'BinaryExpression', 'operator': '===', 'left': {'type': 'ThisExpression'},
                                 'right': ident('undefined')}}]}
            ast = {'type': 'FunctionDeclaration', 'id': ident('f'), 'params': [], 'body': body}
            self.assertEqual(execute(generate(ast) + 'console.log(JSON.stringify(f()))'), directive == 'use strict')

    def test_escaped_directives_respect_quote_and_json_options_when_generated_alone(self):
        ast = statement(lit('use strict'))
        ast['directive'] = r'use\u0020strict'
        for is_json in [False, True]:
            code = generate(ast, {'format': {'quotes': 'double', 'json': is_json}})
            self.assertTrue(code.startswith('"'))
            if is_json:
                self.assertEqual(json.loads(code[:-1]), 'use strict')
            self.assertNotEqual(code, '"use strict";')


if __name__ == '__main__':
    unittest.main()
