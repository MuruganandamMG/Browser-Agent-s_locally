import json
import unittest
from datetime import datetime
from chat_tools import execute_tool


class ToolTests(unittest.TestCase):
    def test_calculator(self):
        for operation, expected in [('add', 10), ('subtract', 6), ('multiply', 16), ('divide', 4)]:
            self.assertEqual(execute_tool('calculate', json.dumps(
                {'operation': operation, 'a': 8, 'b': 2})), {'result': expected})

    def test_invalid_arguments_are_tool_errors(self):
        for name, arguments in [('unknown', '{}'), ('calculate', '{'),
                                ('calculate', '[]'), ('current_time', '{"extra":1}'),
                                ('calculate', '{"operation":"divide","a":1,"b":0}'),
                                ('calculate', '{"operation":"add","a":true,"b":2}'),
                                ('calculate', '{"operation":"add","a":NaN,"b":2}')]:
            with self.subTest(arguments=arguments):
                self.assertIn('error', execute_tool(name, arguments))

    def test_clock_has_timezone(self):
        result = execute_tool('current_time', '{}')
        self.assertIsNotNone(datetime.fromisoformat(result['datetime']).tzinfo)
