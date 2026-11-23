import copy
import json
import unittest
from unittest.mock import patch

from agent.browser_executor import BrowserExecutor


def observation(page=1, url='https://example.com/'):
    return {'page': page, 'url': url, 'snapshot': {'text': '- searchbox "Search" [ref=e1]\n- button "Publish" [ref=e2]',
            'refs': ['e1', 'e2'], 'url': url}, 'target': {'tag': 'input', 'type': 'search', 'name': 'q', 'value': ''}, 'form': []}


class FakeNeo:
    def __init__(self):
        self.calls = []
        self.current = observation()
        self.failure = None
        self.changed = None
        self.owned = True
        self.discoveries = 0

    def tools(self):
        self.discoveries += 1
        return [{'name': 'run', 'inputSchema': {'properties': {'code': {}, 'maxChars': {}}, 'required': ['code']}}]

    def call(self, name, arguments):
        code = arguments['code']
        # The first line is JSON data, never model-provided executable code.
        data = json.loads(code.splitlines()[0][len('const input = '):-1])
        if data['phase'] == 'batch':
            values = []
            for job in data['jobs']:
                response = self.call(name, {'code': 'const input = ' + json.dumps(job) + ';'})
                values.append(response['structuredContent']['value'])
            return {'structuredContent': {'ok': True, 'value': values, 'logs': []}}
        self.calls.append(data)
        if data['phase'] == 'check':
            result = {'page': data.get('page', 1), 'url': self.current['url'], 'ownership': 'mine' if self.owned else 'user'}
        elif data['phase'] == 'observe':
            result = copy.deepcopy(self.current)
        elif data['phase'] == 'execute':
            if self.failure:
                raise self.failure
            if self.changed:
                self.current = copy.deepcopy(self.changed)
            result = {'page': 1, 'url': self.current['url'], 'ownership': 'mine', 'action_result': {}}
        else:
            raise AssertionError(data)
        return {'structuredContent': {'ok': True, 'value': result, 'logs': []}}


class ExecutorTests(unittest.TestCase):
    def test_image_ref_is_replaced_with_a_real_download_link(self):
        original = self.neo.call
        requested = []
        self.neo.current['target'] = {'tag': 'img'}
        def call(name, arguments):
            if name == 'download':
                requested.append(arguments['ref'])
                return {'isError': True, 'content': []}
            data = json.loads(arguments['code'].splitlines()[0][len('const input = '):-1])
            if data['phase'] == 'image_download_link':
                return {'structuredContent': {'ok': True, 'value': {'ref': 'e99'}}}
            return original(name, arguments)
        self.neo.call = call
        self.executor.run({'action': 'download', 'page': 1, 'ref': 'e1'}, self.tabs)
        self.assertEqual(requested, ['e99'])

    def test_download_requires_real_file_not_just_navigation(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.png'
            path.write_bytes(b'\x89PNG\r\n\x1a\n' + b'test image')
            original = self.neo.call
            def download(name, arguments):
                if name == 'download':
                    return {'content': [{'type': 'text', 'text': f'Downloaded "test.png" (18 bytes) on the machine running this browser, to: {path}'}]}
                return original(name, arguments)
            self.neo.call = download
            result = self.executor.run({'action': 'download', 'page': 1, 'ref': 'e1'}, self.tabs)
            self.assertTrue(result.get('verified'), result)
            self.assertEqual(result['download']['path'], str(path))
            path.unlink()
            self.assertFalse(self.executor.run({'action': 'download', 'page': 1, 'ref': 'e1'}, self.tabs).get('verified'))

    def setUp(self):
        self.neo = FakeNeo()
        self.executor = BrowserExecutor(self.neo)
        self.tabs = {'1': observation()}
        self.urls = patch('agent.browser_executor.validate_url', side_effect=lambda url: url)
        self.urls.start()
        self.addCleanup(self.urls.stop)

    def test_invalid_or_unowned_actions_never_execute(self):
        self.assertEqual(self.executor.run({'action': 'eval', 'code': 'x'}, self.tabs)['status'], 'denied')
        self.assertEqual(self.executor.run({'action': 'read', 'page': 8}, self.tabs)['status'], 'denied')
        self.neo.owned = False
        self.assertEqual(self.executor.run({'action': 'read', 'page': 1}, self.tabs)['status'], 'denied')
        self.assertFalse(any(x['phase'] == 'execute' for x in self.neo.calls))

    def test_missing_or_changed_ref_denied(self):
        for ref in ('e900', 'e2'):
            self.neo.current['snapshot']['text'] = '- searchbox "Search" [ref=e1]'
            self.assertEqual(self.executor.run({'action': 'click', 'page': 1, 'ref': ref}, self.tabs)['status'], 'error')
        self.assertFalse(any(x['phase'] == 'execute' for x in self.neo.calls))

    def test_fill_machine_verification_observes_actual_value(self):
        self.neo.changed = observation()
        self.neo.changed['target']['value'] = 'hello'
        result = self.executor.run({'action': 'fill', 'page': 1, 'ref': 'e1', 'value': 'hello'}, self.tabs)
        self.assertTrue(result['ok'])
        self.assertTrue(result['verified'])
        self.assertEqual(self.tabs['1']['target']['value'], 'hello')
        self.assertEqual(self.neo.discoveries, 1)

    def test_no_effect_fill_is_uncertain(self):
        result = self.executor.run({'action': 'fill', 'page': 1, 'ref': 'e1', 'value': 'hello'}, self.tabs)
        self.assertEqual(result['status'], 'uncertain')
        self.assertFalse(result['verified'])

    def test_automatic_submit_timeout_is_reported_without_repeating(self):
        self.neo.current['target'] = {'tag': 'button', 'text': 'Publish'}
        self.tabs['1']['target'] = self.neo.current['target']
        self.neo.failure = TimeoutError('outcome unknown')
        result = self.executor.run({'action': 'click', 'page': 1, 'ref': 'e2'}, self.tabs)
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(sum(x['phase'] == 'execute' for x in self.neo.calls), 1)

    def test_parallel_errors_isolated_and_mutations_denied(self):
        result = self.executor.run_parallel([{'action': 'read', 'page': 1}, {'action': 'click', 'page': 1, 'ref': 'e1'}], self.tabs)
        self.assertTrue(result['results'][0]['ok'])
        self.assertEqual(result['results'][1]['status'], 'denied')
        self.assertFalse(any(x['phase'] == 'execute' and x['action']['action'] == 'click' for x in self.neo.calls))

    def test_five_tab_limit(self):
        self.tabs.update({str(i): observation(i) for i in range(2, 6)})
        self.assertEqual(self.executor.run({'action': 'new_tab', 'url': 'https://example.com/'}, self.tabs)['status'], 'denied')

    def test_forbidden_redirect_is_not_read(self):
        self.neo.changed = observation(url='http://127.0.0.1/')
        with patch('agent.browser_executor.validate_url', side_effect=lambda url: (_ for _ in ()).throw(ValueError('private')) if '127.0.0.1' in url else url):
            result = self.executor.run({'action': 'navigate', 'page': 1, 'url': 'https://example.com/'}, self.tabs)
        self.assertEqual(result['status'], 'denied')
        self.assertFalse(any(x['phase'] == 'observe' and '127.0.0.1' in x['url'] for x in self.neo.calls))

    def test_click_without_fresh_evidence_is_uncertain(self):
        self.neo.current['target'] = {'tag': 'a', 'href': 'https://example.com/about', 'text': 'About'}
        result = self.executor.run({'action': 'click', 'page': 1, 'ref': 'e1'}, self.tabs)
        self.assertEqual(result['status'], 'uncertain')
        self.assertFalse(result['verified'])

    def test_link_destination_verifies_navigation(self):
        self.neo.current['target'] = {'tag': 'a', 'href': 'https://example.com/about', 'text': 'About'}
        self.neo.changed = observation(url='https://example.com/about')
        result = self.executor.run({'action': 'click', 'page': 1, 'ref': 'e1'}, self.tabs)
        self.assertTrue(result['verified'])
        self.assertEqual(result['status'], 'ok')

    def test_expected_text_must_be_new_after_click(self):
        self.neo.current['target'] = {'tag': 'a', 'href': 'https://example.com/about', 'text': 'About'}
        action = {'action': 'click', 'page': 1, 'ref': 'e1', 'expected_text': 'Search'}
        self.assertEqual(self.executor.run(action, self.tabs)['status'], 'uncertain')

    def test_parallel_unknown_open_outcome_stays_uncertain(self):
        self.neo.failure = TimeoutError('unknown open outcome')
        result = self.executor.run_parallel([{'action': 'new_tab', 'url': 'https://example.com/'}], {})
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(result['results'][0]['status'], 'uncertain')


if __name__ == '__main__':
    unittest.main()
