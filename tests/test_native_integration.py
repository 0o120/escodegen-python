import copy
from pathlib import Path
import sys
import unittest
from escodegen import generate


PARSER = Path(__file__).resolve().parents[2] / 'esprima-python'
if PARSER.exists():
    sys.path.insert(0, str(PARSER))
try:
    import esprima
except ImportError:
    esprima = None


@unittest.skipUnless(esprima is not None, 'optional coordinated parser required')
class NativeIntegrationTests(unittest.TestCase):
    def test_native_and_serialized_nodes_match(self):
        sources = ['const x=1; function f(a=2){return a+x}',
                   'async function f(x){return await x}',
                   'const obj={...x,a:1}; const [first,...rest]=list;',
                   'import x from "m"; export default x;']
        for source in sources:
            tree = esprima.parseModule(source) if source.startswith('import') else esprima.parseScript(source)
            mapping = tree.toDict()
            before = copy.deepcopy(mapping)
            self.assertEqual(generate(tree), generate(mapping))
            self.assertEqual(tree.toDict(), before)

    def test_native_location_source_maps(self):
        tree = esprima.parseScript('const x=1;', {'loc': True, 'range': True})
        result = generate(tree, {'sourceMap': 'input.js', 'sourceMapWithCode': True})
        self.assertEqual(result.code, 'const x = 1;')
        self.assertEqual(result.map.toJSON()['sources'], ['input.js'])


if __name__ == '__main__':
    unittest.main()
