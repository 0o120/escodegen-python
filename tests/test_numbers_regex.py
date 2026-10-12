import json
import math
import random
import shutil
import subprocess
import unittest
from escodegen import generate


class NumberRegexTests(unittest.TestCase):
    def test_number_domain_and_negative_zero_policy(self):
        for value in [10 ** 1000]:
            with self.assertRaisesRegex(ValueError, 'bigint'):
                generate({'type': 'Literal', 'value': value})
        self.assertEqual(generate({'type': 'Literal', 'value': 9007199254740993}), '9007199254740992.0')
        with self.assertRaisesRegex(ValueError, 'NaN'):
            generate({'type': 'Literal', 'value': math.nan})
        self.assertEqual(generate({'type': 'Literal', 'value': -0.0}), '-0')
        self.assertEqual(generate({'type': 'Literal', 'value': math.inf}), '1e400')
        self.assertEqual(generate({'type': 'Literal', 'value': -math.inf}), '-1e400')
        self.assertEqual(generate({'type': 'Literal', 'value': math.inf}, {'format': {'json': True}}), 'null')

    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_numeric_shortening_preserves_binary64(self):
        random_source = random.Random(2026)
        values = [0.0, -0.0, 1000000.0, 1000000000000000000, 0.001, -0.25, 2.0 ** 53, 1e300, 1e-300]
        values += [random_source.uniform(-1e30, 1e30) for _ in range(250)]
        codes = [generate({'type': 'Literal', 'value': value}, {'format': {'renumber': True, 'hexadecimal': True}}) for value in values]
        source = 'console.log(JSON.stringify([' + ','.join('[' + code + ',Object.is(' + code + ',-0)]' for code in codes) + ']))'
        result = subprocess.run(['node', '-e', source], text=True, capture_output=True, check=True)
        for expected, (actual, negative_zero) in zip(values, json.loads(result.stdout)):
            self.assertEqual(float(actual), float(expected))
            self.assertEqual(negative_zero, expected == 0 and math.copysign(1, expected) < 0)
        self.assertEqual(codes[2], '1e6')

    def test_modern_regex_source_and_combined_flags(self):
        patterns = [(r'(?<name>a)\k<name>', 'dgimu'), (r'[\p{ASCII}&&\p{Letter}]', 'v'),
                    (r'a\/b', 'gim'), ('', ''), ('a/b', ''), ('line\nnext', '')]
        for pattern, flags in patterns:
            code = generate({'type': 'Literal', 'value': None, 'regex': {'pattern': pattern, 'flags': flags}})
            self.assertTrue(code.endswith('/' + flags))
            self.assertNotIn('\n', code)
            if shutil.which('node'):
                result = subprocess.run(['node', '--check'], input=code + ';', text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(generate({'type': 'Literal', 'value': '/a/gim'}), "'/a/gim'")
        for flags in ['gg', 'uv', 'z']:
            with self.assertRaisesRegex(ValueError, 'flags'):
                generate({'type': 'Literal', 'value': None, 'regex': {'pattern': 'x', 'flags': flags}})

    def test_unknown_nodes_have_actionable_diagnostics(self):
        for node in [{'type': 'FutureNode'}, {}]:
            with self.assertRaises(ValueError):
                generate(node)


if __name__ == '__main__':
    unittest.main()
