#  AST walker module for Mozilla Parser API compatible trees

#  A simple walk is one where you simply specify callbacks to be
#  called on specific nodes. The last two arguments are optional. A
#  simple use would be
# 
#      walk.simple(myTree, {
#          Expression: function(node) { ... }
#      });
# 
#  to do something with all expressions. All Parser API node types
#  can be used to identify node types, as well as Expression and
#  Statement, which denote categories of nodes.
# 
#  The base argument can be used to pass a custom (recursive)
#  walker, and state can be used to give this walked an initial
#  state.

def simple(node, visitors, baseVisitor=None, state=None, override=None):
    baseVisitor = baseVisitor or Base()
    def c(node, st, override=None):
        _type = override or node.type
        found = visitors.get(_type)
        baseVisitor[_type](node, st, c)
        if found:
            found(node, st)
    c(node, state, override)


#  An ancestor walk keeps an array of ancestor nodes (including the
#  current node) and passes them to the callback as third parameter
#  (and also as state parameter when no other state is present).

def ancestor(node, visitors, baseVisitor=None, state=None, override=None):
    ancestors = []
    if not baseVisitor:
        baseVisitor = Base()
    def c(node, st, override=None):
        _type = override or node.type
        found = visitors.get(_type)
        isNew = node != (None if len(ancestors) - 1 < 0 else ancestors[len(ancestors) - 1])
        if isNew:
            ancestors.append(node)
        baseVisitor[_type](node, st, c)
        if found:
            found(node, st or ancestors, ancestors)
        if isNew:
            ancestors.pop()
    c(node, state, override)


#  A recursive walk is one where your functions override the default
#  walkers. They can modify and replace the state parameter that's
#  threaded through the walk, and can opt how and whether to walk
#  their child nodes (by calling their third argument on these
#  nodes).
def recursive(node, state, funcs, baseVisitor=None, override=None):
    visitor = make(funcs, baseVisitor or None) if funcs else baseVisitor
    def c(node, st, override):
        visitor[override or node.type](node, st, c)
    c(node, state, override)


def makeTest(test):
    if type(test) == str:
        return lambda _type: _type == test
    elif not test:
        return lambda:True
    else:
        return test


class Found:
    def __init__(self, node, state):
        self.node = node
        self.state = state


#  A full walk triggers the callback on each node
def full(node, callback, baseVisitor=None, state=None, override=None):
    baseVisitor = baseVisitor or Base()
    last = None
    def c(node, st, override=None):
        nonlocal last
        _type = override or node.type
        baseVisitor[_type](node, st, c)
        if last != node:
            callback(node, st, _type)
            last = node
    c(node, state, override)


#  An fullAncestor walk is like an ancestor walk, but triggers
#  the callback on each node
def fullAncestor(node, callback, baseVisitor, state=None):
    baseVisitor = baseVisitor or Base()
    ancestors = []
    last = None
    
    def c(node, st, override=None):
        _type = override or node.type
        isNew = node != (None if len(ancestors) - 1 < 0 else ancestors[len(ancestors) - 1])
        if isNew:
            ancestors.append(node)
        baseVisitor[type](node, st, c)
        if last != node:
            callback(node, st or ancestors, ancestors, type)
            last = node
        if isNew:
            ancestors.pop()
    c(node, state)


#  Find a node with a given start, end, and type (all are optional,
#  null can be used as wildcard). Returns a {node, state} object, or
#  undefined when it doesn't find a matching node.
def findNodeAt(node, start, end, test, baseVisitor=None, state=None):
    baseVisitor = baseVisitor or Base()
    test = makeTest(test)
    try:
        def c(node, st, override=None):
            _type = override or node.type
            if (start is None or node.start <= start) and (end is None or node.end >= end):
                baseVisitor[_type](node, st, c)
            if (start is None or node.start == start) and (end is None or node.end == end) and test(_type, node):
                raise Found(node, st)
        c(node, state)
    except Exception as e:
        if isinstance(e, Found):
            return e
        raise e


#  Find the innermost node of a given type that contains the given
#  position. Interface similar to findNodeAt.
def findNodeAround(node, pos, test, baseVisitor=None, state=None):
    test = makeTest(test)
    baseVisitor = baseVisitor or Base()
    try:
        def c(node, st, override=None):
            _type = override or node.type
            if node.start > pos or node.end < pos:
                return
        c(node, state)
    except Exception as e:
        if isinstance(e, Found):
            return e
        raise e


#  Find the outermost matching node after a given position.
def findNodeAfter(node, pos, test, baseVisitor=None, state=None):
    test = makeTest(test)
    baseVisitor = baseVisitor or Base()
    try:
        def c(node, st, override=None):
            if node.end < pos:
                return
            _type = override or node.type
            if node.start >= pos and test(_type, node):
                raise Found(node, st)
            baseVisitor[type](node, st, c)
        c(node, state)
    except Exception as e:
        if isinstance(e, Found):
            return e
        raise e


#  Find the outermost matching node before a given position.
def findNodeBefore(node, pos, test, baseVisitor=None, state=None):
    test = makeTest(test)
    baseVisitor = baseVisitor or Base()
    _max = None
  
    def c(node, st, override=None):
        if node.start > pos:
            return
        _type = override or node.type
        if node.end <= pos and (not _max or _max.node.end < node.end) and test(_type, node):
            _max = Found(node, st)
        baseVisitor[type](node, st, c)
    c(node, state)
    return _max


#  Used to create a custom walker. Will fill in all missing node
#  type properties with the defaults.
def make(funcs, baseVisitor=None):
    visitor = baseVisitor or Base()
    for _type in funcs:
        setattr(visitor, _type, funcs[_type])
    return visitor


def skipThrough(node, st, c):
    c(node, st)

def ignore(_node, _st, _c):
	pass

#  Node walkers.



class Base:

    def __init__(self):
        pass
    
    def __getitem__(self, key):
        return getattr(Base, key)
        
    def Program(node, st, c):
        for stmt in node.body:
            c(stmt, st, "Statement")

    def BlockStatement(node, st, c):
        for stmt in node.body:
            c(stmt, st, "Statement")
    
    def StaticBlock(node, st, c):
        for stmt in node.body:
            c(stmt, st, "Statement")

    def Statement(node, st, c):
        return skipThrough(node, st, c)
        
    def EmptyStatement():
        return ignore(node, st, c)

    def ExpressionStatement(node, st, c):
        return c(node.expression, st, "Expression")
    
    def ParenthesizedExpression(node, st, c):
        return c(node.expression, st, "Expression")
    
    def ChainExpression(node, st, c):
        return c(node.expression, st, "Expression")
        
    def IfStatement(node, st, c):
        c(node.test, st, "Expression")
        c(node.consequent, st, "Statement")
        if node.alternate:
            c(node.alternate, st, "Statement")
    
    def LabeledStatement(node, st, c):
        return c(node.body, st, "Statement")
    
    def BreakStatement(node, st, c):
        return ignore(node, st, c)
    
    def ContinueStatement(node, st, c):
        return ignore(node, st, c)
    
    def WithStatement(node, st, c):
        c(node.object, st, "Expression")
        c(node.body, st, "Statement")

    def SwitchStatement(node, st, c):
        c(node.discriminant, st, "Expression")
        for cs in node.cases:
            if cs.test:
                c(cs.test, st, "Expression")
            for cons in cs.consequent:
                c(cons, st, "Statement")

    def SwitchCase(node, st, c):
        if node.test:
            c(node.test, st, "Expression")
        for cons in node.consequent:
            c(cons, st, "Statement")

    def ReturnStatement(node, st, c):
        if node.argument:
            c(node.argument, st, "Expression")

    def YieldExpression(node, st, c):
        if node.argument:
            c(node.argument, st, "Expression")

    def AwaitExpression(node, st, c):
        if node.argument:
            c(node.argument, st, "Expression")

    def ThrowStatement(node, st, c):
        return c(node.argument, st, "Expression")
    
    def SpreadElement(node, st, c):
        c(node.argument, st, "Expression")
    
    def TryStatement(node, st, c):
        c(node.block, st, "Statement")
        if node.handler:
            c(node.handler, st)
        if node.finalizer:
            c(node.finalizer, st, "Statement")
    
    def CatchClause(node, st, c):
        if node.param:
            c(node.param, st, "Pattern")
        c(node.body, st, "Statement")

    def WhileStatement(node, st, c):
        c(node.test, st, "Expression")
        c(node.body, st, "Statement")
    
    def DoWhileStatement(node, st, c):
        c(node.test, st, "Expression")
        c(node.body, st, "Statement")

    
    def ForStatement(node, st, c):
        if node.init:
            c(node.init, st, "ForInit")
        if node.test:
            c(node.test, st, "Expression")
        if node.update:
            c(node.update, st, "Expression")
        c(node.body, st, "Statement")
    
    def ForInStatement(node, st, c):
        c(node.left, st, "ForInit")
        c(node.right, st, "Expression")
        c(node.body, st, "Statement")
    
    def ForOfStatement(node, st, c):
        c(node.left, st, "ForInit")
        c(node.right, st, "Expression")
        c(node.body, st, "Statement")

    def ForInit(node, st, c):
        if node.type == "VariableDeclaration":
            c(node, st)
        else:
            c(node, st, "Expression")

    def DebuggerStatement(node, st, c):
        return ignore(node, st, c)

    def FunctionDeclaration(node, st, c):
        return c(node, st, "Function")

    def VariableDeclaration(node, st, c):
        for decl in node.declarations:
            c(decl, st)

    def VariableDeclarator(node, st, c):
        c(node.id, st, "Pattern")
        if node.init:
            c(node.init, st, "Expression")

    def Function(node, st, c):
        if node.id:
            c(node.id, st, "Pattern")
        for param in node.params:
            c(param, st, "Pattern")
        c(node.body, st, "Expression" if node.expression else "Statement")

    def Pattern(node, st, c):
        if node.type == "Identifier":
            c(node, st, "VariablePattern")
        elif node.type == "MemberExpression":
            c(node, st, "MemberPattern")
        else:
            c(node, st)

    def VariablePattern(node, st, c):
        return ignore(node, st, c)

    def MemberPattern(node, st, c):
        return skipThrough(node, st, c)

    def RestElement(node, st, c):
        return c(node.argument, st, "Pattern")

    def ArrayPattern(node, st, c):
        for elt in node.elements:
            if elt:
                c(elt, st, "Pattern")

    def ObjectPattern(node, st, c):
        for prop in node.properties:
            if prop.type == 'Property':
                if prop.computed:
                    c(prop.key, st, "Expression")
            elif prop.type == "RestElement":
                c(prop.argument, st, "Pattern")

    def Expression(node, st, c):
        return skipThrough(node, st, c)

    def ThisExpression(node, st, c):
        return ignore(node, st, c)

    def Super(node, st, c):
        return ignore(node, st, c)

    def MetaProperty(node, st, c):
        return ignore(node, st, c)

    def ArrayExpression(node, st, c):
        for elt in node.elements:
            if elt:
                c(elt, st, "Expression")

    def ObjectExpression(node, st, c):
        for prop in node.properties:
            c(prop, st)

    def FunctionExpression(node, st, c):
        return c(node, st, "Function")

    def ArrowFunctionExpression(node, st, c):
        return c(node, st, "Function")

    def SequenceExpression(node, st, c):
        for expr in node.expressions:
            c(expr, st, "Expression")

    def TemplateLiteral(node, st, c):
        for quasi in node.quasis:
            c(quasi, st)
        for expr in node.expressions:
            c(expr, st, "Expression")

    def TemplateElement(node, st, c):
        return ignore(node, st, c)

    def UnaryExpression(node, st, c):
        c(node.argument, st, "Expression")

    def UpdateExpression(node, st, c):
        c(node.argument, st, "Expression")

    def BinaryExpression(node, st, c):
        c(node.left, st, "Expression")
        c(node.right, st, "Expression")

    def LogicalExpression(node, st, c):
        c(node.left, st, "Expression")
        c(node.right, st, "Expression")

    def AssignmentExpression(node, st, c):
        c(node.left, st, "Pattern")
        c(node.right, st, "Expression")

    def AssignmentPattern(node, st, c):
        c(node.left, st, "Pattern")
        c(node.right, st, "Expression")

    def ConditionalExpression(node, st, c):
        c(node.test, st, "Expression")
        c(node.consequent, st, "Expression")
        c(node.alternate, st, "Expression")

    def NewExpression(node, st, c):
        c(node.callee, st, "Expression")
        if node.arguments:
            for arg in node.arguments:
                c(arg, st, "Expression")

    def CallExpression(node, st, c):
        c(node.callee, st, "Expression")
        if node.arguments:
            for arg in node.arguments:
                c(arg, st, "Expression")

    def MemberExpression(node, st, c):
        c(node.object, st, "Expression")
        if node.computed:
            c(node.property, st, "Expression")

    def ExportNamedDeclaration(node, st, c):
        if node.declaration:
            c(node.declaration, st, "Statement" if (node.type == "ExportNamedDeclaration" or node.declaration.id) else "Expression")
        if node.source:
            c(node.source, st, "Expression")

    def ExportDefaultDeclaration(node, st, c):
        if node.declaration:
            c(node.declaration, st, "Statement" if (node.type == "ExportNamedDeclaration" or node.declaration.id) else "Expression")
        if node.source:
            c(node.source, st, "Expression")

    def ExportAllDeclaration(node, st, c):
        if node.exported:
            c(node.exported, st)
        c(node.source, st, "Expression")

    def ImportDeclaration(node, st, c):
        for spec in node.specifiers:
            c(spec, st)
        c(node.source, st, "Expression")

    def ImportExpression(node, st, c):
        c(node.source, st, "Expression")

    def ImportSpecifier(node, st, c):
        return ignore(node, st, c)

    def ImportDefaultSpecifier(node, st, c):
        return ignore(node, st, c)

    def ImportNamespaceSpecifier(node, st, c):
        return ignore(node, st, c)

    def Identifier(node, st, c):
        return ignore(node, st, c)

    def PrivateIdentifier(node, st, c):
        return ignore(node, st, c)

    def Literal(node, st, c):
        return ignore(node, st, c)

    def TaggedTemplateExpression(node, st, c):
        c(node.tag, st, "Expression")
        c(node.quasi, st, "Expression")

    def ClassDeclaration(node, st, c):
        return c(node, st, "Class")

    def ClassExpression(node, st, c):
        return c(node, st, "Class")

    def Class(node, st, c):
        if node.id:
            c(node.id, st, "Pattern")
        if node.superClass:
            c(node.superClass, st, "Expression")
        c(node.body, st)

    def ClassBody(node, st, c):
        for elt in node.body:
            c(elt, st)

    def MethodDefinition(node, st, c):
        if node.computed:
            c(node.key, st, "Expression")
        if node.value:
            c(node.value, st, "Expression")

    def PropertyDefinition(node, st, c):
        if node.computed:
            c(node.key, st, "Expression")
        if node.value:
            c(node.value, st, "Expression")

    def Property(node, st, c):
        if node.computed:
            c(node.key, st, "Expression")
        if node.value:
            c(node.value, st, "Expression")

import esprima

code = '''
let test = "hey";
function ok() {
    alert(23)
}
'''

def LiteralCallback(node, *args, **kwargs):
    print(node)

simple(esprima.parse(code), {
    'Literal': LiteralCallback
})