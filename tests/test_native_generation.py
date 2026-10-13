import unittest
from unittest.mock import patch

from escodegen import generate
from escodegen.escodegen import SimpleObj


class Native:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    def __getattr__(self, name):
        return None


class NativeGenerationTests(unittest.TestCase):
    def test_plain_native_graph_is_read_only_without_a_snapshot(self):
        comment = Native(type='Line', value=' note')
        literal = Native(type='Literal', value=1)
        node = Native(type='Program', body=[Native(type='ExpressionStatement', expression=literal,
                                                 leadingComments=[comment])], comments=[comment])
        savedComments = list(node.comments)
        savedStatements = list(node.body)
        with patch.object(SimpleObj, 'fromDict', side_effect=AssertionError('unnecessary copy')):
            self.assertEqual(generate(node), '1;')
        self.assertEqual(generate(node, {'comment': True}), '// note\n1;')
        self.assertIs(node.comments[0], node.body[0].leadingComments[0])
        self.assertEqual(node.comments, savedComments)
        self.assertEqual(node.body, savedStatements)
        self.assertEqual(node.body[0].expression.value, 1)
        self.assertEqual(comment.value, ' note')

    def test_native_alias_conflicts_in_metadata_are_still_diagnosed(self):
        node = Native(type='Literal', value=1,
                      metadata=Native(**{'async': True, 'isAsync': False}))
        with self.assertRaisesRegex(ValueError, 'Conflicting async/isAsync'):
            generate(node)

    def test_native_aliases_mappings_and_field_definitions_normalize(self):
        node = Native(**{'type': 'ArrowFunctionExpression', 'async': True,
                         'params': [], 'body': {'type': 'Literal', 'value': 1}, 'expression': True})
        self.assertEqual(generate(node), 'async () => 1')
        self.assertNotIn('isAsync', vars(node))
        field = Native(type='FieldDefinition', key=Native(type='Identifier', name='x'), value=None)
        self.assertEqual(generate(field), 'x;')
        self.assertEqual(field.type, 'FieldDefinition')

    def test_native_cycles_are_checked_without_mutating_or_copying(self):
        node = Native(type='UnaryExpression', operator='!')
        node.argument = node
        with self.assertRaisesRegex(ValueError, 'Cyclic AST child graph'):
            generate(node)
        literal = Native(type='Literal', value=1)
        literal.metadata = [literal]
        self.assertEqual(generate(literal), '1')
        self.assertIs(literal.metadata[0], literal)

    def test_hashbang_comment_filtering_uses_a_snapshot(self):
        comment = Native(type='Line', value='node', hashbang=True)
        node = Native(type='Program', hashbang='node', body=[], comments=[comment], leadingComments=[comment])
        self.assertEqual(generate(node, {'comment': True}), '#!node\n')
        self.assertEqual(node.comments, [comment])
        self.assertEqual(node.leadingComments, [comment])
        comment.type = 'Block'
        self.assertEqual(generate(node, {'comment': True}), '#!node\n')
        self.assertEqual(node.comments, [comment])

    def test_parse_callbacks_preserve_the_input_snapshot_contract(self):
        later = Native(type='Literal', value=2)
        node = Native(type='Program', body=[
            Native(type='ExpressionStatement', expression=Native(type='Literal', value=1, raw='1')),
            Native(type='ExpressionStatement', expression=later)])
        def parse(raw):
            later.value = 99
            return {'type': 'Program', 'body': [{'type': 'ExpressionStatement',
                    'expression': {'type': 'Literal', 'value': 1}}]}
        self.assertEqual(generate(node, {'parse': parse}), '1;\n2;')
        self.assertEqual(later.value, 99)

    def test_descriptors_and_callable_metadata_keep_public_adapter_behavior(self):
        class WithProperty(Native):
            @property
            def value(self):
                return 4
        self.assertEqual(generate(WithProperty(type='Literal')), '4')
        class CallableMetadata(Native):
            def __call__(self):
                return None
        metadata = CallableMetadata(**{'async': True, 'isAsync': False})
        self.assertEqual(generate(Native(type='Literal', value=1, metadata=metadata)), '1')

    def test_custom_truthiness_and_empty_native_flags_keep_snapshot_semantics(self):
        class FalseBranch(Native):
            def __bool__(self):
                return False
        branch = FalseBranch(type='ExpressionStatement', expression=Native(type='Literal', value=1))
        node = Native(type='IfStatement', test=Native(type='Literal', value=True),
                      consequent=Native(type='EmptyStatement'), alternate=branch)
        self.assertIn('else', generate(node))
        member = Native(type='MemberExpression', object=Native(type='Identifier', name='a'),
                        property=Native(type='Identifier', name='x'), computed=Native())
        self.assertEqual(generate(member), 'a.x')

    def test_custom_alias_equality_does_not_bypass_adapter_validation(self):
        class Equal(Native):
            def __eq__(self, other):
                return True
        node = Native(type='Literal', value=1, metadata=Native(**{
            'async': Equal(a=1), 'isAsync': Equal(a=2)}))
        with self.assertRaisesRegex(ValueError, 'Conflicting async/isAsync'):
            generate(node)

    def test_operator_overloads_cannot_hide_an_invalid_import_name(self):
        class EqualName(Native):
            def __eq__(self, other):
                return True
        specifier = Native(type='ImportSpecifier', imported=Native(type='Identifier', name='x'),
                           local=Native(type='Identifier', name=EqualName(value='x')))
        node = Native(type='ImportDeclaration', specifiers=[specifier],
                      source=Native(type='Literal', value='m'))
        with self.assertRaisesRegex(ValueError, 'IdentifierName'):
            generate(node)

    def test_optional_field_methods_remain_absent_in_adapter_semantics(self):
        class WithNumber(Native):
            def number(self):
                return 1
        self.assertEqual(generate(WithNumber(type='Literal', value=1)), '1')

    def test_class_proxies_preserve_mapping_adapter_precedence(self):
        class Proxy(Native):
            @property
            def __class__(self):
                return dict
            def items(self):
                return {'type': 'Literal', 'value': 9}.items()
        self.assertEqual(generate(Proxy(type='Literal', value=2)), '9')

    def test_callable_missing_attribute_code_metadata_is_not_trusted(self):
        class Spoof:
            __code__ = SimpleObj.__getattr__.__code__
            def __call__(self, *args):
                return True
        class Node(Native):
            __getattr__ = Spoof()
        node = Node(type='FunctionExpression', params=[],
                    body=Native(type='BlockStatement', body=[]))
        self.assertEqual(generate(node), 'function () {\n}')

    def test_attribute_descriptors_and_static_binding_use_the_snapshot(self):
        class MissingDescriptor:
            def __get__(self, instance, owner):
                return Native.__getattr__ if instance is None else lambda name: True
        class WithMissing(Native):
            __getattr__ = MissingDescriptor()
        self.assertEqual(generate(WithMissing(type='Literal', value=1)), '1')
        class AttributeDescriptor:
            def __get__(self, instance, owner):
                if instance is None:
                    return object.__getattribute__
                return lambda name: 9 if name == 'value' else object.__getattribute__(instance, name)
        class WithAttribute(Native):
            __getattribute__ = AttributeDescriptor()
        self.assertEqual(generate(WithAttribute(type='Literal', value=1)), '1')
        class StaticMissing(Native):
            __getattr__ = staticmethod(Native.__getattr__)
        self.assertEqual(generate(StaticMissing(type='Literal', value=1)), '1')
        class DisabledMissing(Native):
            __getattr__ = None
        self.assertEqual(generate(DisabledMissing(type='Literal', value=1)), '1')


if __name__ == '__main__':
    unittest.main()
