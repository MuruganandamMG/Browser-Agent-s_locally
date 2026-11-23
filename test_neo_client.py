import json
import unittest
from unittest.mock import patch

from neo_client import NeoClient, neo_browser


class NeoTests(unittest.TestCase):
    def test_sse_handshake_and_tool_request(self):
        class Response:
            headers = {'Mcp-Session-Id': 'test-session'}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                return b'data: \n\nid: 0\n\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
        with patch('neo_client.urlopen', return_value=Response()) as request:
            client = NeoClient()
            self.assertEqual(client.request('tools/list'), {'ok': True})
            self.assertEqual(client.session, 'test-session')
            body = json.loads(request.call_args.args[0].data)
            self.assertEqual(body['method'], 'tools/list')

    def test_browser_arguments_and_connection_error(self):
        self.assertIn('error', neo_browser({'action': 'open'}))
        with patch('neo_client.NEO.connect', side_effect=OSError('offline')):
            self.assertIn('Keep BrowserOS neo open', neo_browser({'code': 'return 1;'})['error'])

    def test_missing_return_requests_observation_without_repeating_actions(self):
        with patch('neo_client.NEO.connect'), patch('neo_client.NEO.call', return_value={
            'structuredContent': {'ok': True, 'logs': []},
        }):
            self.assertIn('Do not repeat actions', neo_browser({'code': 'await browser.pages.list();'})['error'])

    def test_transport_failure_invalidates_session_without_replaying_call(self):
        client = NeoClient()
        client.session = 'expired'
        with patch.object(client, 'request', side_effect=OSError('offline')) as request:
            with self.assertRaises(OSError):
                client.call('run', {'code': 'sensitive operation'})
            request.assert_called_once()
        self.assertIsNone(client.session)
