"""Ordinary chat tools; browser jobs use the task controller's validated actions."""

from datetime import datetime
import json
import math
import operator

TOOLS = [
    {'type': 'function', 'function': {
        'name': 'calculate',
        'description': 'Calculate arithmetic accurately using two numbers.',
        'parameters': {'type': 'object', 'properties': {
            'operation': {'type': 'string', 'enum': ['add', 'subtract', 'multiply', 'divide']},
            'a': {'type': 'number'}, 'b': {'type': 'number'},
        }, 'required': ['operation', 'a', 'b'], 'additionalProperties': False},
    }},
    {'type': 'function', 'function': {
        'name': 'current_time',
        'description': 'Get the current date and time on this computer, with UTC offset.',
        'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False},
    }},
]


def execute_tool(name, raw_arguments):
    try:
        if not isinstance(raw_arguments, str) or len(raw_arguments) > 4096:
            raise ValueError('Arguments must be a JSON object under 4096 characters.')
        args = json.loads(raw_arguments)
        if not isinstance(args, dict):
            raise ValueError('Arguments must be an object.')
        if name == 'current_time':
            if args:
                raise ValueError('current_time takes no arguments.')
            return {'datetime': datetime.now().astimezone().isoformat(timespec='seconds')}
        if name != 'calculate':
            raise ValueError('Unknown tool.')
        operations = {'add': operator.add, 'subtract': operator.sub,
                      'multiply': operator.mul, 'divide': operator.truediv}
        if set(args) != {'operation', 'a', 'b'} or args['operation'] not in operations:
            raise ValueError('Use operation (add/subtract/multiply/divide), a, and b.')
        for key in ('a', 'b'):
            value = args[key]
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e100:
                raise ValueError('Numbers must be finite and at most 1e100 in magnitude.')
        result = operations[args['operation']](args['a'], args['b'])
        return {'result': result}
    except (ValueError, TypeError, OverflowError, ZeroDivisionError) as error:
        return {'error': str(error)}
