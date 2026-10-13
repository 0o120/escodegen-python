import itertools
import json
import shutil
import subprocess
import unittest

from escodegen import generate


def literal(value, **fields):
    return dict(type='Literal', value=value, **fields)


@unittest.skipUnless(shutil.which('node'), 'Node is required for independent runtime validation')
class StringTests(unittest.TestCase):
    def test_values_across_all_quote_and_escape_options(self):
        # Chinese punctuation reported by wjsw1781 (PR #4); supplementary
        # symbols and Python-repr-incompatible text reported by AugustineFulgur (#5).
        values = ['我，按钮', '\U000e0001', '\U0001f600', '\ud800', '\udfff',
                  '\\"\'\\\n\\', '\u2028\u2029', '\0' + '9']
        values += [chr(i) for i in range(32)]
        jobs = []
        for quotes, escapeless, is_json in itertools.product(
                ['single', 'double', 'auto'], [False, True], [False, True]):
            for value in values:
                code = generate(literal(value), {'format': {
                    'quotes': quotes, 'escapeless': escapeless, 'json': is_json}})
                if is_json:
                    self.assertEqual(json.loads(code), value)
                jobs.append((value, code))
        source = 'const expressions=' + json.dumps([code for _, code in jobs]) + ';' + (
            'console.log(JSON.stringify(expressions.map(s=>{const v=eval(s);'
            'return Array.from({length:v.length},(_,i)=>v.charCodeAt(i))})))')
        process = subprocess.run(['node', '-e', source], text=True, capture_output=True, check=True)
        units = json.loads(process.stdout)
        for (value, code), actual in zip(jobs, units):
            raw = value.encode('utf-16-le', 'surrogatepass')
            self.assertEqual(actual, [raw[i] | raw[i + 1] << 8 for i in range(0, len(raw), 2)], code)

    def test_selected_quote_is_escaped(self):
        self.assertEqual(generate(literal("'")), "'\\''")
        self.assertEqual(generate(literal('"'), {'format': {'quotes': 'double'}}), '"\\""')


if __name__ == '__main__':
    unittest.main()
