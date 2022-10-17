**Escodegen** ([escodegen](http://github.com/estools/escodegen)) is an
[ECMAScript](http://www.ecma-international.org/publications/standards/Ecma-262.htm)
(also popularly known as [JavaScript](http://en.wikipedia.org/wiki/JavaScript))
code generator from [Mozilla's Parser API](https://developer.mozilla.org/en/SpiderMonkey/Parser_API)
AST. See the [online generator](https://estools.github.io/escodegen/demo/index.html)
for a demo. This repository contains the Python translation of Escodegen.


## Install

    pip install escodegen

## Usage

### Example:
```python
import escodegen

escodegen.generate({
    'type': 'BinaryExpression',
    'operator': '+',
    'left': { 'type': 'Literal', 'value': 20 },
    'right': { 'type': 'Literal', 'value': 2 }
})
```
*produces the string: `'20 + 2'`*

### Example:
```python
import escodegen
import esprima

escodegen.generate(esprima.parse('let a=10;let b=30'))
```
*produces the string: `'let a = 10;\nlet b = 30;'`*

See the [API page](https://github.com/estools/escodegen/wiki/API) for
options.
