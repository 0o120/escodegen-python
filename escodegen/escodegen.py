# Copyright (C) 2012-2014 Yusuke Suzuki <utatane.tea@gmail.com>
# Copyright (C) 2015 Ingvar Stepanyan <me@rreverser.com>
# Copyright (C) 2014 Ivan Nikulin <ifaaan@gmail.com>
# Copyright (C) 2012-2013 Michael Ficarra <escodegen.copyright@michael.ficarra.me>
# Copyright (C) 2012-2013 Mathias Bynens <mathias@qiwi.be>
# Copyright (C) 2013 Irakli Gozalishvili <rfobic@gmail.com>
# Copyright (C) 2012 Robert Gust-Bardon <donate@robert.gust-bardon.org>
# Copyright (C) 2012 John Freeman <jfreeman08@gmail.com>
# Copyright (C) 2011-2012 Ariya Hidayat <ariya.hidayat@gmail.com>
# Copyright (C) 2012 Joost-Wim Boekesteijn <joost-wim@boekesteijn.nl>
# Copyright (C) 2012 Kris Kowal <kris.kowal@cixar.com>
# Copyright (C) 2012 Arpad Borsos <arpad.borsos@googlemail.com>
# Copyright (C) 2020 Apple Inc. All rights reserved.
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#   * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
# THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import re
import math
import esutils
from collections.abc import Mapping
from .sourcemap import SourceNode





from contextvars import ContextVar
from types import FunctionType, GetSetDescriptorType, SimpleNamespace

_generation_context = ContextVar('escodegen_context')

_context = _generation_context.get

# Every caller below obtains an exact code point through ord (or a zero
# sentinel). Older compatible esutils versions retain the strict fallback.
_identifierStart = getattr(esutils.code, '_identifier_start_from_ord', esutils.code.isIdentifierStart)
_identifierPart = getattr(esutils.code, '_identifier_part_from_ord', esutils.code.isIdentifierPart)
_whiteSpace = getattr(esutils.code, '_white_space_from_ord', esutils.code.isWhiteSpace)
_lineTerminator = getattr(esutils.code, '_line_terminator_from_ord', esutils.code.isLineTerminator)
_decimalDigit = getattr(esutils.code, '_decimal_digit_from_ord', esutils.code.isDecimalDigit)
_asciiIdentifier = re.compile(r'[$A-Z_a-z][$0-9A-Z_a-z]*').fullmatch


_NODE_LIST_FIELDS = {
    'Program': 'body', 'BlockStatement': 'body', 'ClassBody': 'body', 'StaticBlock': 'body',
    'ArrayExpression': 'elements', 'ArrayPattern': 'elements',
    'ObjectExpression': 'properties', 'ObjectPattern': 'properties',
    'SequenceExpression': 'expressions', 'CallExpression': 'arguments', 'NewExpression': 'arguments',
    'FunctionExpression': 'params', 'FunctionDeclaration': 'params', 'ArrowFunctionExpression': 'params',
    'VariableDeclaration': 'declarations', 'ImportDeclaration': 'specifiers',
    'SwitchStatement': 'cases', 'SwitchCase': 'consequent',
    'JSXElement': 'children', 'JSXFragment': 'children', 'JSXOpeningElement': 'attributes',
}
_NODE_CHILD_FIELDS = {
    'ExpressionStatement': ('expression',), 'MemberExpression': ('object', 'property'),
    'AssignmentExpression': ('left', 'right'), 'AssignmentPattern': ('left', 'right'),
    'BinaryExpression': ('left', 'right'), 'LogicalExpression': ('left', 'right'),
    'ConditionalExpression': ('test', 'consequent', 'alternate'),
    'UnaryExpression': ('argument',), 'UpdateExpression': ('argument',),
    'SpreadElement': ('argument',), 'RestElement': ('argument',),
    'AwaitExpression': ('argument',), 'ThrowStatement': ('argument',),
    'CallExpression': ('callee',), 'NewExpression': ('callee',),
    'ChainExpression': ('expression',), 'ImportExpression': ('source',),
    'ImportDeclaration': ('source',), 'ExportAllDeclaration': ('source',),
    'PropertyDefinition': ('key',), 'AccessorProperty': ('key',), 'Decorator': ('expression',),
    'Property': ('key', 'value'),
    'MethodDefinition': ('key', 'value'), 'VariableDeclarator': ('id',),
    'IfStatement': ('test', 'consequent'), 'WhileStatement': ('test', 'body'),
    'WithStatement': ('object', 'body'), 'DoWhileStatement': ('test', 'body'),
    'FunctionDeclaration': ('body',), 'FunctionExpression': ('body',), 'ArrowFunctionExpression': ('body',),
    'JSXExpressionContainer': ('expression',), 'JSXSpreadChild': ('expression',),
    'JSXSpreadAttribute': ('argument',), 'JSXElement': ('openingElement',),
}


def validateNodeFields(node, context=None):
    context = _context() if context is None else context
    nodeTypes = context.nodeTypes
    if type(node) not in nodeTypes or not isinstance(node.type, str):
        raise ValueError('Expected an ESTree node with a string type field')
    nodeType = node.type
    field = _NODE_LIST_FIELDS.get(nodeType)
    if field is not None and not isinstance(getattr(node, field), list):
        raise ValueError(f'{nodeType}.{field} must be a list')
    if nodeType in ('SequenceExpression', 'VariableDeclaration') and not getattr(node, field):
        raise ValueError(f'{nodeType}.{field} cannot be empty')
    for field in _NODE_CHILD_FIELDS.get(nodeType, ()):
        child = getattr(node, field)
        if type(child) not in nodeTypes or not isinstance(child.type, str):
            raise ValueError(f'{nodeType}.{field} must contain an ESTree node')
    if nodeType == 'Literal' and 'value' not in vars(node) and node.regex is None and node.bigint is None:
        raise ValueError('Literal.value is required; use an explicit None for null')
    decorators = getattr(node, 'decorators')
    if decorators is not None:
        if not isinstance(decorators, list):
            raise ValueError(f'{nodeType}.decorators must be a list')
        if decorators and nodeType not in ('ClassDeclaration', 'ClassExpression', 'MethodDefinition',
                                           'PropertyDefinition', 'AccessorProperty'):
            raise ValueError(f'Decorators are unsupported on {nodeType}')
        for decorator in decorators:
            if type(decorator) not in nodeTypes or decorator.type != 'Decorator':
                raise ValueError(f'{nodeType}.decorators must contain Decorator nodes')

def generate(node, options=None):
    """Generate without mutating input ASTs or sharing formatting state."""
    context = SimpleNamespace(activeNodes=set(), identifierNames=set(), nodeTypes={SimpleObj})
    token = _generation_context.set(context)
    try:
        return _generate(node, options)
    except RecursionError as error:
        raise ValueError('AST nesting exceeds the generator recursion capacity') from error
    finally:
        _generation_context.reset(token)

class Syntax:
    AccessorProperty = "AccessorProperty"
    AssignmentExpression = "AssignmentExpression"
    AssignmentPattern = "AssignmentPattern"
    ArrayExpression = "ArrayExpression"
    ArrayPattern = "ArrayPattern"
    ArrowFunctionExpression = "ArrowFunctionExpression"
    AwaitExpression = "AwaitExpression" # CAUTION = It"s deferred to ES7.
    BlockStatement = "BlockStatement"
    BinaryExpression = "BinaryExpression"
    BreakStatement = "BreakStatement"
    CallExpression = "CallExpression"
    CatchClause = "CatchClause"
    ChainExpression = "ChainExpression"
    ClassBody = "ClassBody"
    ClassDeclaration = "ClassDeclaration"
    ClassExpression = "ClassExpression"
    ComprehensionBlock = "ComprehensionBlock"  # CAUTION = It"s deferred to ES7.
    ComprehensionExpression = "ComprehensionExpression"  # CAUTION = It"s deferred to ES7.
    ConditionalExpression = "ConditionalExpression"
    ContinueStatement = "ContinueStatement"
    DebuggerStatement = "DebuggerStatement"
    Decorator = "Decorator"
    DirectiveStatement = "DirectiveStatement"
    DoWhileStatement = "DoWhileStatement"
    EmptyStatement = "EmptyStatement"
    ExportAllDeclaration = "ExportAllDeclaration"
    ExportDefaultDeclaration = "ExportDefaultDeclaration"
    ExportDefaultSpecifier = "ExportDefaultSpecifier"
    ExportNamespaceSpecifier = "ExportNamespaceSpecifier"
    ExportNamedDeclaration = "ExportNamedDeclaration"
    ExportSpecifier = "ExportSpecifier"
    ExpressionStatement = "ExpressionStatement"
    ForStatement = "ForStatement"
    ForInStatement = "ForInStatement"
    ForOfStatement = "ForOfStatement"
    FunctionDeclaration = "FunctionDeclaration"
    FunctionExpression = "FunctionExpression"
    GeneratorExpression = "GeneratorExpression"  # CAUTION = It"s deferred to ES7.
    Identifier = "Identifier"
    IfStatement = "IfStatement"
    ImportExpression = "ImportExpression"
    ImportDeclaration = "ImportDeclaration"
    ImportDefaultSpecifier = "ImportDefaultSpecifier"
    ImportNamespaceSpecifier = "ImportNamespaceSpecifier"
    ImportSpecifier = "ImportSpecifier"
    Literal = "Literal"
    LabeledStatement = "LabeledStatement"
    LogicalExpression = "LogicalExpression"
    MemberExpression = "MemberExpression"
    MetaProperty = "MetaProperty"
    MethodDefinition = "MethodDefinition"
    ModuleSpecifier = "ModuleSpecifier"
    NewExpression = "NewExpression"
    ObjectExpression = "ObjectExpression"
    ObjectPattern = "ObjectPattern"
    PrivateIdentifier = "PrivateIdentifier"
    Program = "Program"
    Property = "Property"
    PropertyDefinition = "PropertyDefinition"
    RestElement = "RestElement"
    ReturnStatement = "ReturnStatement"
    SequenceExpression = "SequenceExpression"
    SpreadElement = "SpreadElement"
    Super = "Super"
    SwitchStatement = "SwitchStatement"
    SwitchCase = "SwitchCase"
    TaggedTemplateExpression = "TaggedTemplateExpression"
    TemplateElement = "TemplateElement"
    TemplateLiteral = "TemplateLiteral"
    ThisExpression = "ThisExpression"
    ThrowStatement = "ThrowStatement"
    TryStatement = "TryStatement"
    UnaryExpression = "UnaryExpression"
    UpdateExpression = "UpdateExpression"
    VariableDeclaration = "VariableDeclaration"
    VariableDeclarator = "VariableDeclarator"
    WhileStatement = "WhileStatement"
    WithStatement = "WithStatement"
    YieldExpression = "YieldExpression"


# Generation is done by generateExpression.
def isExpression(node):
    return hasattr(CodeGeneratorExpression, node.type)

# Generation is done by generateStatement.
def isStatement(node):
    return hasattr(CodeGeneratorStatement, node.type)

class Precedence:
    Sequence = 0
    Yield = 1
    Assignment = 1
    Conditional = 2
    ArrowFunction = 2
    Coalesce = 3
    LogicalOR = 4
    LogicalAND = 5
    BitwiseOR = 6
    BitwiseXOR = 7
    BitwiseAND = 8
    Equality = 9
    Relational = 10
    BitwiseSHIFT = 11
    Additive = 12
    Multiplicative = 13
    Exponentiation = 14
    Await = 15
    Unary = 15
    Postfix = 16
    OptionalChaining = 17
    Call = 18
    New = 19
    TaggedTemplate = 20
    Member = 21
    Primary = 22
    
BinaryPrecedence = {
    '??': Precedence.Coalesce,
    '||': Precedence.LogicalOR,
    '&&': Precedence.LogicalAND,
    '|': Precedence.BitwiseOR,
    '^': Precedence.BitwiseXOR,
    '&': Precedence.BitwiseAND,
    '==': Precedence.Equality,
    '!=': Precedence.Equality,
    '===': Precedence.Equality,
    '!==': Precedence.Equality,
    'is': Precedence.Equality,
    'isnt': Precedence.Equality,
    '<': Precedence.Relational,
    '>': Precedence.Relational,
    '<=': Precedence.Relational,
    '>=': Precedence.Relational,
    'in': Precedence.Relational,
    'instanceof': Precedence.Relational,
    '<<': Precedence.BitwiseSHIFT,
    '>>': Precedence.BitwiseSHIFT,
    '>>>': Precedence.BitwiseSHIFT,
    '+': Precedence.Additive,
    '-': Precedence.Additive,
    '*': Precedence.Multiplicative,
    '%': Precedence.Multiplicative,
    '/': Precedence.Multiplicative,
    '**': Precedence.Exponentiation
}

#Flags
F_ALLOW_IN = 1
F_ALLOW_CALL = 1 << 1
F_ALLOW_UNPARATH_NEW = 1 << 2
F_FUNC_BODY = 1 << 3
F_DIRECTIVE_CTX = 1 << 4
F_SEMICOLON_OPT = 1 << 5
F_FOUND_COALESCE = 1 << 6
F_USING_FOR_OF = 1 << 7

#Expression flag sets
#NOTE: Flag order:
# F_ALLOW_IN
# F_ALLOW_CALL
# F_ALLOW_UNPARATH_NEW
E_FTT = F_ALLOW_CALL | F_ALLOW_UNPARATH_NEW
E_TTF = F_ALLOW_IN | F_ALLOW_CALL
E_TTT = F_ALLOW_IN | F_ALLOW_CALL | F_ALLOW_UNPARATH_NEW
E_TFF = F_ALLOW_IN
E_FFT = F_ALLOW_UNPARATH_NEW
E_TFT = F_ALLOW_IN | F_ALLOW_UNPARATH_NEW

#Statement flag sets
#NOTE: Flag order:
# F_ALLOW_IN
# F_FUNC_BODY
# F_DIRECTIVE_CTX
# F_SEMICOLON_OPT
S_TFFF = F_ALLOW_IN
S_TFFT = F_ALLOW_IN | F_SEMICOLON_OPT
S_FFFF = 0x00
S_TFTF = F_ALLOW_IN | F_DIRECTIVE_CTX
S_TTFF = F_ALLOW_IN | F_FUNC_BODY

class SimpleObj:
    """Private attribute adapter; retains custom non-JSON values and nulls."""
    def __init__(self, obj=None):
        if obj is not None:
            fields = obj.items() if isinstance(obj, Mapping) else vars(obj).items()
            for key, value in fields:
                setattr(self, key, value)

    def __getattr__(self, key):
        # Emitters explicitly query optional fields. Do not hide exceptions
        # raised by properties or other existing attributes.
        return None
        
    def __setitem__(self, k, v):
        setattr(self, k, v)
        
    def __getitem__(self, k):
        return getattr(self, k, None)
    
    def __iter__(self):
        return iter(vars(self))
        
    def __contains__(self, k):
        return k in vars(self)
        
    def __len__(self):
        return len(list(self.__iter__()))
    
    def __repr__(self):
        string = '[\n'
        for k in self.__iter__():
            val = self[k]
            if isinstance(val, list):
                length = len(val)
                val = length > 0 and f'[... {length} items]' or '[]'
            elif isinstance(val, (dict, SimpleObj)):
                length = len(val)
                val = length > 0 and '{... ' + f'{length}' + ' items}' or '{}'
            elif isinstance(val, str):
                val = f'\"{val}\"'
            string += '    {' + f'{k}: ' + f'{val}' + '},\n'
        string = (string.endswith(',\n') and string[:-2] or string) + '\n]'
        return string
    
    @staticmethod
    def fromJsonString(string):
        import json as JSON
        return JSON.loads(string, object_hook=SimpleObj)
    
    @staticmethod
    def fromJsonFile(fp):
        import json as JSON
        with open(fp, 'rb') as f:
            return JSON.load(f, object_hook=SimpleObj)
    
    @staticmethod
    def fromDict(obj, hashbangContainers=None):
        memo = {}
        kinds = {}
        nativeFields = {}
        def adapt(value):
            cls = type(value)
            if value is None or cls in (str, int, float, bool):
                return value
            if isinstance(value, (list, tuple)) and (
                    cls is list or cls is tuple or not isinstance(value, Mapping)):
                identity = id(value)
                if identity in memo:
                    return memo[identity]
                result = []
                memo[identity] = result
                result.extend(adapt(item) for item in value)
                return result
            kind = kinds.get(cls)
            if kind is None:
                if cls is dict or isinstance(value, Mapping):
                    kind = 'mapping'
                elif isinstance(value, SimpleObj) or (hasattr(value, '__dict__') and not callable(value)):
                    kind = 'native'
                else:
                    kind = 'opaque'
                kinds[cls] = kind
            if kind != 'opaque':
                identity = id(value)
                if identity in memo:
                    return memo[identity]
                result = SimpleObj()
                memo[identity] = result
                if kind == 'mapping':
                    fields = value.items()
                else:
                    attributes = vars(value)
                    additions = nativeFields.get(cls)
                    if additions is None:
                        additions = {}
                        for base in reversed(cls.__mro__):
                            for key, field in vars(base).items():
                                if not key.startswith('_'):
                                    if not callable(field) and not isinstance(field, (staticmethod, classmethod)):
                                        additions[key] = field
                                    else:
                                        additions.pop(key, None)
                        nativeFields[cls] = additions
                    if additions:
                        attributes = dict(attributes)
                        for key in additions:
                            # Honor subclass descriptors rather than bypassing
                            # a property with a raw instance-dictionary value.
                            attributes[key] = getattr(value, key)
                    fields = attributes.items()
                data = vars(result)
                for key, item in fields:
                    data[key] = adapt(item)
                for canonical, legacy in [('async', 'isAsync'), ('await', 'allowAwait')]:
                    if canonical in data:
                        if legacy in data and data[canonical] != data[legacy]:
                            raise ValueError(f'Conflicting {canonical}/{legacy} AST fields')
                        data[legacy] = data[canonical]
                if data.get('type') == 'FieldDefinition':
                    data['type'] = 'PropertyDefinition'
                if hashbangContainers is not None and any(key in data for key in ('comments', 'leadingComments', 'trailingComments', 'innerComments')):
                    hashbangContainers.append(result)
                return result
            return value
        try:
            return adapt(obj)
        finally:
            memo.clear()
            kinds.clear()
            nativeFields.clear()
            # The recursive closure otherwise retains comment containers
            # (and copied nodes) until cyclic garbage collection runs.
            adapt = None


_UNSAFE_NATIVE_METHODS = frozenset((
    '__class__', '__call__', '__bool__', '__len__', '__eq__', '__ne__', '__hash__',
    '__lt__', '__le__', '__gt__', '__ge__', '__str__', '__format__',
    '__getitem__', '__contains__', '__add__', '__radd__', '__sub__', '__rsub__',
    '__mul__', '__rmul__', '__truediv__', '__rtruediv__', '__mod__', '__rmod__',
    '__and__', '__rand__', '__or__', '__ror__', '__xor__', '__rxor__'))


def _nativeDictionaryIterator(self):
    return iter(self.__dict__)


def _nativeLegacyIterator(self):
    return self.__iter__


def prepareNativeGraph(node, containers):
    """Use ordinary attribute ASTs read-only when no normalization is needed.

    The public adapter remains a snapshot. This internal fast path requires
    plain instance dictionaries, no descriptors or custom attribute reads,
    and a missing-attribute implementation that is exactly ``return None``.
    All fields are inspected so alias conflicts in metadata remain errors.
    """
    scalarTypes = (str, int, float, bool, type(None))
    if type(node) in scalarTypes or type(node) in (dict, list, tuple):
        return False
    classes = {}
    declarations = {}
    seen = {}
    pending = [node]
    pureGetter = SimpleObj.__getattr__.__code__
    pureIterator = _nativeDictionaryIterator.__code__
    legacyIterator = _nativeLegacyIterator.__code__
    while pending:
        value = pending.pop()
        cls = type(value)
        if cls in scalarTypes:
            continue
        identity = id(value)
        if identity in seen:
            continue
        if cls is list:
            before = len(pending)
            for item in value:
                if type(item) not in scalarTypes:
                    pending.append(item)
            if len(pending) != before:
                seen[identity] = None
            continue
        compatible = classes.get(cls)
        if compatible is None:
            getter = None
            attributeGetter = None
            getterFound = attributeGetterFound = False
            for base in cls.__mro__:
                declared = vars(base)
                if not getterFound and '__getattr__' in declared:
                    getter = declared['__getattr__']
                    getterFound = True
                if not attributeGetterFound and '__getattribute__' in declared:
                    attributeGetter = declared['__getattribute__']
                    attributeGetterFound = True
            code = getter.__code__ if type(getter) is FunctionType else None
            compatible = (type(cls) is type and not issubclass(cls, Mapping) and
                          cls.__dictoffset__ != 0 and
                          attributeGetter is object.__getattribute__ and
                          code is not None and code.co_code == pureGetter.co_code and
                          code.co_consts == pureGetter.co_consts and not code.co_freevars and
                          code.co_argcount == 2 and code.co_kwonlyargcount == 0 and
                          not (code.co_flags & 12))
            if compatible:
                for base in cls.__mro__:
                    simple = declarations.get(base)
                    if simple is None:
                        declared = vars(base)
                        dictionary = declared.get('__dict__')
                        simple = ((dictionary is None or type(dictionary) is GetSetDescriptorType) and
                                  (base in (object, SimpleObj) or
                                   not _UNSAFE_NATIVE_METHODS.intersection(declared)) and
                                  not any(not key.startswith('_') and not (
                                      base is SimpleObj or
                                      (key in ('keys', 'items', 'toDict') and callable(field)) or
                                      (key == 'Value' and isinstance(field, type)))
                                      for key, field in declared.items()))
                        iterator = declared.get('__iter__')
                        if simple and iterator is not None and base is not SimpleObj:
                            iteratorCode = iterator.__code__ if type(iterator) is FunctionType else None
                            simple = (iteratorCode is not None and not iteratorCode.co_freevars and
                                      iteratorCode.co_argcount == 1 and
                                      ((iteratorCode.co_code == pureIterator.co_code and
                                        iteratorCode.co_names == pureIterator.co_names and
                                        iteratorCode.co_consts == pureIterator.co_consts and
                                        iterator.__globals__.get('iter', iter) is iter) or
                                       (iteratorCode.co_code == legacyIterator.co_code and
                                        iteratorCode.co_names == legacyIterator.co_names and
                                        iteratorCode.co_consts == legacyIterator.co_consts)))
                        declarations[base] = simple
                    if not simple:
                        compatible = False
                        break
            classes[cls] = compatible
        if not compatible:
            return False
        fields = value.__dict__
        if not fields and not isinstance(value, SimpleObj):
            return False
        nodeType = fields.get('type')
        if nodeType is not None and type(nodeType) is not str:
            return False
        if 'async' in fields:
            if 'isAsync' not in fields:
                return False
            if type(fields['async']) not in scalarTypes or type(fields['isAsync']) not in scalarTypes:
                return False
            if fields['async'] != fields['isAsync']:
                raise ValueError('Conflicting async/isAsync AST fields')
        if 'await' in fields:
            if 'allowAwait' not in fields:
                return False
            if type(fields['await']) not in scalarTypes or type(fields['allowAwait']) not in scalarTypes:
                return False
            if fields['await'] != fields['allowAwait']:
                raise ValueError('Conflicting await/allowAwait AST fields')
        if nodeType in ('FieldDefinition', 'Hashbang') or fields.get('hashbang'):
            return False
        if ('comments' in fields or 'leadingComments' in fields or
                'trailingComments' in fields or 'innerComments' in fields):
            containers.append(value)
        before = len(pending)
        for item in fields.values():
            if type(item) not in scalarTypes:
                pending.append(item)
        if len(pending) != before:
            seen[identity] = True
    _context().nodeTypes.update(cls for cls, compatible in classes.items() if compatible)
    return True
    
def getDefaultOptions():
    # default options
    return SimpleObj({
        'indent': None,
        'base': None,
        'parse': None,
        'comment': False,
        'format': SimpleObj({
            'indent': SimpleObj({
                'style': '    ',
                'base': 0,
                'adjustMultilineComment': False
            }),
            'newline': '\n',
            'space': ' ',
            'json': False,
            'renumber': False,
            'hexadecimal': False,
            'quotes': 'single',
            'escapeless': False,
            'compact': False,
            'parentheses': True,
            'semicolons': True,
            'safeConcatenation': False,
            'preserveBlankLines': False
        }),
        'moz': SimpleObj({
            'comprehensionExpressionStartsWithAssignment': False,
            'starlessGenerator': False
        }),
        'extensions': SimpleObj({'resourceManagement': False, 'decorators': False,
                                  'deferredImportEvaluation': False, 'sourcePhaseImports': False,
                                  'exportDefaultFrom': False}),
        'sourceMap': None,
        'sourceMapRoot': None,
        'sourceMapWithCode': False,
        'directive': False,
        'raw': True,
        'verbatim': None,
        'sourceCode': None
    })

def stringRepeat(string, num):
    result = ''
    num |= 0
    while num > 0:
        if (num & 1):
            result += string
        num >>= 1
        string += string
    return result

def hasLineTerminator(string):
    return bool(re.search('[\r\n\u2028\u2029]', string))

def endsWithLineTerminator(string):
    length = len(string)
    return length and _lineTerminator(ord(string[length - 1]))

def updateDeeply(target, override):

    target = SimpleObj(target) if isinstance(target, dict) else target
    override = SimpleObj(override) if isinstance(override, dict) else override
 
    for key in override:

        val = SimpleObj(override[key]) if isinstance(override[key], dict) else override[key]
        
        if isinstance(val, (SimpleObj, dict)):
        
            if isinstance(target[key], (SimpleObj, dict)):
            
                target[key] = SimpleObj(target[key]) if isinstance(target[key], dict) else target[key]
                updateDeeply(target[key], val)
                
            else:
                target[key] = val
        else:
            target[key] = val
            
    return target

def to_base(n, _base):
    if not isinstance(n, int) or n < 0 or not 2 <= _base <= 36:
        raise ValueError('base conversion requires a nonnegative integer and base 2..36')
    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    result = ''
    while n:
        n, remainder = divmod(n, _base)
        result = digits[remainder] + result
    return result or '0'

def splice(array, start, deleteCount, *items):
    head = array[:start]
    tail = array[start + (deleteCount or 0):]
    items = [i for i in items]
    array.clear()
    if deleteCount is None and not items:
        array.extend(head)
        return array
    array.extend(head + items + tail)
    return array

def generateNumber(value):
    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError('Number literal exceeds binary64; use Literal.bigint for exact integers') from error
    if isinstance(value, int) and not math.isfinite(number):
        raise ValueError('Number literal exceeds binary64; use Literal.bigint for exact integers')
    if isinstance(value, int) and int(number) != value:
        # JSON decoders commonly deliver integers for JS Number spellings.
        # Apply JavaScript's binary64 rounding; BigInt is the exact API.
        value = number
    if math.isnan(number):
        raise ValueError('Number literal cannot be NaN')
    if math.isinf(number):
        return 'null' if _context().json else ('-' if number < 0 else '') + '1e400'
    if number == 0 and math.copysign(1, number) < 0:
        return '-0'
    result = str(value)
    if not _context().renumber:
        return result
    candidates = {result.replace('e+', 'e')}
    if '.' in result and 'e' not in result.lower():
        trimmed = result.rstrip('0').rstrip('.')
        candidates.add(trimmed)
        if not _context().json:
            candidates.add(trimmed.replace('0.', '.', 1) if abs(number) < 1 else trimmed)
    if number.is_integer() and number != 0:
        decimal = str(abs(int(number)))
        stem = decimal.rstrip('0')
        zeros = len(decimal) - len(stem)
        if zeros:
            candidates.add(('-' if number < 0 else '') + stem + 'e' + str(zeros))
        if _context().hexadecimal and not _context().json:
            candidates.add(('-' if number < 0 else '') + hex(abs(int(number))))
    # Candidate spellings must round-trip to the same binary64 value.
    def equivalent(candidate):
        try:
            actual = float(int(candidate, 16)) if 'x' in candidate else float(candidate)
            return actual == number
        except (ValueError, OverflowError):
            return False
    return min((candidate for candidate in candidates if equivalent(candidate)), key=lambda text: (len(text), text))


def decodeRawNumber(raw):
    """Validate Number-literal spelling locally for tagged interchange values."""
    if not isinstance(raw, str):
        raise ValueError('Tagged Number raw spelling must be a string')
    digits = r'[0-9](?:_?[0-9])*'
    decimal = rf'[+-]?(?:{digits}(?:\.(?:{digits})?)?|\.{digits})(?:[eE][+-]?{digits})?'
    if re.fullmatch(decimal, raw):
        return float(raw.replace('_', ''))
    for base, prefix, characters in [(16, 'xX', '0-9a-fA-F'), (8, 'oO', '0-7'), (2, 'bB', '01')]:
        if re.fullmatch(rf'[+-]?0[{prefix}][{characters}](?:_?[{characters}])*', raw):
            cleaned = raw.replace('_', '')
            try:
                return float(int(cleaned, base))
            except OverflowError:
                return -math.inf if cleaned.startswith('-') else math.inf
    raise ValueError('Tagged Number raw spelling must be a numeric literal')


def jsxTextValue(raw):
    import html
    # HTML4 references, with semicolons, are the JSX interchange contract.
    # Normalize physical CRLF before decoding so &#13;&#10; remains two units.
    def entity(match):
        text = match.group(1)
        if text.startswith('#'):
            try:
                point = int(text[2:], 16) if text.startswith('#x') else int(text[1:])
            except ValueError:
                return match.group(0)
            return chr(point) if 0 <= point <= 0x10ffff else match.group(0)
        return html.entities.entitydefs.get(text, match.group(0))
    return re.sub(r'&(#x[0-9A-Fa-f]+|#[0-9]+|[A-Za-z][A-Za-z0-9]*);', entity, raw.replace('\r\n', '\n'))


def escapeJSXString(value, attribute=False):
    import html
    if not isinstance(value, str):
        raise ValueError('JSX text and literal attribute values must be strings')
    escaped = html.escape(value, quote=attribute)
    result = []
    for character in escaped:
        code = ord(character)
        if code < 0x20 or 0xd800 <= code <= 0xdfff or code in (0x2028, 0x2029):
            result.append(f'&#x{code:X};')
        elif not attribute and character in '{}':
            result.append(f'&#{code};')
        else:
            result.append(character)
    return ''.join(result)
    
# Generate valid RegExp expression.
# This function is based on https://github.com/Constellation/iv Engine

class RegExp(SimpleObj):
    
    def __init__(self, regex_str):
        
        if not isinstance(regex_str, str) or not regex_str.startswith('/'):
            raise ValueError('Legacy regex values must be JavaScript /pattern/flags strings')
        end = regex_str.rfind('/')
        if end == 0:
            raise ValueError('Legacy regex value is missing its closing slash')
        _pattern, _flags = regex_str[1:end], regex_str[end + 1:]
        validateRegExpFlags(_flags)
        self.regex = SimpleObj({
            'pattern': _pattern,
            'flags': _flags
        })
        self.raw = regex_str
        
    def toString(self):
        return '/' + self.regex.pattern + '/' + (self.regex.flags)
        
    @property
    def source(self):
        return self.regex.pattern
        
    @property
    def flags(self):
        return self.regex.flags


def validateRegExpFlags(flags):
    if not isinstance(flags, str) or len(set(flags)) != len(flags) or any(flag not in 'dgimsuvy' for flag in flags) or ('u' in flags and 'v' in flags):
        raise ValueError('Invalid ECMAScript regular-expression flags')

def escapeRegExpCharacter(ch, previousIsBackslash):
    if (ch & ~1) == 0x2028:
        return ('u' if previousIsBackslash else '\\u') + ('2028' if ch == 0x2028 else '2029')
    elif ch == 10 or ch == 13:
        return ('' if previousIsBackslash else '\\') + ('n' if ch == 10 else 'r')
    return chr(ch)

def generateRegExp(reg):

    # if '\\' in reg:
        # reg = fr'{reg}'
        # reg =  re.compile(r'\\').sub(r'\\\\', reg)
    
    reg = RegExp(reg)
    result = reg.toString() # Is regex pattern?
    
    if reg.source:
        # extract flag from toString result
        match = re.compile(r'/([^/]*)$').search(result)
        if not bool(match):
            return result
        
        flags = match.group(1)
        result = ''
        
        characterInBrack = False
        previousIsBackslash = False
        
        i = 0
        iz = len(reg.source)
        for i in range(iz):
            ch = ord(reg.source[i])
            if not previousIsBackslash:
                if characterInBrack:
                    if ch == 93: # ]
                        characterInBrack = False
                else:
                    if ch == 47: # /
                        result += '\\'
                    elif ch == 91: # [
                        characterInBrack = True
                result += escapeRegExpCharacter(ch, previousIsBackslash)
                previousIsBackslash = ch == 92 # \
            else:
                # if new RegExp("\\\n') is provided, create /\n/
                result += escapeRegExpCharacter(ch, previousIsBackslash)
                # prevent like /\\[/]/
                previousIsBackslash = False
        return '/' + result + '/' + flags
    
    return result

def escapeAllowedCharacter(code, nextChar):

    if code == 0x08: # \b
        return '\\b'
        
    if code == 0x0c: # \f
        return '\\f'
        
    if code == 0x09: # \t
        return '\\t'
        
    if code > 0xffff:
        scalar = code - 0x10000
        return '\\u%04X\\u%04X' % (0xd800 + (scalar >> 10), 0xdc00 + (scalar & 0x3ff))
    _hex = format(code, 'X')
    if (_context().json or code > 0xff):
        return '\\u' + '0000'[len(_hex):] + _hex
    elif code == 0x0000 and not _decimalDigit(nextChar if not nextChar is None else 0x00):
        return '\\0'
    elif code == 0x000b: # \v
        return '\\x0b'
    else:
        return '\\x' + '00'[len(_hex):] + _hex

def escapeDisallowedCharacter(code):
    if code == 0x5c: # \
        return '\\\\'
    
    if code == 0x0a: # \n
        return '\\n'
        
    if code == 0x0d: # \r
        return '\\r'
        
    if code == 0x2028:
        return '\\u2028'
        
    if code == 0x2029:
        return '\\u2029'
    
    raise Exception('Incorrectly classified character')

def escapeDirective(string):
    
    quote = '"' if _context().quotes == 'double' else '\''
    iz = len(string)
    i = 0
    while i < iz:
        code = ord(string[i])
        if code == 0x27: # '
            quote = '"'
            break
        elif code == 0x22: # "
            quote = '\''
            break
        elif code == 0x5c: # \
            i += 1
        i += 1
    
    return quote + string + quote

def escapeString(string):
    single = not (_context().json or _context().quotes == 'double' or
                  (_context().quotes == 'auto' and string.count('"') < string.count("'")))
    quote = "'" if single else '"'
    result = [quote]
    for i, character in enumerate(string):
        code = ord(character)
        if character == quote:
            result.append('\\' + character)
        elif code == 0x5c or _lineTerminator(code):
            result.append(escapeDisallowedCharacter(code))
        elif code < 0x20 or 0xd800 <= code <= 0xdfff or (
                not _context().json and not _context().escapeless and code > 0x7e and
                not _identifierPart(code)):
            nextChar = ord(string[i + 1]) if i + 1 < len(string) else None
            result.append(escapeAllowedCharacter(code, nextChar))
        elif _context().json and character == '/':
            result.append('\\/')
        else:
            result.append(character)
    result.append(quote)
    return ''.join(result)

"""
 * flatten an array to a string, where the array can contain
 * either strings or nested arrays
"""
def flattenToString(arr):
    result = []
    for i in arr:
        result.append((flattenToString(i) if type(i) == list else i) or '')
    return ''.join(result)
"""
 * convert generated to a SourceNode when source maps are enabled.
"""
def toSourceNodeWhenNeeded(generated, node=None, toString=False):
    if not _context().sourceMap:
        # with no source maps, generated is either an
        # array or a string.  if an array, flatten it.
        # if a string, just return it
        if isinstance(generated, list):
            return flattenToString(generated)
        else:
            return generated
    
    if node is None:
        if isinstance(generated, SourceNode):
            return generated.toString() if toString else generated
        else:
            node = SimpleObj()
            
    if node.loc is None:
        sn = SourceNode(None, None, None, generated, node.name or None)
    else:
        if node.loc.start is None:
            raise ValueError('source-map loc must contain a start position')
        sn = SourceNode(node.loc.start.line, node.loc.start.column, (node.loc.source or 'source.js') if _context().sourceMap == True else _context().sourceMap, generated, node.name or None)
    return sn.toString() if toString else sn

def noEmptySpace():
    return _context().space if _context().space else ' '

def join(left, right):
    
    leftSource = toSourceNodeWhenNeeded(left, toString=True)
    if (len(leftSource) == 0):
        return [right]
    
    rightSource = toSourceNodeWhenNeeded(right, toString=True)
    if len(rightSource) == 0:
        return [left]
    
    leftCharCode = ord(leftSource[len(leftSource) - 1])
    rightCharCode = ord(rightSource[0])
    
    if ((leftCharCode == 0x2b or leftCharCode == 0x2d) and leftCharCode == rightCharCode or
        _identifierPart(leftCharCode) and _identifierPart(rightCharCode) or
        leftCharCode == 0x2f and rightCharCode == 0x69):
        return [left, noEmptySpace(), right]
    elif (_whiteSpace(leftCharCode) or _lineTerminator(leftCharCode) or
            _whiteSpace(rightCharCode) or _lineTerminator(rightCharCode)):
        return [left, right]
    return [left, _context().space, right]
    
def addIndent(stmt):
    return [_context().base, stmt]

def withIndent(func):
    previousBase = _context().base
    _context().base += _context().indent
    try:
        func(_context().base)
    finally:
        _context().base = previousBase

def calculateSpaces(string):
    i = len(string) - 1
    while i >= 0:
        if _lineTerminator(ord(string[i])):
            break
        i -= 1
    return (len(string) - 1) - i


class UTF16Source:
    """Source slicing uses ESTree offsets, measured in UTF-16 code units."""
    def __init__(self, source):
        if not isinstance(source, str):
            raise TypeError('sourceCode must be a string')
        self.data = source.encode('utf-16-le', 'surrogatepass')

    def __len__(self):
        return len(self.data) // 2

    def validate(self, start, end):
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start <= end <= len(self):
            raise ValueError('source ranges require ordered UTF-16 offsets within sourceCode')
        for offset in (start, end):
            if 0 < offset < len(self):
                before = int.from_bytes(self.data[2 * offset - 2:2 * offset], 'little')
                after = int.from_bytes(self.data[2 * offset:2 * offset + 2], 'little')
                if 0xd800 <= before <= 0xdbff and 0xdc00 <= after <= 0xdfff:
                    raise ValueError('source range splits a UTF-16 surrogate pair')

    def __getitem__(self, key):
        if isinstance(key, slice):
            start = 0 if key.start is None else key.start
            end = len(self) if key.stop is None else key.stop
            self.validate(start, end)
            if key.step is not None:
                raise ValueError('source slices do not support steps')
            return self.data[2 * start:2 * end].decode('utf-16-le', 'surrogatepass')
        if not isinstance(key, int) or not 0 <= key < len(self):
            raise ValueError('source index is outside sourceCode')
        return self.data[2 * key:2 * key + 2].decode('utf-16-le', 'surrogatepass')


def validateSourceRanges(node):
    seen = set()
    def visit(value):
        if type(value) in _context().nodeTypes:
            if id(value) in seen:
                return
            seen.add(id(value))
            for field in ('range', 'extendedRange'):
                span = getattr(value, field)
                if span is not None:
                    if not isinstance(span, list) or len(span) != 2:
                        raise ValueError(f'{field} must contain two UTF-16 offsets')
                    _context().sourceCode.validate(*span)
            for item in vars(value).values():
                visit(item)
        elif isinstance(value, list):
            if id(value) in seen:
                return
            seen.add(id(value))
            for item in value:
                visit(item)
    visit(node)


def extractHashbang(node, containers):
    hashbang = node.hashbang if node.type == Syntax.Program else None
    for value in containers:
        for key in ('comments', 'leadingComments', 'trailingComments', 'innerComments'):
            comments = getattr(value, key)
            if comments:
                marked = False
                for comment in comments:
                    if comment.hashbang or comment.type == 'Hashbang':
                        text = comment.value.removeprefix('#!')
                        if hashbang is not None and hashbang != text:
                            raise ValueError('Conflicting Program/comment hashbang metadata')
                        hashbang = text
                        marked = True
                if marked:
                    value[key] = [comment for comment in comments if not comment.hashbang and comment.type != 'Hashbang']
    if hashbang is not None and (not isinstance(hashbang, str) or hasLineTerminator(hashbang)):
        raise ValueError('Program.hashbang must contain one line excluding #!')
    return hashbang

def adjustMultilineComment(value, specialBase):
    
    array = re.compile('\r\n|[\r\n]').split(value)
    spaces = 1.7976931348623157e+308
    
    # first line doesn't have indentation
    i = 1
    while i < len(array):
        line = array[i]
        j = 0
        while j < len(line) and _whiteSpace(ord(line[j])):
            j += 1
        if spaces > j:
            spaces = j
        i += 1
    
    if not specialBase is None:
        # pattern like
        # {
        #   var t = 20;  /*
        #                 * this is comment
        #                 */
        # }
        previousBase = _context().base
        if len(array[1]) > spaces and array[1][spaces] == '*':
            specialBase += ' '
        _context().base = specialBase
    else:
        if (spaces & 1):
            # /*
            #  *
            #  */
            # If spaces are odd number, above pattern is considered.
            # We waste 1 space.
            spaces -= 1
        previousBase = _context().base
    
    i = 1
    while i < len(array):
        sn = toSourceNodeWhenNeeded(addIndent(array[i][spaces:]))
        array[i] = sn.toString() if _context().sourceMap else sn
        i += 1
        
    _context().base = previousBase
    
    return '\n'.join(array)
    
def generateComment(comment, specialBase=None):
    if comment.type not in ('Line', 'Block') or not isinstance(comment.value, str):
        raise ValueError('Comments require a Line/Block type and string value')
    if comment.type == 'Block' and '*/' in comment.value:
        raise ValueError('Block comment value cannot contain its closing delimiter')
    if comment.type == 'Line' and hasLineTerminator(comment.value.rstrip('\r\n\u2028\u2029')):
        raise ValueError('Line comment value cannot contain an internal line terminator')
    if comment.type == 'Line':
        if endsWithLineTerminator(comment.value):
            return '//' + comment.value
        else:
            result = '//' + comment.value
            if not _context().preserveBlankLines:
                result += '\n'
            return result
    if _context().extra.format.indent.adjustMultilineComment and bool(re.compile("[\n\r]").search(comment.value)):
        return adjustMultilineComment('/*' + comment.value + '*/', specialBase)
    return '/*' + comment.value + '*/';

def addComments(stmt, result):

    if not isinstance(result, list):
        result = [result]

    if stmt.leadingComments and len(stmt.leadingComments) > 0:

        save = result
        
        inline = (not _context().preserveBlankLines and isExpression(stmt) and
                  all(comment.type == 'Block' and not hasLineTerminator(comment.value)
                      for comment in stmt.leadingComments))
        if inline:
            result = [[generateComment(comment), ' '] for comment in stmt.leadingComments]
        elif _context().preserveBlankLines:
            comment = stmt.leadingComments[0]
            result = []
        
            extRange = comment.extendedRange or comment.range
            _range = comment.range
            
            prefix = _context().sourceCode[extRange[0]:_range[0]]
            count = len(re.compile('\n').findall(prefix) or [])
            if count > 0:
                result.append(stringRepeat('\n', count))
                result.append(addIndent(generateComment(comment)))
            else:
                result.append(prefix)
                result.append(generateComment(comment))
            
            prevRange = _range
            previousComment = comment
        
            i = 1
            while i < len(stmt.leadingComments):
                comment = stmt.leadingComments[i]
                _range = comment.range
                
                infix = _context().sourceCode[prevRange[1]:_range[0]]
                count = len(re.compile('\n').findall(infix) or [])
                if count == 0 and previousComment.type == 'Line' and not endsWithLineTerminator(previousComment.value):
                    count = 1
                result.append(stringRepeat('\n', count))
                result.append(addIndent(generateComment(comment)))

                prevRange = _range
                previousComment = comment
                i += 1

            extRange = comment.extendedRange or comment.range
            suffix = _context().sourceCode[_range[1]:extRange[1]]
            count = len(re.compile('\n').findall(suffix) or [])
            if count == 0 and comment.type == 'Line' and not endsWithLineTerminator(comment.value):
                count = 1
            result.append(stringRepeat('\n', count))
        else:
            comment = stmt.leadingComments[0]
            result = []
            if _context().safeConcatenation and stmt.type == Syntax.Program and len(stmt.body) == 0:
                result.append('\n')
            result.append(generateComment(comment))
            if not endsWithLineTerminator(toSourceNodeWhenNeeded(result, toString=True)):
                result.append('\n')
            
            for i in range(1, len(stmt.leadingComments)):
                comment = stmt.leadingComments[i]
                fragment = [generateComment(comment)]
                if not endsWithLineTerminator(toSourceNodeWhenNeeded(fragment, toString=True)):
                    fragment.append('\n')
                result.append(addIndent(fragment))
        
        result.append(save if inline else addIndent(save))
    
    if stmt.trailingComments:
        
        if _context().preserveBlankLines:
            previous_end = None
            for comment in stmt.trailingComments:
                extRange = comment.extendedRange or comment.range
                _range = comment.range
                prefix = _context().sourceCode[extRange[0] if previous_end is None else previous_end:_range[0]]
                count = len(re.compile('\n').findall(prefix) or [])
                if count > 0:
                    result.append(stringRepeat('\n', count))
                    result.append(addIndent(generateComment(comment)))
                else:
                    result.append(prefix)
                    result.append(generateComment(comment))
                previous_end = _range[1]
        else:
            tailingToStatement = not endsWithLineTerminator(toSourceNodeWhenNeeded(result, toString=True))
            specialBase = stringRepeat(' ', calculateSpaces(toSourceNodeWhenNeeded([_context().base, result, _context().indent], toString=True)))
            length = len(stmt.trailingComments)
            for i in range(length):
                comment = stmt.trailingComments[i]
                if tailingToStatement:
                    # We assume target like following script
                    #
                    # var t = 20;  /**
                    #               * This is comment of t
                    #               */
                    if i == 0:
                        # first case
                        result = [result, _context().indent]
                    else:
                        result = [result, specialBase]
                    result.append(generateComment(comment, specialBase))
                else:
                    result = [result, addIndent(generateComment(comment))]
                if i != length - 1 and not endsWithLineTerminator(toSourceNodeWhenNeeded(result, toString=True)):
                    result = [result, '\n']

    return result
            
def generateBlankLines(start, end, result):
    _context().sourceCode.validate(start, end)
    newlineCount = 0
    
    for j in range(start, end):
        if _context().sourceCode[j] == '\n':
            newlineCount += 1
    
    for j in range(1, newlineCount):
        result.append(_context().newline)

def parenthesize(text, current, should):
    if current < should:
        return ['(', text, ')']
    return text

def generateVerbatimString(string):
    result = re.compile('\r\n|\n').split(string)
    for i in range(1, len(result)):
        result[i] = _context().newline + _context().base + result[i]
    return result

def generateVerbatim(expr, precedence):
    verbatim = getattr(expr, _context().extra.verbatim)
    if isinstance(verbatim, str):
        result = parenthesize(generateVerbatimString(verbatim), Precedence.Sequence, precedence)
    else:
        # verbatim is object
        result = generateVerbatimString(verbatim.content)
        prec = verbatim.precedence if not verbatim.precedence is None else Precedence.Sequence
        result = parenthesize(result, prec, precedence)
        
    return toSourceNodeWhenNeeded(result, expr)

def generateIdentifier(node):
    name = node.name
    exact = type(name) is str
    known = _context().identifierNames
    if not exact or name not in known:
        if exact and name.isascii():
            valid = _asciiIdentifier(name) is not None
        else:
            valid = (isinstance(name, str) and bool(name) and _identifierStart(ord(name[0])) and
                     all(_identifierPart(ord(character)) for character in name[1:]))
        if not valid:
            raise ValueError('Identifier.name must be a valid ECMAScript IdentifierName')
        if exact:
            known.add(name)
    return toSourceNodeWhenNeeded(('#' if node.type == 'PrivateIdentifier' else '') + name, node)

def generateAsyncPrefix(node, spaceRequired):
    return 'async' + (noEmptySpace() if spaceRequired else _context().space) if node.isAsync else ''

def generateStarSuffix(node):
    isGenerator = node.generator and not _context().extra.moz.starlessGenerator
    return '*' + _context().space if isGenerator else ''

def generateMethodPrefix(prop):
    func = prop.value
    prefix = ''
    if func.isAsync:
        prefix += generateAsyncPrefix(func, not prop.computed)
    if func.generator:
        prefix += '*' if generateStarSuffix(func) else ''
    return prefix

def generateInternal(node):

    if type(node) not in _context().nodeTypes or not isinstance(node.type, str):
        raise ValueError('Expected an ESTree node with a string type field')

    codegen = CodeGenerator()
    
    if isStatement(node):
        return codegen.generateStatement(node, S_TFFF)

    if isExpression(node):
        return codegen.generateExpression(node, Precedence.Sequence, E_TTT)

    raise ValueError('Unsupported ESTree node type: ' + node.type)

def _generate(node, options=None):

    defaultOptions = getDefaultOptions()
    
    if not options is None:
        # Obsolete options
        #
        #   `options.indent`
        #   `options.base`
        #
        # Instead of them, we can use `option.format.indent`.
        if isinstance(options, dict):
            options = SimpleObj.fromDict(options)

        if isinstance(options.indent, str):
            defaultOptions.format.indent.style = options.indent

        if isinstance(options.base, int):
            defaultOptions.format.indent.base = options.base
        options = updateDeeply(defaultOptions, options)

        _context().indent = options.format.indent.style
        if isinstance(options.base, str):
            _context().base = options.base
        else:
            _context().base = stringRepeat(_context().indent, options.format.indent.base)
    
    else:
        options = defaultOptions
        _context().indent = options.format.indent.style
        _context().base = stringRepeat(_context().indent, options.format.indent.base)
    
    _context().json = options.format.json
    _context().renumber = options.format.renumber
    _context().hexadecimal = False if _context().json else options.format.hexadecimal
    _context().quotes = 'double' if _context().json else options.format.quotes
    _context().escapeless = options.format.escapeless
    _context().newline = options.format.newline
    _context().space = options.format.space

    if options.format.compact:
        _context().newline = _context().space = _context().indent = _context().base = ''
        
    _context().parentheses = options.format.parentheses
    _context().semicolons = options.format.semicolons
    _context().safeConcatenation = options.format.safeConcatenation
    _context().directive = options.directive
    _context().parse = None if _context().json else options.parse
    _context().sourceMap = options.sourceMap
    if options.sourceMap is not None and not isinstance(options.sourceMap, (str, bool)):
        raise ValueError('sourceMap must be a source filename, boolean or None')
    _context().sourceCode = UTF16Source(options.sourceCode) if options.sourceCode is not None else None
    
    _context().preserveBlankLines = options.format.preserveBlankLines and not _context().sourceCode is None

    if options.format.quotes not in ('single', 'double', 'auto'):
        raise ValueError('format.quotes must be single, double or auto')
    for field in ('space', 'newline'):
        if not isinstance(options.format[field], str):
            raise TypeError(f'format.{field} must be a string')
    if not isinstance(options.format.indent.style, str) or not isinstance(options.format.indent.base, int) or options.format.indent.base < 0:
        raise ValueError('format.indent requires a string style and nonnegative integer base')

    _context().extra = options

    hashbangContainers = []
    if _context().parse is not None or _context().extra.verbatim or not prepareNativeGraph(node, hashbangContainers):
        hashbangContainers.clear()
        node = SimpleObj.fromDict(node, hashbangContainers)
    if _context().preserveBlankLines:
        validateSourceRanges(node)
    hashbang = extractHashbang(node, hashbangContainers)
    
    result = generateInternal(node)
    if hashbang is not None:
        result = ['#!' + hashbang + '\n', result]
        result = toSourceNodeWhenNeeded(result)
    
    if not _context().sourceMap:
        pair = SimpleObj({'code': result, 'map': None}) # result.toString()
        return pair if options.sourceMapWithCode else pair.code
    
    pair = result.toStringWithSourceMap(SimpleObj({
        'file': options.file,
        'sourceRoot': options.sourceMapRoot
    }))
    
    if options.sourceContent is not None:
        if isinstance(options.sourceMap, str):
            pair.map.setSourceContent(options.sourceMap, options.sourceContent)
        elif options.sourceMap is True:
            for source in pair.map.toJSON()['sources']:
                pair.map.setSourceContent(source, options.sourceContent)
    
    if options.sourceMapWithCode:
        return pair

    return pair.map.toString()

# Statements.

class CodeGeneratorStatement:
    
    def BlockStatement(self, stmt, flags):
        if not stmt.body and _context().preserveBlankLines:
            return self.preservedEmptyContainer(stmt, '{', '}')
        _range = None
        content = None
        result = ['{', _context().newline]
        that = self
        def fn(*args, **kwargs):
            nonlocal result
            if len(stmt.body) == 0 and _context().preserveBlankLines:
                _range = stmt.range
                if _range[1] - _range[0] > 2:
                    content = _context().sourceCode[_range[0] + 1:_range[1] - 1]
                    if content.startswith('\n'):
                        result.clear()
                        result = ['{']

                    result.append(content)

            if (_context().extra.comment and stmt.innerComments and
                    not (len(stmt.body) == 0 and _context().preserveBlankLines)):
                for comment in stmt.innerComments:
                    fragment = toSourceNodeWhenNeeded(addIndent(generateComment(comment)), comment)
                    result.append(fragment)
                    if not endsWithLineTerminator(toSourceNodeWhenNeeded(fragment, toString=True)):
                        result.append(_context().newline)
         
            bodyFlags = S_TFFF
            if flags & F_FUNC_BODY:
                bodyFlags |= F_DIRECTIVE_CTX
            
            i = 0
            iz = len(stmt.body)
            while i < iz:
                if _context().preserveBlankLines:
                    # handle spaces before the first line
                    if i == 0:
                        if stmt.body[0].leadingComments:
                            _range = stmt.body[0].leadingComments[0].extendedRange
                            content = _context().sourceCode[_range[0]:_range[1]]
                            if content.startswith('\n'):
                                result.clear()
                                result = ['{']

                        if not stmt.body[0].leadingComments:
                            generateBlankLines(stmt.range[0], stmt.body[0].range[0], result)

                    # handle spaces between lines
                    if i > 0:
                        if not stmt.body[i - 1].trailingComments and not stmt.body[i].leadingComments:
                            generateBlankLines(stmt.body[i - 1].range[1], stmt.body[i].range[0], result)

                if i == iz - 1:
                    bodyFlags |= F_SEMICOLON_OPT

                if stmt.body[i].leadingComments and _context().preserveBlankLines:
                    fragment = that.generateStatement(stmt.body[i], bodyFlags)
                else:
                    fragment = addIndent(that.generateStatement(stmt.body[i], bodyFlags))

                result.append(fragment)
                
                if not endsWithLineTerminator(toSourceNodeWhenNeeded(fragment, toString=True)):

                    if (_context().preserveBlankLines and i < iz - 1):
                        # don't add a new line if there are leading coments
                        # in the next statement
                        if not stmt.body[i + 1].leadingComments:
                            result.append(_context().newline)
                    else:
                        result.append(_context().newline)

                if _context().preserveBlankLines:
                    # handle spaces after the last line
                    if i == iz - 1:
                        if not stmt.body[i].trailingComments:
                            generateBlankLines(stmt.body[i].range[1], stmt.range[1], result)
                
                i += 1
            
        withIndent(fn)
        result.append(addIndent('}'))
        return result
    
    def BreakStatement(self, stmt, flags):
        if stmt.label:
            return 'break ' + stmt.label.name + self.semicolon(flags)

        return 'break' + self.semicolon(flags)
    
    def ContinueStatement(self, stmt, flags):
        if stmt.label:
            return 'continue ' + stmt.label.name + self.semicolon(flags)

        return 'continue' + self.semicolon(flags)
    
    def ClassBody(self, stmt, flags):
        if not stmt.body and _context().preserveBlankLines:
            return self.preservedEmptyContainer(stmt, '{', '}')
        if not stmt.body and _context().extra.comment and stmt.innerComments:
            return self.emptyContainer(stmt, '{', '}')
        result = [ '{', _context().newline]
        that = self
        
        def fn(indent, *args, **kwargs):
            nonlocal result
            iz = len(stmt.body)
            for i in range(iz):
                result.append(indent)
                result.append(that.generateExpression(stmt.body[i], Precedence.Sequence, E_TTT))
                if i + 1 < iz:
                    result.append(_context().newline)
                    
        withIndent(fn)

        if not endsWithLineTerminator(toSourceNodeWhenNeeded(result, toString=True)):
            result.append(_context().newline)

        result.append(_context().base)
        result.append('}')
        return result
    
    def ClassDeclaration(self, stmt, flags):
        result = [self.generateDecorators(stmt), 'class']
        if stmt.id:
            result = join(result, self.generateExpression(stmt.id, Precedence.Sequence, E_TTT))
        
        if stmt.superClass:
            fragment = join('extends', self.generateExpression(stmt.superClass, Precedence.Unary, E_TTT))
            result = join(result, fragment)

        result.append(_context().space)
        result.append(self.generateStatement(stmt.body, S_TFFT))
        return result
    
    def DirectiveStatement(self, stmt, flags):
        if _context().extra.raw and stmt.raw:
            return stmt.raw + self.semicolon(flags)

        return escapeDirective(stmt.directive) + self.semicolon(flags)
        
    def DoWhileStatement(self, stmt, flags):
        # Because `do 42 while (cond)` is Syntax Error. We need semicolon.
        result = join('do', self.maybeBlock(stmt.body, S_TFFF))
        result = self.maybeBlockSuffix(stmt.body, result)
        return join(result, [
            'while' + _context().space + '(',
            self.generateExpression(stmt.test, Precedence.Sequence, E_TTT),
            ')' + self.semicolon(flags)
        ])
        
    def CatchClause(self, stmt, flags):
        result = []
        that = self
        
        def fn(*args, **kwargs):
            nonlocal result
            if stmt.param:
                result = [
                    'catch' + _context().space + '(',
                    that.generateExpression(stmt.param, Precedence.Sequence, E_TTT),
                    ')'
                ]
                if stmt.guard:
                    guard = that.generateExpression(stmt.guard, Precedence.Sequence, E_TTT)
                    splice(result, 2, 0, ' if ', guard)
            else:
                result = ['catch']

        withIndent(fn)
        result.append(self.maybeBlock(stmt.body, S_TFFF))
        return result
        
    def DebuggerStatement(self, stmt, flags):
        return 'debugger' + self.semicolon(flags)
        
    def EmptyStatement(self, stmt, flags):
        return ';'
        
    def ExportDefaultDeclaration(self, stmt, flags):
        result = [ 'export' ]
        
        bodyFlags = S_TFFT if (flags & F_SEMICOLON_OPT) else S_TFFF
        
        # export default HoistableDeclaration[Default]
        # export default AssignmentExpression[In] 
        result = join(result, 'default')
        if isStatement(stmt.declaration):
            result = join(result, self.generateStatement(stmt.declaration, bodyFlags))
        else:
            result = join(result, self.generateExpression(stmt.declaration, Precedence.Assignment, E_TTT) + self.semicolon(flags))

        return result
        
    def ExportNamedDeclaration(self, stmt, flags):
        result = [ 'export' ]
        that = self
        
        bodyFlags = S_TFFT if (flags & F_SEMICOLON_OPT) else S_TFFF
        
        # export VariableStatement
        # export Declaration[Default]
        if stmt.declaration:
            return join(result, self.generateStatement(stmt.declaration, bodyFlags))

        special = [specifier for specifier in stmt.specifiers or []
                   if specifier.type in (Syntax.ExportDefaultSpecifier, Syntax.ExportNamespaceSpecifier)]
        if special:
            if stmt.source is None:
                raise ValueError('Default/namespace re-export specifiers require a source')
            defaults = [specifier for specifier in special if specifier.type == Syntax.ExportDefaultSpecifier]
            namespaces = [specifier for specifier in special if specifier.type == Syntax.ExportNamespaceSpecifier]
            if (len(defaults) > 1 or len(namespaces) > 1 or
                    (defaults and stmt.specifiers[0] is not defaults[0]) or
                    (namespaces and len(stmt.specifiers) != len(defaults) + 1)):
                raise ValueError('Default re-export must be first and namespace re-exports cannot mix with named specifiers')
            cursor = 0
            if defaults:
                result = join(result, self.generateExpression(defaults[0], Precedence.Sequence, E_TTT))
                cursor = 1
            if namespaces:
                if cursor:
                    result.append(',' + _context().space)
                result = join(result, self.generateExpression(namespaces[0], Precedence.Sequence, E_TTT))
            elif cursor < len(stmt.specifiers):
                result.append(',' + _context().space + '{' + _context().space)
                for index, specifier in enumerate(stmt.specifiers[cursor:]):
                    if specifier.type != Syntax.ExportSpecifier:
                        raise ValueError('Unsupported named re-export specifier: ' + specifier.type)
                    if index:
                        result.append(',' + _context().space)
                    result.append(self.generateExpression(specifier, Precedence.Sequence, E_TTT))
                result.append(_context().space + '}')
            return join(result, ['from' + _context().space,
                                 self.generateExpression(stmt.source, Precedence.Sequence, E_TTT),
                                 self.generateImportAttributes(stmt), self.semicolon(flags)])
        
        # export ExportClause[NoReference] FromClause 
        # export ExportClause 
        if stmt.specifiers is not None:
            if len(stmt.specifiers) == 0:
                result = join(result, '{' + _context().space + '}')
            else:
                result = join(result, '{')
                
                def fn(indent, *args, **kwargs):
                    nonlocal result
                    result.append(_context().newline)
                    iz = len(stmt.specifiers)
                    for i in range(iz):
                        result.append(indent)
                        result.append(that.generateExpression(stmt.specifiers[i], Precedence.Sequence, E_TTT))
                        if i + 1 < iz:
                            result.append(',' + _context().newline)

                withIndent(fn)
                
                if not endsWithLineTerminator(toSourceNodeWhenNeeded(result, toString=True)):
                    result.append(_context().newline)

                result.append(_context().base + '}')

            if stmt.source:
                result = join(result, [
                    'from' + _context().space,
                    # ModuleSpecifier
                    self.generateExpression(stmt.source, Precedence.Sequence, E_TTT),
                    self.generateImportAttributes(stmt),
                    self.semicolon(flags)
                ])
            else:
                result.append(self.semicolon(flags))

        return result
        
    def ExportAllDeclaration(self, stmt, flags):
        # export * FromClause 
        return [
            'export' + _context().space,
            '*' + _context().space,
            ['as', noEmptySpace(), self.generateExpression(stmt.exported, Precedence.Primary, E_TTT), noEmptySpace()] if stmt.exported else '',
            'from' + _context().space,
            # ModuleSpecifier
            self.generateExpression(stmt.source, Precedence.Sequence, E_TTT),
            self.generateImportAttributes(stmt),
            self.semicolon(flags)
        ]
        
    def ExpressionStatement(self, stmt, flags):

        def isClassPrefixed(fragment):
            if len(fragment) <= 5 or fragment[0:5] != 'class':
                return False
            code = ord(fragment[5])
            return (code == 0x7b or # '{'
                    _whiteSpace(code) or
                    _lineTerminator(code))
            
        def isFunctionPrefixed(fragment):
            if len(fragment) <= 8 or fragment[0:8] != 'function':
                return False
            code = ord(fragment[8])
            return (code == 0x28 or # '('
                    _whiteSpace(code) or
                    code == 0x2a or # '*'
                    _lineTerminator(code))

        def isAsyncPrefixed(fragment):
            
            if len(fragment) <= 5 or fragment[0:5] != 'async':
                return False

            if not _whiteSpace(ord(fragment[5])):
                return False
            
            i = 6
            iz = len(fragment)
            while i < iz:
                if not _whiteSpace(ord(fragment[i])):
                    break
                i += 1

            if i == iz:
                return False

            if len(fragment) <= i + 8 or fragment[i:i + 8] != 'function':
                return False

            code = ord(fragment[i + 8])
            return (code == 0x28 or # '('
                    _whiteSpace(code) or
                    code == 0x2A or # '*'
                    _lineTerminator(code))
                    
        if (stmt.expression.type == Syntax.Literal and
                stmt.expression.value == 'use strict' and stmt.directive != 'use strict'):
            # An escaped directive is a string in the prologue, but is not a
            # strict-mode directive. Retain that distinction even without raw.
            quote = '"' if _context().quotes == 'double' else "'"
            escaped_space = '\\u0020' if _context().json else '\\x20'
            result = [quote + 'use' + escaped_space + 'strict' + quote]
        else:
            result = [self.generateExpression(stmt.expression, Precedence.Sequence, E_TTT)]
        # 12.4 '{', 'function', 'class' is not allowed in this position.
        # wrap expression with parentheses
        fragment = toSourceNodeWhenNeeded(result, toString=True)
        first = self.firstExpression(stmt.expression)
        if (fragment.startswith('{') or
                first.type in (Syntax.ObjectExpression, Syntax.ObjectPattern, Syntax.FunctionExpression, Syntax.ClassExpression) or
                # ObjectExpression
                isClassPrefixed(fragment) or
                isFunctionPrefixed(fragment) or
                isAsyncPrefixed(fragment) or
                bool(re.match(r'^let\s*\[', fragment)) or self.startsWithLetBracket(stmt.expression) or
                (_context().directive and (flags & F_DIRECTIVE_CTX) and
                 stmt.directive is None and stmt.expression.type == Syntax.Literal and
                 isinstance(stmt.expression.value, str) and stmt.expression.value != 'use strict')
            ):
            result = ['(', result, ')' + self.semicolon(flags)]
        else:
            result.append(self.semicolon(flags))

        return result

    def ImportDeclaration(self, stmt, flags):
        # ES6: 15.2.1 valid import declarations:
        #     - import ImportClause FromClause 
        #     - import ModuleSpecifier 
        that = self
        phase = self.generateImportPhase(stmt)
        if phase:
            expected = Syntax.ImportNamespaceSpecifier if phase == 'defer' else Syntax.ImportDefaultSpecifier
            if len(stmt.specifiers) != 1 or stmt.specifiers[0].type != expected:
                raise ValueError(f'ImportDeclaration.phase {phase} requires exactly one {expected}')

        # If no ImportClause is present,
        # this should be `import ModuleSpecifier` so skip `from`
        # ModuleSpecifier is StringLiteral.
        if len(stmt.specifiers) == 0:
            # import ModuleSpecifier 
            return [
                'import',
                _context().space,
                # ModuleSpecifier
                self.generateExpression(stmt.source, Precedence.Sequence, E_TTT),
                self.generateImportAttributes(stmt),
                self.semicolon(flags)
            ]
            
        # import ImportClause FromClause 
        result = ['import' + (noEmptySpace() + phase if phase else '')]
        cursor = 0
        
        # ImportedBinding
        if stmt.specifiers[cursor].type == Syntax.ImportDefaultSpecifier:
            result = join(result, [
                self.generateExpression(stmt.specifiers[cursor], Precedence.Sequence, E_TTT)
            ])
            cursor += 1
            
        if cursor < len(stmt.specifiers):
            if cursor != 0:
                result.append(',')

            if stmt.specifiers[cursor].type == Syntax.ImportNamespaceSpecifier:
                # NameSpaceImport
                result = join(result, [
                    _context().space,
                    self.generateExpression(stmt.specifiers[cursor], Precedence.Sequence, E_TTT)
                ])
            else:
                # NamedImports
                result.append(_context().space + '{')

                if len(stmt.specifiers) - cursor == 1:
                    # import { ... } from "..."
                    result.append(_context().space)
                    result.append(self.generateExpression(stmt.specifiers[cursor], Precedence.Sequence, E_TTT))
                    result.append(_context().space + '}' + _context().space)
                else:
                    # import {
                    #    ...,
                    #    ...,
                    # } from "..."
                    def fn(indent, *args, **kwargs):
                        nonlocal result
                        result.append(_context().newline)
                        i = cursor
                        iz = len(stmt.specifiers)
                        while i < iz:
                            result.append(indent)
                            result.append(that.generateExpression(stmt.specifiers[i], Precedence.Sequence, E_TTT))
                            if i + 1 < iz:
                                result.append(',' + _context().newline)
                            i += 1
                                
                    withIndent(fn)
                    if not endsWithLineTerminator(toSourceNodeWhenNeeded(result, toString=True)):
                        result.append(_context().newline)
                    result.append(_context().base + '}' + _context().space)

        result = join(result, [
            'from' + _context().space,
            # ModuleSpecifier
            self.generateExpression(stmt.source, Precedence.Sequence, E_TTT),
            self.generateImportAttributes(stmt),
            self.semicolon(flags)
        ])
        return result
        
    def VariableDeclarator(self, stmt, flags):
        itemFlags = E_TTT if (flags & F_ALLOW_IN) else E_FTT
        if flags & F_USING_FOR_OF and stmt.id.type == Syntax.Identifier and stmt.id.name == 'of':
            # `for (using of of xs)` is ambiguous. Escaping the binding's
            # first character retains its name and the valid declaration.
            return toSourceNodeWhenNeeded('\\u006ff', stmt.id)
        if stmt.init:
            return [
                self.generateExpression(stmt.id, Precedence.Assignment, itemFlags),
                _context().space,
                '=',
                _context().space,
                self.generateExpression(stmt.init, Precedence.Assignment, itemFlags)
            ]

        return self.generatePattern(stmt.id, Precedence.Assignment, itemFlags)
        
    def VariableDeclaration(self, stmt, flags):
        self.validateVariableDeclaration(stmt)
        # VariableDeclarator is typed as Statement,
        # but joined with comma (not LineTerminator).
        # So if comment is attached to target node, we should specialize.
        result = [stmt.kind]
        that = self
        bodyFlags = S_TFFF if (flags & F_ALLOW_IN) else S_FFFF

        def fnBlock(*args, **kwargs):
            nonlocal result
            node = stmt.declarations[0]
            if _context().extra.comment and node.leadingComments:
                result.append('\n')
                result.append(addIndent(that.generateStatement(node, bodyFlags)))
            else:
                result.append(noEmptySpace())
                result.append(that.generateStatement(node, bodyFlags))

            for i in range(1, len(stmt.declarations)):
                node = stmt.declarations[i]
                if _context().extra.comment and node.leadingComments:
                    result.append(',' + _context().newline)
                    result.append(addIndent(that.generateStatement(node, bodyFlags)))
                else:
                    result.append(',' + _context().space)
                    result.append(that.generateStatement(node, bodyFlags))

        if len(stmt.declarations) > 1:
            withIndent(fnBlock)
        else:
            fnBlock()

        result.append(self.semicolon(flags))

        return result
        
    def ThrowStatement(self, stmt, flags):
        return [join(
            'throw',
            self.restrictedArgument(stmt.argument, Precedence.Sequence, E_TTT)
        ), self.semicolon(flags)]
        
    def TryStatement(self, stmt, flags):

        result = ['try', self.maybeBlock(stmt.block, S_TFFF)]
        result = self.maybeBlockSuffix(stmt.block, result)

        if stmt.handlers:
            # old interface
            iz = len(stmt.handlers)
            for i in range(iz):
                result = join(result, self.generateStatement(stmt.handlers[i], S_TFFF))
                if stmt.finalizer or (i + 1 != iz):
                    result = self.maybeBlockSuffix(stmt.handlers[i].body, result)
        else:
            guardedHandlers = stmt.guardedHandlers or []
            
            iz = len(guardedHandlers)
            for i in range(iz):
                result = join(result, self.generateStatement(guardedHandlers[i], S_TFFF))
                if stmt.finalizer or (i + 1 != iz):
                    result = self.maybeBlockSuffix(guardedHandlers[i].body, result)

            # new interface
            if stmt.handler:
                if isinstance(stmt.handler, list):
                    iz = len(stmt.handler)
                    for i in range(iz):
                        result = join(result, self.generateStatement(stmt.handler[i], S_TFFF))
                        if stmt.finalizer or (i + 1 != iz):
                            result = self.maybeBlockSuffix(stmt.handler[i].body, result)
                else:
                    result = join(result, self.generateStatement(stmt.handler, S_TFFF))
                    if stmt.finalizer:
                        result = self.maybeBlockSuffix(stmt.handler.body, result)

        if stmt.finalizer:
            result = join(result, ['finally', self.maybeBlock(stmt.finalizer, S_TFFF)])

        return result
        
    def SwitchStatement(self, stmt, flags):
        result = []
        that = self
        def fn(*args, **kwargs):
            nonlocal result
            result.extend([
                'switch' + _context().space + '(',
                that.generateExpression(stmt.discriminant, Precedence.Sequence, E_TTT),
                ')' + _context().space + '{' + _context().newline
            ])
        withIndent(fn)
        if stmt.cases:
            bodyFlags = S_TFFF
            iz = len(stmt.cases)
            for i in range(iz):
                if i == (iz - 1):
                    bodyFlags |= F_SEMICOLON_OPT
                fragment = addIndent(self.generateStatement(stmt.cases[i], bodyFlags))
                result.append(fragment)
                if not endsWithLineTerminator(toSourceNodeWhenNeeded(fragment, toString=True)):
                    result.append(_context().newline)

        result.append(addIndent('}'))
        return result
        
    def SwitchCase(self, stmt, flags):
        result = []
        that = self
        def fn(*args, **kwargs):
            nonlocal result
            
            if stmt.test:
                result.extend([
                    join('case', that.generateExpression(stmt.test, Precedence.Sequence, E_TTT)),
                    ':'
                ])
            else:
                result.extend(['default:'])

            i = 0
            iz = len(stmt.consequent)
            if iz and stmt.consequent[0].type == Syntax.BlockStatement:
                fragment = that.maybeBlock(stmt.consequent[0], S_TFFF)
                result.append(fragment)
                i = 1

            if i != iz and not endsWithLineTerminator(toSourceNodeWhenNeeded(result, toString=True)):
                result.append(_context().newline)

            bodyFlags = S_TFFF
            while i < iz:
                if i == iz - 1 and (flags & F_SEMICOLON_OPT):
                    bodyFlags |= F_SEMICOLON_OPT

                fragment = addIndent(that.generateStatement(stmt.consequent[i], bodyFlags))
                result.append(fragment)
                if i + 1 != iz and not endsWithLineTerminator(toSourceNodeWhenNeeded(fragment, toString=True)):
                    result.append(_context().newline)
                i += 1

        withIndent(fn)
        return result

    def IfStatement(self, stmt, flags):
        result = []
        that = self
        def fn(*args, **kwargs):
            nonlocal result
            
            result.extend([
                'if' + _context().space + '(',
                that.generateExpression(stmt.test, Precedence.Sequence, E_TTT),
                ')'
            ])
        withIndent(fn)
        semicolonOptional = flags & F_SEMICOLON_OPT
        bodyFlags = S_TFFF
        if semicolonOptional:
            bodyFlags |= F_SEMICOLON_OPT

        if stmt.alternate:
            consequent = stmt.consequent
            if self.endsWithUnmatchedIf(consequent):
                consequent = SimpleObj({'type': Syntax.BlockStatement, 'body': [consequent]})
            result.append(self.maybeBlock(consequent, S_TFFF))
            result = self.maybeBlockSuffix(consequent, result)
            if (stmt.alternate.type == Syntax.IfStatement):
                result = join(result, ['else ', self.generateStatement(stmt.alternate, bodyFlags)])
            else:
                result = join(result, join('else', self.maybeBlock(stmt.alternate, bodyFlags)))

        else:
            result.append(self.maybeBlock(stmt.consequent, bodyFlags))

        return result

    def ForStatement(self, stmt, flags):
        that = self
        result = []
        def fn(*args, **kwargs):
            nonlocal result
            result.extend(['for' + _context().space + '('])
            if stmt.init:
                if stmt.init.type == Syntax.VariableDeclaration:
                    result.append(that.generateStatement(stmt.init, S_FFFF))
                else:
                    # F_ALLOW_IN becomes false.
                    fragment = that.generateExpression(stmt.init, Precedence.Sequence, E_FTT)
                    if that.startsWithLetBracket(stmt.init):
                        fragment = ['(', fragment, ')']
                    result.append(fragment)
                    result.append(';')
            else:
                result.append(';')

            if stmt.test:
                result.append(_context().space)
                result.append(that.generateExpression(stmt.test, Precedence.Sequence, E_TTT))
                result.append(';')
            else:
                result.append(';')

            if stmt.update:
                result.append(_context().space)
                result.append(that.generateExpression(stmt.update, Precedence.Sequence, E_TTT))
                result.append(')')
            else:
                result.append(')')

        withIndent(fn)

        result.append(self.maybeBlock(stmt.body, S_TFFT if (flags & F_SEMICOLON_OPT) else S_TFFF))
        return result

    def ForInStatement(self, stmt, flags):
        return self.generateIterationForStatement('in', stmt, S_TFFT if (flags & F_SEMICOLON_OPT) else S_TFFF)

    def ForOfStatement(self, stmt, flags):
        return self.generateIterationForStatement('of', stmt, S_TFFT if (flags & F_SEMICOLON_OPT) else S_TFFF)

    def LabeledStatement(self, stmt, flags):
        return [stmt.label.name + ':', self.maybeBlock(stmt.body, S_TFFT if (flags & F_SEMICOLON_OPT) else S_TFFF)]

    def Program(self, stmt, flags):
        iz = len(stmt.body)
        result = ['\n' if (_context().safeConcatenation and iz > 0) else '']
        bodyFlags = S_TFTF
        for i in range(iz):
            if not _context().safeConcatenation and i == iz - 1:
                bodyFlags |= F_SEMICOLON_OPT

            if _context().preserveBlankLines:
                # handle spaces before the first line
                if i == 0:
                    if not stmt.body[0].leadingComments:
                        generateBlankLines(stmt.range[0], stmt.body[i].range[0], result)

                # handle spaces between lines
                if i > 0:
                    if not stmt.body[i - 1].trailingComments and not stmt.body[i].leadingComments:
                        generateBlankLines(stmt.body[i - 1].range[1], stmt.body[i].range[0], result)

            fragment = addIndent(self.generateStatement(stmt.body[i], bodyFlags))
            result.append(fragment)
            if i + 1 < iz and not endsWithLineTerminator(toSourceNodeWhenNeeded(fragment, toString=True)):
                if _context().preserveBlankLines:
                    if not stmt.body[i + 1].leadingComments:
                        result.append(_context().newline)
                else:
                    result.append(_context().newline)

            if _context().preserveBlankLines:
                # handle spaces after the last line
                if (i == iz - 1):
                    if not stmt.body[i].trailingComments:
                        generateBlankLines(stmt.body[i].range[1], stmt.range[1], result)
        
        return result

    def FunctionDeclaration(self, stmt, flags):
        return [
            generateAsyncPrefix(stmt, True),
            'function',
            generateStarSuffix(stmt) or noEmptySpace(),
            generateIdentifier(stmt.id) if stmt.id else '',
            self.generateFunctionBody(stmt)
        ]

    def ReturnStatement(self, stmt, flags):
        if stmt.argument:
            return [join(
                'return',
                self.restrictedArgument(stmt.argument, Precedence.Sequence, E_TTT)
            ), self.semicolon(flags)]

        return ['return' + self.semicolon(flags)]

    def WhileStatement(self, stmt, flags):
        result = []
        that = self
        def fn(*args, **kwargs):
            nonlocal result
            result.extend([
                'while' + _context().space + '(',
                that.generateExpression(stmt.test, Precedence.Sequence, E_TTT),
                ')'
            ])

        withIndent(fn)
        result.append(self.maybeBlock(stmt.body, S_TFFT if (flags & F_SEMICOLON_OPT) else S_TFFF))
        return result

    def WithStatement(self, stmt, flags):
        result = []
        that = self
        def fn(*args, **kwargs):
            nonlocal result
            result.extend([
                'with' + _context().space + '(',
                that.generateExpression(stmt.object, Precedence.Sequence, E_TTT),
                ')'
            ])
        withIndent(fn)
        result.append(self.maybeBlock(stmt.body, S_TFFT if (flags & F_SEMICOLON_OPT) else S_TFFF))
        return result

# Expressions.

class CodeGeneratorExpression:
    def ExportDefaultSpecifier(self, expr, precedence, flags):
        if not _context().extra.extensions.exportDefaultFrom:
            raise ValueError('Default re-export specifiers require extensions.exportDefaultFrom')
        exported = expr.exported if expr.exported is not None else expr.local
        if exported is None or exported.type != Syntax.Identifier:
            raise ValueError('ExportDefaultSpecifier.exported must contain an Identifier')
        if expr.exported is not None and expr.local is not None and expr.exported.name != expr.local.name:
            raise ValueError('Conflicting ExportDefaultSpecifier.exported/local fields')
        return self.generateExpression(exported, Precedence.Primary, E_TTT)

    def ExportNamespaceSpecifier(self, expr, precedence, flags):
        if expr.exported is None or expr.exported.type not in (Syntax.Identifier, Syntax.Literal):
            raise ValueError('ExportNamespaceSpecifier.exported must contain an exported name')
        return ['*', noEmptySpace(), 'as', noEmptySpace(),
                self.generateExpression(expr.exported, Precedence.Primary, E_TTT)]


    def SequenceExpression(self, expr, precedence, flags):
        if Precedence.Sequence < precedence:
            flags |= F_ALLOW_IN

        result = []
        iz = len(expr.expressions)
        for i in range(iz):
            result.append(self.generateExpression(expr.expressions[i], Precedence.Assignment, flags))
            if i + 1 < iz:
                result.append(',' + _context().space)

        return parenthesize(result, Precedence.Sequence, precedence)
    
    def AssignmentExpression(self, expr, precedence, flags):
        return self.generateAssignment(expr.left, expr.right, expr.operator, precedence, flags)
    
    def ArrowFunctionExpression(self, expr, precedence, flags):
        return parenthesize(self.generateFunctionBody(expr), Precedence.ArrowFunction, precedence)
    
    def ConditionalExpression(self, expr, precedence, flags):
        if Precedence.Conditional < precedence:
            flags |= F_ALLOW_IN
        return parenthesize(
            [
                self.generateExpression(expr.test, Precedence.Coalesce, flags),
                _context().space + '?' + _context().space,
                self.generateExpression(expr.consequent, Precedence.Assignment, flags),
                _context().space + ':' + _context().space,
                self.generateExpression(expr.alternate, Precedence.Assignment, flags)
            ],
            Precedence.Conditional,
            precedence
        )
    
    def LogicalExpression(self, expr, precedence, flags):
        if expr.operator == '??':
            flags |= F_FOUND_COALESCE

        return self.BinaryExpression(expr, precedence, flags)
    
    def BinaryExpression(self, expr, precedence, flags):
        
        result = []
        
        if expr.operator not in BinaryPrecedence:
            raise ValueError('Unsupported binary operator: ' + str(expr.operator))
        currentPrecedence = BinaryPrecedence[expr.operator]
        leftPrecedence = Precedence.Postfix if expr.operator == '**' else currentPrecedence
        rightPrecedence = currentPrecedence if expr.operator == '**' else currentPrecedence + 1

        if currentPrecedence < precedence:
            flags |= F_ALLOW_IN

        fragment = self.generateExpression(expr.left, leftPrecedence, flags)

        leftSource = fragment # TODO fragment.toString()

        if (ord(leftSource[len(leftSource) - 1]) == 0x2f and # '/'
                _identifierPart(ord(expr.operator[0]))):
            result = [fragment, noEmptySpace(), expr.operator]
        else:
            result = join(fragment, expr.operator)

        fragment = self.generateExpression(expr.right, rightPrecedence, flags)

        if (expr.operator == '/' and fragment[0] == '/' or # TODO fragment.toString()
                expr.operator[-1] == '<' and fragment[0:3] == '!--'): # TODO fragment.toString()
            # If '/' concats with '/' or `<` concats with `!--`, it is interpreted as comment start
            result.append(noEmptySpace())
            result.append(fragment)
        else:
            result = join(result, fragment)

        if expr.operator == 'in' and not (flags & F_ALLOW_IN):
            return ['(', result, ')']

        if (expr.operator == '||' or expr.operator == '&&') and (flags & F_FOUND_COALESCE):
            return ['(', result, ')']

        return parenthesize(result, currentPrecedence, precedence)
    
    def CallExpression(self, expr, precedence, flags):
        
        # F_ALLOW_UNPARATH_NEW becomes false.
        result = [self.generateExpression(expr.callee, Precedence.Call, E_TTF)]

        if expr.optional:
            result.append('?.')

        result.append('(')

        iz = len(expr.arguments)
        for i in range(iz):
            result.append(self.generateExpression(expr.arguments[i], Precedence.Assignment, E_TTT))
            if i + 1 < iz:
                result.append(',' + _context().space)
        result.append(')')

        if not (flags & F_ALLOW_CALL):
            return ['(', result, ')']

        return parenthesize(result, Precedence.Call, precedence)
    
    def ChainExpression(self, expr, precedence, flags):
        if Precedence.OptionalChaining < precedence:
            flags |= F_ALLOW_CALL
        
        result = self.generateExpression(expr.expression, Precedence.OptionalChaining, flags)

        return parenthesize(result, Precedence.OptionalChaining, precedence)
    
    def NewExpression(self, expr, precedence, flags):

        length = len(expr.arguments)
        
        # F_ALLOW_CALL becomes false.
        # F_ALLOW_UNPARATH_NEW may become false.
        itemFlags = E_TFT if (flags & F_ALLOW_UNPARATH_NEW and not _context().parentheses and length == 0) else E_TFF

        result = join(
            'new',
            self.generateExpression(expr.callee, Precedence.New, itemFlags)
        )

        if not (flags & F_ALLOW_UNPARATH_NEW) or _context().parentheses or length > 0:
            result.append('(')
            iz = length
            for i in range(iz):
                result.append(self.generateExpression(expr.arguments[i], Precedence.Assignment, E_TTT))
                if i + 1 < iz:
                    result.append(',' + _context().space)
            result.append(')')

        return parenthesize(result, Precedence.New, precedence)
    
    def MemberExpression(self, expr, precedence, flags):
        # F_ALLOW_UNPARATH_NEW becomes false.
        result = [self.generateExpression(expr.object, Precedence.Call, E_TTF if (flags & F_ALLOW_CALL) else E_TFF)]

        if expr.computed:
            if expr.optional:
                result.append('?.')
            result.append('[')
            result.append(self.generateExpression(expr.property, Precedence.Sequence, E_TTT if (flags & F_ALLOW_CALL) else E_TFT))
            result.append(']')
        else:
            if not expr.optional and (expr.object.type == Syntax.Literal) and isinstance(expr.object.value, (int, float)):
                fragment = toSourceNodeWhenNeeded(result, toString=True)
                # When the following conditions are all true,
                #   1. No floating point
                #   2. Don't have exponents
                #   3. The last character is a decimal digit
                #   4. Not hexadecimal OR octal number literal
                # we should add a floating point.
                if (not '.' in fragment and
                        not bool(re.compile("[eExX]").search(fragment)) and
                        _decimalDigit(ord(fragment[len(fragment) - 1])) and
                        not (len(fragment) >= 2 and ord(fragment[0]) == 48)  # '0'
                    ):
                    result.append(' ')

            result.append('?.' if expr.optional else '.')
            result.append(generateIdentifier(expr.property))

        return parenthesize(result, Precedence.Member, precedence)
    
    def MetaProperty(self, expr, precedence, flags):
        result = []
        result.append(expr.meta if isinstance(expr.meta, str) else generateIdentifier(expr.meta))
        result.append('.')
        result.append(expr.property if isinstance(expr.property, str) else generateIdentifier(expr.property))
        return parenthesize(result, Precedence.Member, precedence)
    
    def UnaryExpression(self, expr, precedence, flags):
        fragment = self.generateExpression(expr.argument, Precedence.Unary, E_TTT)

        if _context().space == '':
            result = join(expr.operator, fragment)
        else:
            result = [expr.operator]
            if len(expr.operator) > 2:
                # delete, void, typeof
                # get `typeof []`, not `typeof[]`
                result = join(result, fragment)
            else:
                # Prevent inserting spaces between operator and argument if it is unnecessary
                # like, `!cond`
                leftSource = toSourceNodeWhenNeeded(result, toString=True)
                leftCharCode = ord(leftSource[len(leftSource) - 1])
                rightCharCode = ord(fragment[0]) # TODO: fragment.toString()

                if (((  leftCharCode == 0x2B or # '+' 
                        leftCharCode == 0x2D # '-'
                        ) and leftCharCode == rightCharCode) or
                        (_identifierPart(leftCharCode) and _identifierPart(rightCharCode))
                    ):
                    result.append(noEmptySpace())
                    result.append(fragment)
                else:
                    result.append(fragment)

        return parenthesize(result, Precedence.Unary, precedence)
    
    def YieldExpression(self, expr, precedence, flags):
        if expr.delegate:
            result = 'yield*'
        else:
            result = 'yield'

        if expr.argument:
            result = join(
                result,
                self.restrictedArgument(expr.argument, Precedence.Yield, E_TTT)
            )

        return parenthesize(result, Precedence.Yield, precedence)
    
    def AwaitExpression(self, expr, precedence, flags):
        result = join(
            'await*' if expr.all else 'await',
            self.generateExpression(expr.argument, Precedence.Await, E_TTT)
        )
        return parenthesize(result, Precedence.Await, precedence)
    
    def UpdateExpression(self, expr, precedence, flags):
        if expr.prefix:
            return parenthesize(
                [
                    expr.operator,
                    self.generateExpression(expr.argument, Precedence.Unary, E_TTT)
                ],
                Precedence.Unary,
                precedence
            )

        return parenthesize(
            [
                self.restrictedArgument(expr.argument, Precedence.Postfix, E_TTT),
                expr.operator
            ],
            Precedence.Postfix,
            precedence
        )
    
    def FunctionExpression(self, expr, precedence, flags):
        result = [
            generateAsyncPrefix(expr, True),
            'function'
        ]
        if expr.id:
            result.append(generateStarSuffix(expr) or noEmptySpace())
            result.append(generateIdentifier(expr.id))
        else:
            result.append(generateStarSuffix(expr) or _context().space)

        result.append(self.generateFunctionBody(expr))
        return result
    
    def ArrayPattern(self, expr, precedence, flags):
        return self.ArrayExpression(expr, precedence, flags, True)
    
    def ArrayExpression(self, expr, precedence, flags, isPattern=False):
        that = self
        if not len(expr.elements):
            return self.emptyContainer(expr, '[', ']')

        multiline = False if isPattern else len(expr.elements) > 1
        result = ['[', _context().newline if multiline else '']
        def fn(indent, *args, **kwargs):
            nonlocal result
            iz = len(expr.elements)
            for i in range(iz):
                if not expr.elements[i]:
                    if multiline:
                        result.append(indent)
                    if i + 1 == iz:
                        result.append(',')
                else:
                    result.append(indent if multiline else '')
                    result.append(that.generateExpression(expr.elements[i], Precedence.Assignment, E_TTT))
                if i + 1 < iz:
                    result.append(',' + (_context().newline if multiline else _context().space))

        withIndent(fn)
        
        if multiline and not endsWithLineTerminator(toSourceNodeWhenNeeded(result, toString=True)):
            result.append(_context().newline)

        result.append(_context().base if multiline else '')
        result.append(']')
        return result
    
    def RestElement(self, expr, precedence, flags):
        return '...' + self.generatePattern(expr.argument, precedence, flags)
    
    def ClassExpression(self, expr, precedence, flags):
        result = [self.generateDecorators(expr), 'class']
        if expr.id:
            result = join(result, self.generateExpression(expr.id, Precedence.Sequence, E_TTT))

        if expr.superClass:
            fragment = join('extends', self.generateExpression(expr.superClass, Precedence.Unary, E_TTT))
            result = join(result, fragment)

        result.append(_context().space)
        result.append(self.generateStatement(expr.body, S_TFFT))
        # A decorated class still has the precedence of a class expression.
        return parenthesize(result, Precedence.Primary, precedence)
    
    def MethodDefinition(self, expr, precedence, flags):

        if expr.static:
            result = ['static' + _context().space]
        else:
            result = []

        if expr.kind == 'get' or expr.kind == 'set':
            fragment = [
                join(expr.kind, self.generatePropertyKey(expr.key, expr.computed)),
                self.generateFunctionBody(expr.value)
            ]
        else:
            fragment = [
                generateMethodPrefix(expr),
                self.generatePropertyKey(expr.key, expr.computed),
                self.generateFunctionBody(expr.value)
            ]

        return [self.generateDecorators(expr), join(result, fragment)]

    def PrivateIdentifier(self, expr, precedence, flags):
        return generateIdentifier(expr)

    def PropertyDefinition(self, expr, precedence, flags):
        result = [self.generateDecorators(expr)]
        if expr.static:
            result.extend(['static', noEmptySpace()])
        if expr.type == Syntax.AccessorProperty:
            if not _context().extra.extensions.decorators:
                raise ValueError('Auto-accessors require extensions.decorators')
            result.extend(['accessor', noEmptySpace()])
        result.append(self.generatePropertyKey(expr.key, expr.computed))
        if expr.value is not None:
            result.extend([_context().space, '=', _context().space,
                           self.generateExpression(expr.value, Precedence.Assignment, E_TTT)])
        # Always terminate fields: newlines can disappear in compact output.
        result.append(';')
        return result

    AccessorProperty = PropertyDefinition

    def Decorator(self, expr, precedence, flags):
        if not _context().extra.extensions.decorators:
            raise ValueError('Decorators require extensions.decorators')
        # Parenthesized decorators accept every expression and prevent a
        # following decorator/member from extending a call or property access.
        return ['@(', self.generateExpression(expr.expression, Precedence.Sequence, E_TTT), ')']

    def StaticBlock(self, expr, precedence, flags):
        block = SimpleObj({'type': Syntax.BlockStatement, 'body': expr.body,
                           'innerComments': expr.innerComments})
        if _context().preserveBlankLines:
            if expr.range is None:
                raise ValueError('StaticBlock.range is required to preserve blank lines')
            source = _context().sourceCode[expr.range[0]:expr.range[1]]
            prefix = re.match(r'static(?:\s|/\*.*?\*/|//[^\r\n\u2028\u2029]*(?:\r\n|[\r\n\u2028\u2029]))*\{', source, re.S)
            if prefix is None:
                raise ValueError('StaticBlock.range must cover the static keyword and block braces')
            opening = len(source[:prefix.end() - 1].encode('utf-16-le', 'surrogatepass')) // 2
            block.range = [expr.range[0] + opening, expr.range[1]]
            preceding = [comment for comment in expr.innerComments or [] if comment.range and comment.range[0] < block.range[0]]
            block.innerComments = [comment for comment in expr.innerComments or [] if comment not in preceding]
            trivia = self.preservedTrivia(expr.range[0] + 6, block.range[0], preceding)
            return ['static', trivia, self.generateStatement(block, S_TFFF)]
        return ['static', _context().space, self.generateStatement(block, S_TFFF)]
    
    def Property(self, expr, precedence, flags):
        if expr.kind == 'get' or expr.kind == 'set':
            return [
                expr.kind, noEmptySpace(),
                self.generatePropertyKey(expr.key, expr.computed),
                self.generateFunctionBody(expr.value)
            ]

        if expr.shorthand:
            if expr.value.type == "AssignmentPattern":
                return self.AssignmentPattern(expr.value, Precedence.Sequence, E_TTT)
            return self.generatePropertyKey(expr.key, expr.computed)

        if expr.method:
            return [
                generateMethodPrefix(expr),
                self.generatePropertyKey(expr.key, expr.computed),
                self.generateFunctionBody(expr.value)
            ]

        return [
            self.generatePropertyKey(expr.key, expr.computed),
            ':' + _context().space,
            self.generateExpression(expr.value, Precedence.Assignment, E_TTT)
        ]
    
    def ObjectExpression(self, expr, precedence, flags):
        that = self
        fragment = ''
        result = []
        if not len(expr.properties):
            return self.emptyContainer(expr, '{', '}')

        multiline = len(expr.properties) > 1

        def fn(*args, **kwargs):
            nonlocal fragment
            fragment = that.generateExpression(expr.properties[0], Precedence.Sequence, E_TTT)
        
        withIndent(fn)

        if not multiline:
            # issues 4
            # Do not transform from
            #   dejavu.Class.declare({
            #       method2: function () {}
            #   })
            # to
            #   dejavu.Class.declare({method2: function ():
            #       }})
            if not hasLineTerminator(toSourceNodeWhenNeeded(fragment, toString=True)):
                return [ '{', _context().space, fragment, _context().space, '}' ]

        def fn2(indent, *args, **kwargs):
            nonlocal result
            
            result.extend([ '{', _context().newline, indent, fragment ])

            if multiline:
                result.append(',' + _context().newline)
                iz = len(expr.properties)
                for i in range(1, iz):
                    result.append(indent)
                    result.append(that.generateExpression(expr.properties[i], Precedence.Sequence, E_TTT))
                    if i + 1 < iz:
                        result.append(',' + _context().newline)

        withIndent(fn2)

        if not endsWithLineTerminator(toSourceNodeWhenNeeded(result, toString=True)):
            result.append(_context().newline)

        result.append(_context().base)
        result.append('}')
        return result
    
    def AssignmentPattern(self, expr, precedence, flags):
        return self.generateAssignment(expr.left, expr.right, '=', precedence, flags)
    
    def ObjectPattern(self, expr, precedence, flags):
        that = self
        
        if not len(expr.properties):
            return self.emptyContainer(expr, '{', '}')

        multiline = False
        if len(expr.properties) == 1:
            property = expr.properties[0]
            if property.type == Syntax.Property and property.value.type != Syntax.Identifier:
                multiline = True
        else:
            iz = len(expr.properties)
            for i in range(iz):
                property = expr.properties[i]
                if (property.type == Syntax.Property and not property.shorthand):
                    multiline = True
                    break

        result = ['{', _context().newline if multiline else '' ]

        def fn(indent, *args, **kwargs):
            nonlocal result
            iz = len(expr.properties)
            for i in range(iz):
                result.append(indent if multiline else '')
                result.append(that.generateExpression(expr.properties[i], Precedence.Sequence, E_TTT))
                if i + 1 < iz:
                    result.append(',' + (_context().newline if multiline else _context().space))

        withIndent(fn)

        if multiline and not endsWithLineTerminator(toSourceNodeWhenNeeded(result, toString=True)):
            result.append(_context().newline)

        result.append(_context().base if multiline else '')
        result.append('}')
        return result
    
    def ThisExpression(self, expr, precedence, flags):
        return 'this'
    
    def Super(self, expr, precedence, flags):
        return 'super'
    
    def Identifier(self, expr, precedence, flags):
        return generateIdentifier(expr)
    
    def ImportDefaultSpecifier(self, expr, precedence, flags):
        return generateIdentifier(expr.id or expr.local)
    
    def ImportNamespaceSpecifier(self, expr, precedence, flags):
        result = ['*']
        _id = expr.id or expr.local
        if _id:
            result.append(_context().space + 'as' + noEmptySpace() + generateIdentifier(_id))

        return result
    
    def ImportSpecifier(self, expr, precedence, flags):
        imported = expr.imported
        result = [self.generateExpression(imported, Precedence.Primary, E_TTT)]
        local = expr.local
        if local and (imported.type != Syntax.Identifier or local.name != imported.name):
            result.append(noEmptySpace() + 'as' + noEmptySpace() + generateIdentifier(local))

        return result
    
    def ExportSpecifier(self, expr, precedence, flags):
        local = expr.local
        result = [self.generateExpression(local, Precedence.Primary, E_TTT)]
        exported = expr.exported
        if exported and (local.type != Syntax.Identifier or exported.type != Syntax.Identifier or exported.name != local.name):
            result.extend([noEmptySpace(), 'as', noEmptySpace(),
                           self.generateExpression(exported, Precedence.Primary, E_TTT)])

        return result
    
    def Literal(self, expr, precedence, flags):

        if expr.number is not None:
            if expr.number not in ('Infinity', '-Infinity', 'NaN'):
                raise ValueError('Literal.number must be Infinity, -Infinity or NaN')
            if expr.value is not None or expr.bigint is not None or expr.regex is not None:
                raise ValueError('Tagged Number requires value=None and no bigint/regex fields')
            value = {'Infinity': math.inf, '-Infinity': -math.inf, 'NaN': math.nan}[expr.number]
            if expr.raw is not None:
                raw_value = decodeRawNumber(expr.raw)
                if raw_value != value:
                    raise ValueError('Literal.number conflicts with raw numeric value')
            result = generateNumber(value)
            return parenthesize(result, Precedence.Unary, precedence) if result.startswith('-') else result

        if expr.bigint is not None:
            if not isinstance(expr.bigint, str) or not re.fullmatch(r'(0|[1-9][0-9]*)', expr.bigint):
                raise ValueError('Literal.bigint must contain canonical nonnegative decimal digits')
            return expr.bigint + 'n'

        if expr.raw is not None and _context().parse and _context().extra.raw:
            try:
                raw = SimpleObj.fromDict(_context().parse(expr.raw)).body[0].expression
                if raw.type == Syntax.Literal and self.literalValuesEqual(raw, expr):
                    return expr.raw
            except Exception:
                # not use raw property
                pass


        if expr.regex:
            validateRegExpFlags(expr.regex.flags)
            if not isinstance(expr.regex.pattern, str):
                raise ValueError('Regular-expression pattern must be JavaScript source text')
            return generateRegExp('/' + (expr.regex.pattern or '(?:)') + '/' + expr.regex.flags)

        if expr.value is None:
            return 'null'

        if type(expr.value) == str:
            return escapeString(expr.value)

        if type(expr.value) in (int, float):
            result = generateNumber(expr.value)
            return parenthesize(result, Precedence.Unary, precedence) if result.startswith('-') else result

        if type(expr.value) == bool:
            return 'true' if expr.value else 'false'

        return generateRegExp(expr.value)
    
    def GeneratorExpression(self, expr, precedence, flags):
        return self.ComprehensionExpression(expr, precedence, flags)
    
    def ComprehensionExpression(self, expr, precedence, flags):
        # GeneratorExpression should be parenthesized with (...), ComprehensionExpression with [...]
        # Due to https://bugzilla.mozilla.org/show_bug.cgi?id=883468 position of expr.body can differ in Spidermonkey and ES6

        that = self
        result =  ['('] if (expr.type == Syntax.GeneratorExpression) else ['[']
        fragment = None
        
        if _context().extra.moz.comprehensionExpressionStartsWithAssignment:
            fragment = self.generateExpression(expr.body, Precedence.Assignment, E_TTT)
            result.append(fragment)

        if expr.blocks:
            def fn(*args, **kwargs):
                nonlocal result, fragment
                for i in range(len(expr.blocks)):
                    fragment = that.generateExpression(expr.blocks[i], Precedence.Sequence, E_TTT)
                    if i > 0 or _context().extra.moz.comprehensionExpressionStartsWithAssignment:
                        result = join(result, fragment)
                    else:
                        result.append(fragment)

            withIndent(fn)

        if expr.filter:
            result = join(result, 'if' + _context().space)
            fragment = self.generateExpression(expr.filter, Precedence.Sequence, E_TTT)
            result = join(result, [ '(', fragment, ')' ])

        if not _context().extra.moz.comprehensionExpressionStartsWithAssignment:
            fragment = self.generateExpression(expr.body, Precedence.Assignment, E_TTT)
            result = join(result, fragment)

        result.append(')' if (expr.type == Syntax.GeneratorExpression) else ']')
        return result
    
    def ComprehensionBlock(self, expr, precedence, flags):
        if expr.left.type == Syntax.VariableDeclaration:
            fragment = [
                expr.left.kind, noEmptySpace(),
                self.generateStatement(expr.left.declarations[0], S_FFFF)
            ]
        else:
            fragment = self.generateExpression(expr.left, Precedence.Call, E_TTT)


        fragment = join(fragment, 'of' if expr.of else 'in')
        fragment = join(fragment, self.generateExpression(expr.right, Precedence.Sequence, E_TTT))

        return [ 'for' + _context().space + '(', fragment, ')' ]
    
    def SpreadElement(self, expr, precedence, flags):
        return [
            '...',
            self.generateExpression(expr.argument, Precedence.Assignment, E_TTT)
        ]
    
    def TaggedTemplateExpression(self, expr, precedence, flags):
        itemFlags = E_TTF
        if not (flags & F_ALLOW_CALL):
            itemFlags = E_TFF

        result = [
            self.generateExpression(expr.tag, Precedence.Call, itemFlags),
            self.generateExpression(expr.quasi, Precedence.Primary, E_FFT)
        ]
        return parenthesize(result, Precedence.TaggedTemplate, precedence)
    
    def TemplateElement(self, expr, precedence, flags):
        # Don't use "cooked". Since tagged template can use raw template
        # representation. So if we do so, it breaks the script semantics.
        return expr.value.raw
    
    def TemplateLiteral(self, expr, precedence, flags):
        result = [ '`' ]
        iz = len(expr.quasis)
        for i in range(iz):
            result.append(self.generateExpression(expr.quasis[i], Precedence.Primary, E_TTT))
            if i + 1 < iz:
                result.append('${' + _context().space)
                result.append(self.generateExpression(expr.expressions[i], Precedence.Sequence, E_TTT))
                result.append(_context().space + '}')

        result.append('`')
        return result
    
    def ModuleSpecifier(self, expr, precedence, flags):
        return self.Literal(expr, precedence, flags)
    
    def ImportExpression(self, expr, precedence, flags):
        phase = self.generateImportPhase(expr)
        return parenthesize([
            'import' + ('.' + phase if phase else '') + '(',
            (expr.source and self.generateExpression(expr.source, Precedence.Assignment, E_TTT) or ''),
            [',' + _context().space, self.generateExpression(expr.options, Precedence.Assignment, E_TTT)] if expr.options is not None else '',
            ')'
        ], Precedence.Call, precedence)

    def JSXIdentifier(self, expr, precedence, flags):
        return expr.name

    def JSXNamespacedName(self, expr, precedence, flags):
        return [self.generateExpression(expr.namespace, Precedence.Primary, E_TTT), ':',
                self.generateExpression(expr.name, Precedence.Primary, E_TTT)]

    def JSXMemberExpression(self, expr, precedence, flags):
        return [self.generateExpression(expr.object, Precedence.Primary, E_TTT), '.',
                self.generateExpression(expr.property, Precedence.Primary, E_TTT)]

    def JSXAttribute(self, expr, precedence, flags):
        result = [self.generateExpression(expr.name, Precedence.Primary, E_TTT)]
        if expr.value is not None:
            result.append('=')
            if expr.value.type == Syntax.Literal:
                result.extend(['"', escapeJSXString(expr.value.value, attribute=True), '"'])
            else:
                result.append(self.generateExpression(expr.value, Precedence.Primary, E_TTT))
        return result

    def JSXSpreadAttribute(self, expr, precedence, flags):
        return ['{...', self.generateExpression(expr.argument, Precedence.Assignment, E_TTT), '}']

    def JSXExpressionContainer(self, expr, precedence, flags):
        return ['{', self.generateExpression(expr.expression, Precedence.Sequence, E_TTT), '}']

    def JSXSpreadChild(self, expr, precedence, flags):
        return ['{...', self.generateExpression(expr.expression, Precedence.Assignment, E_TTT), '}']

    def JSXEmptyExpression(self, expr, precedence, flags):
        return ''

    def JSXText(self, expr, precedence, flags):
        if not isinstance(expr.value, str):
            raise ValueError('JSXText.value must be a string')
        if _context().extra.raw and isinstance(expr.raw, str) and not any(0xd800 <= ord(character) <= 0xdfff for character in expr.raw):
            raw_value = jsxTextValue(expr.raw)
            if raw_value.encode('utf-16-le', 'surrogatepass') == expr.value.encode('utf-16-le', 'surrogatepass'):
                return expr.raw
        return escapeJSXString(expr.value)

    def JSXOpeningElement(self, expr, precedence, flags):
        result = ['<', self.generateExpression(expr.name, Precedence.Primary, E_TTT)]
        for attribute in expr.attributes:
            result.extend([' ', self.generateExpression(attribute, Precedence.Primary, E_TTT)])
        result.append(' />' if expr.selfClosing else '>')
        return result

    def JSXClosingElement(self, expr, precedence, flags):
        return ['</', self.generateExpression(expr.name, Precedence.Primary, E_TTT), '>']

    def JSXElement(self, expr, precedence, flags):
        result = [self.generateExpression(expr.openingElement, Precedence.Primary, E_TTT)]
        result.extend(self.generateExpression(child, Precedence.Primary, E_TTT) for child in expr.children)
        if expr.closingElement is not None:
            result.append(self.generateExpression(expr.closingElement, Precedence.Primary, E_TTT))
        return parenthesize(result, Precedence.Primary, precedence)

    def JSXOpeningFragment(self, expr, precedence, flags):
        return '<>'

    def JSXClosingFragment(self, expr, precedence, flags):
        return '</>'

    def JSXFragment(self, expr, precedence, flags):
        return ['<>', [self.generateExpression(child, Precedence.Primary, E_TTT) for child in expr.children], '</>']

class CodeGenerator(CodeGeneratorStatement, CodeGeneratorExpression):

    def __init__(self):
        self.context = _context()

    def preservedTrivia(self, start, end, comments):
        result = []
        cursor = start
        def whitespace(text):
            return ''.join(character for character in text if _whiteSpace(ord(character)) or
                           _lineTerminator(ord(character)))
        for comment in comments if _context().extra.comment else []:
            if comment.range is None or comment.range[0] < cursor or comment.range[1] > end:
                raise ValueError('Inner comment ranges must be ordered within their container')
            result.append(whitespace(_context().sourceCode[cursor:comment.range[0]]))
            result.append(toSourceNodeWhenNeeded(generateComment(comment), comment))
            cursor = comment.range[1]
            if comment.type == 'Line' and not hasLineTerminator(_context().sourceCode[cursor:end]):
                result.append('\n')
        result.append(whitespace(_context().sourceCode[cursor:end]))
        return result

    def preservedEmptyContainer(self, node, opening, closing):
        if node.range is None:
            raise ValueError(f'{node.type}.range is required to preserve blank lines')
        start, end = node.range
        source = _context().sourceCode[start:end]
        if not source.startswith(opening) or not source.endswith(closing):
            raise ValueError(f'{node.type}.range must cover its container delimiters')
        return [opening, self.preservedTrivia(start + 1, end - 1, node.innerComments or []), closing]

    def emptyContainer(self, node, opening, closing):
        if _context().preserveBlankLines and node.range is not None:
            return self.preservedEmptyContainer(node, opening, closing)
        if not _context().extra.comment or not node.innerComments:
            return opening + closing
        result = [opening, _context().newline]
        def emit(*args):
            for comment in node.innerComments:
                fragment = toSourceNodeWhenNeeded(addIndent(generateComment(comment)), comment)
                result.append(fragment)
                if not endsWithLineTerminator(toSourceNodeWhenNeeded(fragment, toString=True)):
                    result.append('\n' if comment.type == 'Line' else _context().newline)
        withIndent(emit)
        result.extend([_context().base, closing])
        return result

    def firstExpression(self, node):
        while True:
            if node.type in (Syntax.AssignmentExpression, Syntax.BinaryExpression, Syntax.LogicalExpression):
                node = node.left
            elif node.type == Syntax.ConditionalExpression:
                node = node.test
            elif node.type == Syntax.SequenceExpression:
                node = node.expressions[0]
            elif node.type == Syntax.MemberExpression:
                node = node.object
            elif node.type == Syntax.CallExpression:
                node = node.callee
            elif node.type == Syntax.ChainExpression:
                node = node.expression
            elif node.type == Syntax.TaggedTemplateExpression:
                node = node.tag
            else:
                return node

    def startsWithLetBracket(self, node):
        if node.type == Syntax.MemberExpression and node.computed and not node.optional:
            return node.object.type == Syntax.Identifier and node.object.name == 'let'
        if node.type in (Syntax.AssignmentExpression, Syntax.BinaryExpression, Syntax.LogicalExpression):
            return self.startsWithLetBracket(node.left)
        if node.type == Syntax.ConditionalExpression:
            return self.startsWithLetBracket(node.test)
        if node.type == Syntax.SequenceExpression:
            return self.startsWithLetBracket(node.expressions[0])
        if node.type == Syntax.CallExpression:
            return self.startsWithLetBracket(node.callee)
        if node.type == Syntax.ChainExpression:
            return self.startsWithLetBracket(node.expression)
        return False

    def literalValuesEqual(self, left, right):
        if left.regex is not None or right.regex is not None:
            return (left.regex is not None and right.regex is not None and
                    left.regex.pattern == right.regex.pattern and left.regex.flags == right.regex.flags)
        if left.value == 0 and right.value == 0 and type(left.value) in (int, float) and type(right.value) in (int, float):
            return math.copysign(1, left.value) == math.copysign(1, right.value)
        if type(left.value) in (int, float) and type(right.value) in (int, float):
            return left.value == right.value
        return type(left.value) is type(right.value) and left.value == right.value

    def generateImportAttributes(self, node):
        attributes = node.attributes if node.attributes is not None else node.assertions
        if not attributes:
            return ''
        result = [noEmptySpace(), 'with', _context().space, '{', _context().space]
        for index, attribute in enumerate(attributes):
            if index:
                result.append(',' + _context().space)
            result.extend([self.generateExpression(attribute.key, Precedence.Primary, E_TTT),
                           ':' + _context().space,
                           self.generateExpression(attribute.value, Precedence.Primary, E_TTT)])
        result.extend([_context().space, '}'])
        return result

    def generateImportPhase(self, node):
        phase = node.phase
        if phase is None:
            return ''
        option = {'defer': 'deferredImportEvaluation', 'source': 'sourcePhaseImports'}.get(phase)
        if option is None:
            raise ValueError(f'Unsupported {node.type}.phase: {phase}')
        if not getattr(_context().extra.extensions, option):
            raise ValueError(f'Import phase {phase} requires extensions.{option}')
        return phase

    def generateDecorators(self, node):
        result = []
        for decorator in node.decorators or []:
            result.extend([self.generateExpression(decorator, Precedence.Sequence, E_TTT),
                           _context().newline or noEmptySpace(), _context().base if _context().newline else ''])
        return result

    def validateVariableDeclaration(self, node, iteration=None):
        validateNodeFields(node)
        resource = node.kind in ('using', 'await using')
        if resource:
            if not _context().extra.extensions.resourceManagement:
                raise ValueError('Resource declarations require extensions.resourceManagement')
            if iteration == 'in':
                raise ValueError('Resource declarations cannot be used in for-in loops')
        elif node.kind not in ('var', 'let', 'const'):
            raise ValueError('Unsupported VariableDeclaration.kind: ' + str(node.kind))
        if iteration is not None and len(node.declarations) != 1:
            raise ValueError('Iteration declarations require exactly one declarator')
        for declaration in node.declarations:
            validateNodeFields(declaration)
            if declaration.type != Syntax.VariableDeclarator:
                raise ValueError('VariableDeclaration.declarations must contain VariableDeclarator nodes')
            if resource and declaration.id.type != Syntax.Identifier:
                raise ValueError('Resource declarations require identifier bindings')
            if iteration == 'of' and declaration.init is not None:
                raise ValueError('For-of declarations cannot have an initializer')
            if resource and iteration is None and declaration.init is None:
                raise ValueError('Resource declarations require an initializer')

    def restrictedArgument(self, node, precedence, flags):
        result = self.generateExpression(node, precedence, flags)
        if hasLineTerminator(toSourceNodeWhenNeeded(result, toString=True)):
            return ['(', result, ')']
        return result

    def endsWithUnmatchedIf(self, node):
        if node.type == Syntax.IfStatement:
            return node.alternate is None or self.endsWithUnmatchedIf(node.alternate)
        if node.type in (Syntax.ForStatement, Syntax.ForInStatement, Syntax.ForOfStatement,
                         Syntax.WhileStatement, Syntax.WithStatement, Syntax.LabeledStatement):
            return self.endsWithUnmatchedIf(node.body)
        return False
    
    def maybeBlock(self, stmt, flags):
        that = self
        result = []
        noLeadingComment = not _context().extra.comment or not stmt.leadingComments

        if stmt.type == Syntax.BlockStatement and noLeadingComment:
            return [_context().space, self.generateStatement(stmt, flags)]

        if stmt.type == Syntax.EmptyStatement and noLeadingComment:
            return ';'

        def fn(*args, **kwargs):
            nonlocal result
            result.extend([
                _context().newline,
                addIndent(that.generateStatement(stmt, flags))
            ])
        withIndent(fn)

        return result
    
    def maybeBlockSuffix(self, stmt, result):

        ends = endsWithLineTerminator(toSourceNodeWhenNeeded(result, toString=True))

        if stmt.type == Syntax.BlockStatement and (not _context().extra.comment or not stmt.leadingComments) and not ends:
            return [result, _context().space]

        if ends:
            return [result, _context().base]

        return [result, _context().newline, _context().base]
    
    def generatePattern(self, node, precedence, flags):
        if node.type == Syntax.Identifier:
            return generateIdentifier(node)

        return self.generateExpression(node, precedence, flags)
    
    def generateFunctionParams(self, node):

        hasDefault = False

        if (node.type == Syntax.ArrowFunctionExpression and
                not node.rest and (not node.defaults or len(node.defaults) == 0) and
                len(node.params) == 1 and node.params[0].type == Syntax.Identifier):
            # arg => { } case
            result = [generateAsyncPrefix(node, True), generateIdentifier(node.params[0])]
        else:
            result = [generateAsyncPrefix(node, False)] if (node.type == Syntax.ArrowFunctionExpression) else []
            result.append('(')
            if node.defaults:
                hasDefault = True
            
            iz = len(node.params)
            for i in range(iz):
                if hasDefault and node.defaults[i]:
                    # Handle default values.
                    result.append(self.generateAssignment(node.params[i], node.defaults[i], '=', Precedence.Assignment, E_TTT))
                else:
                    result.append(self.generatePattern(node.params[i], Precedence.Assignment, E_TTT))
                if i + 1 < iz:
                    result.append(',' + _context().space)
            if node.rest:
                if len(node.params):
                    result.append(',' + _context().space)

                result.append('...')
                result.append(generateIdentifier(node.rest))

            result.append(')')

        return result
    
    def generateFunctionBody(self, node):

        validateNodeFields(node)

        result = self.generateFunctionParams(node)

        if node.type == Syntax.ArrowFunctionExpression:
            result.append(_context().space)
            result.append('=>')

        if node.expression:
            result.append(_context().space)
            expr = self.generateExpression(node.body, Precedence.Assignment, E_TTT)
            if expr[0] == '{': # TODO: expr.toString().charAt(0)
                expr = ['(', expr, ')']
            result.append(expr)
        else:
            result.append(self.maybeBlock(node.body, S_TTFF))

        return result
    
    def generateIterationForStatement(self, operator, stmt, flags):
        that = self
        if stmt.allowAwait and operator != 'of':
            raise ValueError('Only for-of loops can be asynchronous')
        result = ['for' + (noEmptySpace() + 'await' if stmt.allowAwait else '') + _context().space + '('] # TODO: stmt.await => stmt.allowAwait ?
        
        def fn(*args, **kwargs):
            nonlocal result
            if stmt.left.type == Syntax.VariableDeclaration:
                that.validateVariableDeclaration(stmt.left, operator)
                def fn2(*args, **kwargs):
                    nonlocal result
                    result.append(stmt.left.kind + noEmptySpace())
                    bindingFlags = F_USING_FOR_OF if operator == 'of' and stmt.left.kind == 'using' else S_FFFF
                    result.append(that.generateStatement(stmt.left.declarations[0], bindingFlags))
                withIndent(fn2)
            else:
                fragment = that.generateExpression(stmt.left, Precedence.Call, E_TTT)
                if operator == 'of' and (that.startsWithLetBracket(stmt.left) or
                        (stmt.left.type == Syntax.Identifier and stmt.left.name in ('let', 'async'))):
                    fragment = ['(', fragment, ')']
                result.append(fragment)

            result = join(result, operator)
            result = [join(
                result,
                that.generateExpression(stmt.right, Precedence.Assignment, E_TTT)
            ), ')']

        withIndent(fn)
        result.append(self.maybeBlock(stmt.body, flags))
        return result
    
    def generatePropertyKey(self, expr, computed):
        result = []

        if computed:
            result.append('[')

        result.append(self.generateExpression(expr, Precedence.Assignment, E_TTT))

        if computed:
            result.append(']')

        return result
    
    def generateAssignment(self, left, right, operator, precedence, flags):
        if Precedence.Assignment < precedence:
            flags |= F_ALLOW_IN

        return parenthesize(
            [
                self.generateExpression(left, Precedence.Call, flags),
                _context().space + operator + _context().space,
                self.generateExpression(right, Precedence.Assignment, flags)
            ],
            Precedence.Assignment,
            precedence
        )
    
    def semicolon(self, flags):
        if not _context().semicolons and (flags & F_SEMICOLON_OPT):
            return ''

        return ';'
    
    def generateExpression(self, expr, precedence, flags):
        context = self.context
        identity = id(expr)
        validateNodeFields(expr, context)
        active = context.activeNodes
        if identity in active:
            raise ValueError('Cyclic AST child graph detected')
        active.add(identity)
        try:
            if context.extra.verbatim and getattr(expr, context.extra.verbatim) is not None:
                return generateVerbatim(expr, precedence)
            if type(self) is CodeGenerator:
                handler = _EXPRESSION_HANDLERS.get(expr.type)
                if handler is None:
                    raise ValueError('Unsupported ESTree expression type: ' + expr.type)
                result = handler(self, expr, precedence, flags)
            else:
                handler = getattr(self, expr.type, None)
                if handler is None or not hasattr(CodeGeneratorExpression, expr.type):
                    raise ValueError('Unsupported ESTree expression type: ' + expr.type)
                result = handler(expr, precedence, flags)
            if context.extra.comment:
                result = addComments(expr, result)
            return toSourceNodeWhenNeeded(result, expr)
        finally:
            active.remove(identity)
    
    def generateStatement(self, stmt, flags):
        context = self.context
        identity = id(stmt)
        validateNodeFields(stmt, context)
        active = context.activeNodes
        if identity in active:
            raise ValueError('Cyclic AST child graph detected')
        active.add(identity)
        try:
            if type(self) is CodeGenerator:
                handler = _STATEMENT_HANDLERS.get(stmt.type)
                if handler is None:
                    raise ValueError('Unsupported ESTree statement type: ' + stmt.type)
                result = handler(self, stmt, flags)
            else:
                handler = getattr(self, stmt.type, None)
                if handler is None or not hasattr(CodeGeneratorStatement, stmt.type):
                    raise ValueError('Unsupported ESTree statement type: ' + stmt.type)
                result = handler(stmt, flags)
            if context.extra.comment:
                result = addComments(stmt, result)
            if stmt.type == Syntax.Program and (not context.safeConcatenation) and context.newline == '':
                fragment = toSourceNodeWhenNeeded(result, toString=True)
                if fragment.endswith('\n'):
                    result = toSourceNodeWhenNeeded(result).replaceRight(r'\s+$', '') if context.sourceMap else re.compile(r'\s+$').sub('', fragment)
                elif not context.sourceMap:
                    return fragment
            return toSourceNodeWhenNeeded(result, stmt)
        finally:
            active.remove(identity)


_EXPRESSION_HANDLERS = {name: handler for name, handler in vars(CodeGeneratorExpression).items()
                        if not name.startswith('_') and callable(handler)}
_STATEMENT_HANDLERS = {name: handler for name, handler in vars(CodeGeneratorStatement).items()
                       if not name.startswith('_') and callable(handler)}



FORMAT_MINIFY = getDefaultOptions().format
FORMAT_MINIFY.indent.style = ''
FORMAT_MINIFY.indent.base = 0
FORMAT_MINIFY.renumber = True
FORMAT_MINIFY.hexadecimal = True
FORMAT_MINIFY.quotes = 'auto'
FORMAT_MINIFY.escapeless = True
FORMAT_MINIFY.compact = True
FORMAT_MINIFY.parentheses = True
FORMAT_MINIFY.semicolons = True

FORMAT_DEFAULTS = getDefaultOptions().format



