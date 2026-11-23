"""Closed browser actions, automatic website interaction and trust-boundary checks."""

import ipaddress
import re
import socket
from urllib.parse import parse_qsl, unquote, urlsplit


FIELDS = {
    'new_tab': ({'url'}, set()), 'navigate': ({'page', 'url'}, set()),
    'snapshot': ({'page'}, set()), 'read': ({'page'}, set()),
    'click': ({'page', 'ref'}, {'expected_text'}),
    'fill': ({'page', 'ref', 'value'}, {'expected_text'}),
    'press': ({'page', 'ref', 'value'}, {'expected_text'}),
    'scroll': ({'page', 'direction'}, set()),
    'select': ({'page', 'ref', 'value'}, {'expected_text'}),
    'back': ({'page'}, set()),
    'download': ({'page'}, {'ref'}),
}
KEYS = {'Enter', 'Tab', 'Escape', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'}
RESTRICTED = re.compile(r'password|passcode|one.?time|\botp\b|\bcaptcha\b|credit.?card|card.?number|\bcvv\b|\bcvc\b|\bpay(?:ment)?\b|checkout|purchase|\bbuy\b|delete|destroy|remove account|security|api.?key|access.?token|private.?key', re.I)
PRIVATE_VALUE = re.compile(r'sk-(?:proj-)?[\w-]{15,}|-----BEGIN .*PRIVATE KEY|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b|\b(?:\d[ -]?){13,19}\b', re.I)
HUMAN = re.compile(r'captcha|verify (?:you are|your identity)|one.?time (?:code|password)|sign in to continue|log in to continue', re.I)


def validate_action(action):
    if not isinstance(action, dict) or not isinstance(action.get('action'), str) or action['action'] not in FIELDS:
        raise ValueError('Unsupported browser action.')
    required, optional = FIELDS[action['action']]
    if not required <= action.keys() or action.keys() - required - optional - {'action'}:
        raise ValueError('Missing or unexpected fields for this action.')
    if 'page' in action and (type(action['page']) is not int or not 0 <= action['page'] <= 4294967295):
        raise ValueError('page must be a nonnegative integer.')
    if 'ref' in action and (not isinstance(action['ref'], str) or not re.fullmatch(r'e[0-9]{1,10}', action['ref'])):
        raise ValueError('Use an eN reference from the latest observation.')
    for key in ('url', 'value', 'expected_text'):
        if key in action and (not isinstance(action[key], str) or len(action[key]) > 8000 or '\x00' in action[key]):
            raise ValueError(f'{key} must be a bounded string.')
    if 'expected_text' in action and not action['expected_text'].strip():
        raise ValueError('expected_text cannot be blank.')
    if action['action'] == 'press' and action['value'] not in KEYS:
        raise ValueError('Unsupported key; browser/system shortcuts are unavailable.')
    if 'direction' in action and action['direction'] not in ('up', 'down', 'left', 'right'):
        raise ValueError('Invalid scroll direction.')
    if any(PRIVATE_VALUE.search(unquote(unquote(action.get(key, '')))) for key in ('value', 'url')):
        raise ValueError('Potential secrets or private information cannot be sent by browser automation.')
    return action


def redact_action(action):
    """Copy action data with recognizable private content removed before persistence."""
    if isinstance(action, dict):
        return {key: '[redacted]' if key == 'value' and action.get('action') in ('fill', 'select') else redact_action(value)
                for key, value in action.items()}
    if isinstance(action, list):
        return [redact_action(value) for value in action]
    if isinstance(action, str) and PRIVATE_VALUE.search(action):
        return '[redacted]'
    return action


def validate_url(url):
    """Check explicit destinations and all DNS answers; this is not a network firewall."""
    if not isinstance(url, str) or not url or len(url) > 8000 or any(ord(c) < 33 for c in url) or '\\' in url:
        raise ValueError('Use a full public HTTP/HTTPS URL.')
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if parsed.scheme not in ('http', 'https') or not host or parsed.username is not None or parsed.password is not None:
            raise ValueError('Use public HTTP/HTTPS without URL credentials.')
        if parsed.port not in (None, 80, 443):
            raise ValueError('Only standard public web ports are permitted.')
        host = host.rstrip('.').lower().encode('idna').decode('ascii')
        if host in ('localhost', 'metadata.google.internal') or host.endswith(('.localhost', '.local', '.internal', '.home', '.lan')) or '%' in host:
            raise ValueError('Local and metadata destinations are blocked.')
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            if '.' not in host:
                raise ValueError('Use a public fully qualified hostname.')
            addresses = [ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)]
        if not addresses or any(not address.is_global or address.is_multicast or address.is_unspecified for address in addresses):
            raise ValueError('Private, loopback, reserved and metadata networks are blocked.')
    except (UnicodeError, OSError) as error:
        raise ValueError('Destination DNS could not be safely resolved.') from error
    return url


def assess(action, context, approved_fingerprint=None):
    kind = action['action']
    target = context.get('target') or {}
    target_text = ' '.join(str(target.get(k, '')) for k in ('tag', 'type', 'name', 'text', 'label', 'autocomplete', 'href', 'form_action'))
    if kind in ('read', 'snapshot', 'scroll', 'back'):
        return {'status': 'ok'}
    if HUMAN.search(context.get('snapshot', {}).get('text', '')) or HUMAN.search(target_text):
        return {'status': 'human_required', 'reason': 'The page requires human sign-in or verification.'}
    destination = action.get('url') or target.get('href') or ''
    parsed_destination = urlsplit(destination)
    destination_route = unquote(unquote(parsed_destination.path)) + ' ' + ' '.join(
        value for key, value in parse_qsl(parsed_destination.query) if key.lower() in ('action', 'cmd', 'do', 'operation'))
    if target.get('sensitive') or target.get('form_truncated') or target.get('type') in ('password', 'file', 'hidden') or RESTRICTED.search(target_text) or RESTRICTED.search(destination_route):
        return {'status': 'denied', 'reason': 'Credentials, payments, security, destructive actions and uploads require a dedicated authorization flow.'}
    if PRIVATE_VALUE.search(action.get('value', '')) or PRIVATE_VALUE.search(action.get('url', '')):
        return {'status': 'denied', 'reason': 'Potential secrets or private information cannot be sent by browser automation.'}
    if any(field.get('sensitive') or PRIVATE_VALUE.search(str(field.get('value', ''))) for field in context.get('form', []) if isinstance(field, dict)):
        return {'status': 'denied', 'reason': 'The form contains sensitive information; finish it directly in the browser.'}
    return {'status': 'ok'}
