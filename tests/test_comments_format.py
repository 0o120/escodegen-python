import copy
import unittest
from escodegen import generate


class CommentFormatTests(unittest.TestCase):
    def test_preserve_blank_lines_uses_utf16_ranges(self):
        source = '//\U0001f600\r\n\r\n/*banner*/\r\n\r\nx;'
        # Offsets intentionally follow UTF-16, not Python string indices.
        def offset(index):
            return len(source[:index].encode('utf-16-le')) // 2
        comment_start = source.index('/*')
        comment_end = source.index('*/') + 2
        x = source.index('x;')
        ast = {'type': 'Program', 'range': [0, offset(len(source))], 'body': [
            {'type': 'ExpressionStatement', 'range': [offset(x), offset(x + 2)],
             'expression': {'type': 'Identifier', 'name': 'x'},
             'leadingComments': [{'type': 'Block', 'value': 'banner',
                 'range': [offset(comment_start), offset(comment_end)],
                 'extendedRange': [offset(comment_start), offset(x)]}]}]}
        before = copy.deepcopy(ast)
        generated = generate(ast, {'comment': True, 'sourceCode': source,
                                   'format': {'preserveBlankLines': True}})
        self.assertIn('/*banner*/\n\nx;', generated)
        self.assertEqual(ast, before)

    def test_invalid_source_ranges_are_actionable(self):
        ast = {'type': 'Program', 'body': [], 'range': [0, 10]}
        with self.assertRaisesRegex(ValueError, 'UTF-16 offsets'):
            generate(ast, {'sourceCode': 'x;', 'format': {'preserveBlankLines': True}})
        ast['range'] = [0, 1]
        with self.assertRaisesRegex(ValueError, 'surrogate pair'):
            generate(ast, {'sourceCode': '\U0001f600', 'format': {'preserveBlankLines': True}})

    def test_hashbang_is_first_and_not_duplicated(self):
        ast = {'type': 'Program', 'hashbang': '/usr/bin/env node', 'body': [],
               'leadingComments': [{'type': 'Line', 'hashbang': True, 'value': '/usr/bin/env node'},
                                   {'type': 'Block', 'value': 'license'}]}
        for compact in [False, True]:
            source = generate(ast, {'comment': True, 'format': {'compact': compact, 'safeConcatenation': True}})
            self.assertTrue(source.startswith('#!/usr/bin/env node\n'))
            self.assertEqual(source.count('/usr/bin/env node'), 1)
            self.assertIn('license', source)
        self.assertEqual(generate(ast), '#!/usr/bin/env node\n')

    def test_trailing_comments_and_empty_multiline_comment_options(self):
        ast = {'type': 'Identifier', 'name': 'x', 'trailingComments': [{'type': 'Block', 'value': '\n'}]}
        code = generate(ast, {'comment': True, 'format': {'indent': {'adjustMultilineComment': True}}})
        self.assertIn('/*\n', code)
        self.assertTrue(code.endswith('*/'))

    def test_preserve_multiple_leading_and_trailing_comments(self):
        source = '/*a*/\n/*b*/\nx; /*c*/ /*d*/'
        comments = []
        for name in 'abcd':
            start = source.index('/*' + name)
            comments.append({'type': 'Block', 'value': name, 'range': [start, start + 5],
                             'extendedRange': [start, start + 5]})
        comments[1]['extendedRange'][1] = source.index('x;')
        comments[2]['extendedRange'][0] = source.index('x;') + 2
        ast = {'type': 'ExpressionStatement', 'expression': {'type': 'Identifier', 'name': 'x'},
               'leadingComments': comments[:2], 'trailingComments': comments[2:]}
        code = generate(ast, {'comment': True, 'sourceCode': source,
                              'format': {'preserveBlankLines': True}})
        for name in 'abcd':
            self.assertIn('/*' + name + '*/', code)

    def test_async_method_inline_key_comments_keep_restricted_boundary(self):
        ast = {'type': 'ObjectExpression', 'properties': [{'type': 'Property', 'method': True, 'kind': 'init',
            'key': {'type': 'Identifier', 'name': 'f', 'leadingComments': [{'type': 'Block', 'value': 'inline'}]},
            'value': {'type': 'FunctionExpression', 'async': True, 'params': [],
                      'body': {'type': 'BlockStatement', 'body': []}}}]}
        code = generate(ast, {'comment': True})
        self.assertIn('async /*inline*/ f()', code)

    def test_jsx_spread_children_and_text_escaping(self):
        ast = {'type': 'JSXFragment', 'children': [
            {'type': 'JSXText', 'value': '<&{text}'},
            {'type': 'JSXSpreadChild', 'expression': {'type': 'Identifier', 'name': 'xs'}}]}
        self.assertEqual(generate(ast), '<>&lt;&amp;&#123;text&#125;{...xs}</>')


if __name__ == '__main__':
    unittest.main()
