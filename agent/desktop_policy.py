"""Closed desktop operations. The model never supplies a native command or global flags."""

import hashlib
import json
import re

from .policy import PRIVATE_VALUE


FIELDS = {
    'list_apps': (set(), set()), 'list_windows': (set(), {'app'}),
    'snapshot': ({'app'}, {'window_id'}), 'launch': ({'app'}, set()),
    'click': ({'app', 'ref'}, {'headed'}),
    'set_value': ({'app', 'ref', 'value'}, set()),
    'type': ({'app', 'ref', 'value'}, {'headed'}),
    'press': ({'app', 'window_id', 'combo'}, {'headed'}),
    'mouse_move': ({'xy', 'headed'}, set()),
}
READS = {'list_apps', 'list_windows', 'snapshot'}
APPS = {'notepad', 'notepad.exe', 'calc', 'calc.exe', 'explorer', 'explorer.exe', 'code', 'code.exe'}


def validate_action(action):
    if not isinstance(action, dict) or action.get('action') not in FIELDS:
        raise ValueError('Unsupported desktop action.')
    required, optional = FIELDS[action['action']]
    if not required <= action.keys() or action.keys() - required - optional - {'action'}:
        raise ValueError('Missing or unexpected desktop fields.')
    for key, value in action.items():
        if key in ('action', 'headed'):
            continue
        if not isinstance(value, str) or (key != 'value' and not value.strip()) or len(value) > (8000 if key == 'value' else 256) or '\x00' in value:
            raise ValueError(f'{key} must be a bounded nonempty string.')
    if 'headed' in action and type(action['headed']) is not bool:
        raise ValueError('headed must be a boolean.')
    if action['action'] in ('type', 'mouse_move') and action.get('headed') is not True:
        raise ValueError('This operation needs explicit headed=true and physical-input approval.')
    if 'ref' in action and not re.fullmatch(r'@[A-Za-z0-9_-]+:e[0-9]+', action['ref']):
        raise ValueError('Use a qualified @snapshot:eN ref from this task.')
    if 'xy' in action and not re.fullmatch(r'-?\d{1,5},-?\d{1,5}', action['xy']):
        raise ValueError('xy must contain bounded x,y screen coordinates.')
    if action['action'] == 'launch' and action['app'].lower() not in APPS:
        raise ValueError('Launch supports Notepad, Calculator, Explorer and VS Code only.')
    if 'combo' in action and not re.fullmatch(r'(?:ctrl\+|shift\+|alt\+)*(?:[a-z0-9]|return|enter|escape|tab|space|backspace|delete|left|right|up|down|home|end|pageup|pagedown|f[1-9]|f1[0-2])', action['combo'].lower()):
        raise ValueError('Unsupported key combo. Windows shell shortcuts and force are unavailable.')
    if PRIVATE_VALUE.search(action.get('value', '')):
        raise ValueError('Potential secrets or private information cannot be typed by desktop automation.')
    return action


def fingerprint(action, target):
    return hashlib.sha256(json.dumps({'action': action, 'target': target}, sort_keys=True).encode()).hexdigest()
