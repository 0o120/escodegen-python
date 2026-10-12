import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from escodegen import generate


REFERENCE = Path(os.environ.get('ESCODEGEN_REFERENCE_NODE_MODULES',
    str(Path(__file__).resolve().parents[2] / 'esprima-python' / 'tools' / 'reference' / 'node_modules')))


def at(node, line, column, source='input.js'):
    return dict(node, loc={'start': {'line': line, 'column': column},
                          'end': {'line': line, 'column': column + 1}, 'source': source})


class SourceMapTests(unittest.TestCase):
    def test_mapping_metadata_and_empty_source_content(self):
        result = generate(at({'type': 'Literal', 'value': 1}, 2, 7), {
            'sourceMap': 'input.js', 'sourceMapWithCode': True, 'sourceContent': '',
            'file': 'out.js', 'sourceMapRoot': '/src'})
        mapping = result.map.toJSON()
        self.assertEqual(result.code, '1')
        self.assertEqual(mapping['sources'], ['input.js'])
        self.assertEqual(mapping['sourcesContent'], [''])
        self.assertEqual(mapping['file'], 'out.js')
        self.assertEqual(mapping['sourceRoot'], '/src')
        self.assertEqual(json.loads(result.map.toString()), mapping)

    @unittest.skipUnless(shutil.which('node') and (REFERENCE / 'source-map').exists(), 'pinned independent consumer required')
    def test_independent_consumer_utf16_and_multiline_lookups(self):
        ast = {'type': 'Program', 'body': [
            {'type': 'ExpressionStatement', 'expression': at({'type': 'Literal', 'value': '\U0001f600'}, 3, 8)},
            {'type': 'ExpressionStatement', 'expression': at({'type': 'Identifier', 'name': 'answer'}, 9, 15)}]}
        script = 'const {SourceMapConsumer}=require(' + json.dumps(str(REFERENCE / 'source-map')) + ');' + (
            'let s="";process.stdin.on("data",d=>s+=d);process.stdin.on("end",async()=>{'
            'const d=JSON.parse(s);await SourceMapConsumer.with(d.map,null,c=>{'
            'console.log(JSON.stringify(d.positions.map(p=>c.originalPositionFor(p))))})});')
        for compact in [False, True]:
            result = generate(ast, {'sourceMap': True, 'sourceMapWithCode': True,
                                   'format': {'compact': compact, 'escapeless': True}})
            line = 1 if compact else 2
            column = 5 if compact else 0  # emoji occupies two UTF-16 units.
            payload = {'map': result.map.toJSON(), 'positions': [
                {'line': 1, 'column': 0}, {'line': line, 'column': column}]}
            process = subprocess.run(['node', '-e', script], input=json.dumps(payload), capture_output=True, text=True, check=True)
            positions = json.loads(process.stdout)
            self.assertEqual([(p['line'], p['column']) for p in positions], [(3, 8), (9, 15)])
            self.assertEqual(positions[1]['name'], 'answer')

    def test_invalid_locations_are_errors(self):
        with self.assertRaisesRegex(ValueError, 'source-map locations'):
            generate(at({'type': 'Literal', 'value': 1}, 0, 0), {'sourceMap': 'x.js'})


if __name__ == '__main__':
    unittest.main()
