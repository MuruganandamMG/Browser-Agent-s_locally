import unittest
from unittest.mock import patch

from agent.policy import assess, redact_action, validate_action, validate_url


class PolicyTests(unittest.TestCase):
    def test_website_actions_do_not_request_routine_confirmation(self):
        for action, target in [
            ({'action': 'click', 'page': 1, 'ref': 'e1'}, {'tag': 'button', 'text': 'Publish'}),
            ({'action': 'fill', 'page': 1, 'ref': 'e1', 'value': 'Draft text'}, {'tag': 'textarea'}),
            ({'action': 'press', 'page': 1, 'ref': 'e1', 'value': 'Enter'}, {'tag': 'input', 'form_method': 'post'}),
        ]:
            with self.subTest(action=action):
                self.assertEqual(assess(action, {'url': 'https://example.com/', 'target': target})['status'], 'ok')

    def test_closed_action_specific_schema(self):
        for action in ({'action': 'eval', 'code': 'x'}, {'action': 'read', 'page': True},
                       {'action': 'click', 'page': 1}, {'action': 'fill', 'page': 1, 'ref': 'e1'},
                       {'action': 'read', 'page': 1, 'value': 'ignored'},
                       {'action': 'press', 'page': 1, 'ref': 'e1', 'value': 'Control+L'}):
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate_action(action)
        validate_action({'action': 'fill', 'page': 1, 'ref': 'e1', 'value': 'hello'})

    def test_url_rejects_local_credentials_schemes_and_dns(self):
        for url in ('file:///etc/passwd', 'https://localhost/', 'http://127.0.0.1',
                    'https://[::1]/', 'https://user:pass@example.com', 'http://2130706433/',
                    'https://example.com:9010/', 'https://example.com/\n'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)
        with patch('agent.policy.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('10.0.0.2', 443))]):
            with self.assertRaises(ValueError):
                validate_url('https://public-looking.example')

    def test_public_and_mixed_dns(self):
        with patch('agent.policy.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))]):
            self.assertEqual(validate_url('https://example.com/'), 'https://example.com/')
        with patch('agent.policy.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443)), (2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaises(ValueError):
                validate_url('https://example.com/')

    def test_automatic_actions_use_current_state_without_an_approval(self):
        action = {'action': 'click', 'page': 1, 'ref': 'e1'}
        context = {'url': 'https://example.com/', 'target': {'tag': 'button', 'text': 'Publish'},
                   'form': [{'name': 'body', 'value': 'draft'}]}
        self.assertEqual(assess(action, context)['status'], 'ok')
        fingerprint = 'legacy-approval'
        self.assertEqual(assess(action, context, fingerprint)['status'], 'ok')
        for key, value in [('url', 'https://example.com/changed'), ('target', {'text': 'Send'}), ('form', [])]:
            changed = dict(context, **{key: value})
            self.assertEqual(assess(action, changed, fingerprint)['status'], 'ok')

    def test_restricted_actions_stay_blocked_but_ordinary_unknown_targets_run(self):
        action = {'action': 'fill', 'page': 1, 'ref': 'e1', 'value': 'secret'}
        for target in ({'type': 'password'}, {'text': 'Credit card number'}, {'text': 'Delete account'}):
            context = {'url': 'https://example.com/', 'target': target}
            self.assertEqual(assess(action, context, 'legacy-approval')['status'], 'denied')
        self.assertEqual(assess(action, {'url': 'https://example.com/', 'target': {}})['status'], 'ok')

    def test_search_is_automatic_but_private_data_is_denied(self):
        action = {'action': 'fill', 'page': 1, 'ref': 'e1', 'value': 'public browser documentation'}
        context = {'url': 'https://example.com/', 'target': {'tag': 'input', 'type': 'search', 'name': 'q'}}
        self.assertEqual(assess(action, context)['status'], 'ok')
        self.assertEqual(assess(dict(action, value='sk-proj-' + 'a' * 30), context)['status'], 'denied')

    def test_secrets_rejected_before_intent_and_redacted_for_persistence(self):
        action = {'action': 'fill', 'page': 1, 'ref': 'e1', 'value': 'sk-proj-' + 'a' * 30}
        with self.assertRaises(ValueError):
            validate_action(action)
        self.assertEqual(redact_action(action)['value'], '[redacted]')
        self.assertEqual(action['value'], 'sk-proj-' + 'a' * 30)
        self.assertEqual(redact_action(dict(action, value='ordinary but could be a password'))['value'], '[redacted]')

    def test_post_search_cross_origin_and_next_proceed_automatically(self):
        context = {'url': 'https://example.com/', 'target': {'tag': 'input', 'type': 'search', 'name': 'q', 'form_method': 'post'}}
        action = {'action': 'press', 'page': 1, 'ref': 'e1', 'value': 'Enter'}
        self.assertEqual(assess(action, context)['status'], 'ok')
        context['target'] = {'tag': 'input', 'type': 'search', 'name': 'q', 'form_action': 'https://another.example/search'}
        self.assertEqual(assess(action, context)['status'], 'ok')
        context['target'] = {'tag': 'button', 'text': 'Next', 'type': 'submit'}
        self.assertEqual(assess({'action': 'click', 'page': 1, 'ref': 'e1'}, context)['status'], 'ok')

    def test_mutation_urls_cannot_bypass_policy_via_navigation(self):
        for kind in ('new_tab', 'navigate'):
            action = {'action': kind, 'url': 'https://example.com/delete/account'}
            if kind == 'navigate':
                action['page'] = 1
            context = {'url': 'https://example.com/'}
            self.assertEqual(assess(action, context, 'legacy-approval')['status'], 'denied')
        action = {'action': 'click', 'page': 1, 'ref': 'e1'}
        context = {'url': 'https://example.com/', 'target': {'tag': 'a', 'href': 'https://example.com/unsubscribe', 'text': 'Unsubscribe'}}
        self.assertEqual(assess(action, context)['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
