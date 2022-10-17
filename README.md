## Escodegen
[![npm version](https://badge.fury.io/js/escodegen.svg)](http://badge.fury.io/js/escodegen)
[![Build Status](https://secure.travis-ci.org/estools/escodegen.svg)](http://travis-ci.org/estools/escodegen)
[![Dependency Status](https://david-dm.org/estools/escodegen.svg)](https://david-dm.org/estools/escodegen)
[![devDependency Status](https://david-dm.org/estools/escodegen/dev-status.svg)](https://david-dm.org/estools/escodegen#info=devDependencies)

**Escodegen** ([escodegen](http://github.com/estools/escodegen)) is an
[ECMAScript](http://www.ecma-international.org/publications/standards/Ecma-262.htm)
(also popularly known as [JavaScript](http://en.wikipedia.org/wiki/JavaScript))
code generator from [Mozilla's Parser API](https://developer.mozilla.org/en/SpiderMonkey/Parser_API)
AST. See the [online generator](https://estools.github.io/escodegen/demo/index.html)
for a demo. This repository contains the Python translation of Escodegen.


### Install

    pip install escodegen

### Usage

A simple example: the program
````js
import escodegen

escodegen.generate({
    'type': 'BinaryExpression',
    'operator': '+',
    'left': { 'type': 'Literal', 'value': 40 },
    'right': { 'type': 'Literal', 'value': 2 }
})
````
produces the string `'40 + 2'`.


See the [API page](https://github.com/estools/escodegen/wiki/API) for
options.
