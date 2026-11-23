import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from server import ChatHandler, MODEL, valid_messages
from chat_tools import TOOLS


class ChatTests(unittest.TestCase):
    def test_message_validation(self):
        self.assertTrue(valid_messages([{'role': 'user', 'content': 'Hi'}]))
        self.assertTrue(valid_messages([
            {'role': 'user', 'content': 'Hi'},
            {'role': 'assistant', 'content': 'Hello'},
            {'role': 'user', 'content': 'Continue'},
        ]))
        for value in (None, [], [None], [{'role': 'system', 'content': 'test'}],
                      [{'role': 'user', 'content': ' '}], [{'role': 'user', 'content': 1}],
                      [{'role': 'assistant', 'content': 'test'}],
                      [{'role': 'user', 'content': 'x' * 20001}],
                      [{'role': 'user', 'content': 'Hi'}] * 101):
            with self.subTest(value=str(value)[:80]):
                self.assertFalse(valid_messages(value))

    def test_http_chat_and_validation(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), ChatHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        def request(body, host='127.0.0.1:3000', length=None):
            connection = HTTPConnection(*server.server_address, timeout=5)
            try:
                connection.request('POST', '/api/chat', body, {
                    'Host': host, 'Content-Type': 'application/json',
                    'Content-Length': str(len(body.encode()) if length is None else length),
                })
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

        with patch('server.lm_request') as upstream:
            upstream.return_value = {'choices': [{'message': {'content': 'Hello!'}, 'finish_reason': 'stop'}]}
            messages = [{'role': 'user', 'content': 'Hi'}]
            status, result = request(json.dumps({'messages': messages}))
            self.assertEqual(status, 200)
            self.assertEqual(result['reply'], 'Hello!')
            self.assertEqual(result['model'], MODEL)
            self.assertFalse(result['truncated'])
            self.assertIsNone(result['metrics']['average_tokens_per_second'])
            self.assertIsNone(result['metrics']['output_tokens'])
            upstream.assert_called_once_with('/chat/completions', {
                'model': MODEL, 'messages': upstream.call_args.args[1]['messages'], 'stream': False, 'max_tokens': 2048,
                'chat_template_kwargs': {'enable_thinking': True},
                'tools': TOOLS, 'tool_choice': 'auto',
            })
            self.assertEqual(upstream.call_args.args[1]['messages'][0]['role'], 'system')
            self.assertEqual(upstream.call_args.args[1]['messages'][1:], messages)
            upstream.return_value['usage'] = {
                'prompt_tokens': 20, 'completion_tokens': 40, 'total_tokens': 60,
                'completion_tokens_details': {'reasoning_tokens': 30},
            }
            with patch('server.perf_counter', side_effect=[10, 12]):
                status, result = request(json.dumps({'messages': messages}))
            self.assertEqual(status, 200)
            self.assertEqual(result['metrics'], {
                'response_seconds': 2, 'input_tokens': 20, 'output_tokens': 40,
                'total_tokens': 60, 'reasoning_tokens': 30, 'average_tokens_per_second': 20,
            })
            tool_response = {'choices': [{'message': {'content': None, 'tool_calls': [{
                'id': 'call_1', 'type': 'function', 'function': {
                    'name': 'calculate', 'arguments': '{"operation":"multiply","a":6,"b":7}',
                },
            }]}, 'finish_reason': 'tool_calls'}], 'usage': upstream.return_value['usage']}
            upstream.side_effect = [tool_response, upstream.return_value]
            status, result = request(json.dumps({'messages': messages}))
            self.assertEqual(status, 200)
            self.assertEqual(result['tool_calls'][0]['output'], {'result': 42})
            self.assertEqual(result['metrics']['output_tokens'], 80)
            self.assertEqual(upstream.call_args.args[1]['messages'][-1], {
                'role': 'tool', 'tool_call_id': 'call_1', 'content': '{"result": 42}',
            })
            upstream.side_effect = [tool_response] * 11
            self.assertEqual(request(json.dumps({'messages': messages}))[0], 502)
            upstream.side_effect = None
            with patch('server.MODEL', 'wizardlm-7b-uncensored'):
                self.assertEqual(request(json.dumps({'messages': messages}))[0], 200)
                payload = upstream.call_args.args[1]
                self.assertNotIn('tools', payload)
                self.assertNotIn('tool_choice', payload)
                self.assertNotIn('chat_template_kwargs', payload)
                self.assertEqual(payload['stop'], ['USER:'])
                self.assertIn('provided text', payload['messages'][0]['content'])
            for thinking in (False, True):
                self.assertEqual(request(json.dumps({'messages': messages, 'thinking': thinking}))[0], 200)
                self.assertEqual(upstream.call_args.args[1]['chat_template_kwargs'],
                                 {'enable_thinking': thinking})
            for invalid in ('false', 0, None):
                upstream.reset_mock()
                self.assertEqual(request(json.dumps({'messages': messages, 'thinking': invalid}))[0], 400)
                upstream.assert_not_called()
            upstream.reset_mock()
            self.assertEqual(request(json.dumps({'messages': messages, 'voice': True, 'thinking': True}))[0], 200)
            payload = upstream.call_args.args[1]
            self.assertEqual(payload['max_tokens'], 160)
            self.assertEqual(payload['chat_template_kwargs'], {'enable_thinking': False})
            self.assertNotIn('tools', payload)
            self.assertIn('one or two short sentences', payload['messages'][0]['content'])
            upstream.assert_called_once()
            self.assertEqual(request('{')[0], 400)
            self.assertEqual(request('null')[0], 400)
            self.assertEqual(request('{}', 'example.com')[0], 403)
            self.assertEqual(request('', length=256001)[0], 413)
            upstream.side_effect = TimeoutError()
            self.assertEqual(request(json.dumps({'messages': messages}))[0], 502)


if __name__ == '__main__':
    unittest.main()
