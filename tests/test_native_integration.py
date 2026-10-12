import copy
from pathlib import Path
import sys
import unittest
import shutil
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
                   'import x from "m"; export default x;',
                   'const x=a?.b??c; x??=value; x&&=other; x||=last;',
                   'const b=900719925474099312345n; const n=1_000_000;',
                   'async function* f(xs){for await(const x of xs){yield await x}}',
                   'class C {#x=1; static{this.x=2} has(o){return #x in o}}',
                   'try{f()}catch{g()}',
                   'import data from "m" with {type:"json"}; export {data as "a b"};',
                   'export * as ns from "m";',
                   'const p=import("m",{with:{type:"json"}});']
        for source in sources:
            tree = esprima.parseModule(source) if source.startswith(('import', 'export')) else esprima.parseScript(source)
            mapping = tree.toDict()
            before = copy.deepcopy(mapping)
            self.assertEqual(generate(tree), generate(mapping))
            self.assertEqual(tree.toDict(), before)

    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_native_modern_pipeline_against_independent_parser(self):
        from test_roundtrip import parse_many, REFERENCE
        if not (REFERENCE / 'acorn').exists():
            self.skipTest('pinned reference parser required')
        jobs = [
            {'source': 'class C {#x=1;static{this.x=2} has(o){return #x in o}}'},
            {'source': 'async function* f(xs){for await(const x of xs){yield await x}}'},
            {'source': 'const x=a?.b??c; x??=900719925474099312345n;'},
            {'source': 'import data from "m" with {type:"json"}; export {data as "a b"};', 'module': True},
            {'source': 'export * as ns from "m"; await import("m",{with:{type:"json"}});', 'module': True},
        ]
        expected = parse_many([dict(job, normalized=True) for job in jobs])
        generated = []
        for job in jobs:
            tree = esprima.parseModule(job['source']) if job.get('module') else esprima.parseScript(job['source'])
            generated.append(dict(job, source=generate(tree), normalized=True))
        self.assertEqual(parse_many(generated), expected)

    def test_native_location_source_maps(self):
        tree = esprima.parseScript('const x=1;', {'loc': True, 'range': True})
        result = generate(tree, {'sourceMap': 'input.js', 'sourceMapWithCode': True})
        self.assertEqual(result.code, 'const x = 1;')
        self.assertEqual(result.map.toJSON()['sources'], ['input.js'])


if __name__ == '__main__':
    unittest.main()
