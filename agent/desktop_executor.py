"""Desktop observe/approve/act/observe loop using Agent Desktop's native MCP tools."""

import json
import os
from pathlib import Path

from desktop_client import DesktopClient
from .desktop_policy import FIELDS, READS, validate_action, fingerprint


ACTION_TOOL = {'type': 'function', 'function': {
    'name': 'desktop_action',
    'description': 'Operate Windows apps through Agent Desktop. Start with list_apps/list_windows then snapshot with the exact app image name. Use qualified refs from that app snapshot. All mutations need user approval. Use set_value for semantic text; type and mouse_move require headed=true (physical cursor/keyboard). Never add headed after a failure. Snapshot after each mutation to verify. Launch accepts notepad, calc, explorer or code only.',
    'parameters': {'type': 'object', 'properties': {
        'action': {'type': 'string', 'enum': list(FIELDS)},
        **{key: {'type': 'string'} for key in ('app', 'window_id', 'ref', 'value', 'combo', 'xy')},
        'headed': {'type': 'boolean'},
    }, 'required': ['action'], 'additionalProperties': False}}}


def nodes(tree):
    if not isinstance(tree, dict):
        return
    yield tree
    for child in tree.get('children', []):
        yield from nodes(child)


class DesktopExecutor:
    def __init__(self, client=None):
        self.client = client or DesktopClient()

    def _session(self, state):
        self.client.configure(session=state.get('session_id'), headed=False)
        if not state.get('session_id'):
            result = self.client.call('desktop_session_start', {'name': 'Local assistant', 'no_trace': True})
            if not result['ok']:
                raise ValueError('Cannot start an Agent Desktop session.')
            state['session_id'] = result['data']['session_id']
            self.client.configure(session=state['session_id'], headed=False)
        overlay = self.client.call('desktop_cursor_overlay_enable', {'label': 'Local assistant', 'accent': '#4299FF'})
        state['cursor'] = bool(overlay.get('ok') and overlay.get('data', {}).get('rendered'))
        state.setdefault('apps', {})

    def run(self, action, state, approved_fingerprint=None):
        validate_action(action)
        kind = action['action']
        app = action.get('app')
        observed = state.get('apps', {}).get(app, {})
        window_id = action.get('window_id') or observed.get('window_id')
        target = None
        if 'ref' in action:
            target = next((n for n in nodes(observed.get('tree')) if n.get('ref_id') == action['ref']), None)
            if target is None:
                return {'ok': False, 'status': 'denied', 'error': 'Ref is not in this task\'s latest app snapshot. Observe again.'}
        if kind == 'press' and (not observed or observed.get('window_id') != action['window_id']):
            return {'ok': False, 'status': 'denied', 'error': 'Observe this exact app window before pressing keys.'}
        target = target or {'app': app, 'window_id': action.get('window_id')}
        if kind not in READS:
            token = fingerprint(action, target)
            if token != approved_fingerprint:
                physical = action.get('headed') or kind == 'press'
                return {'ok': False, 'status': 'approval_required', 'approval': {
                    'fingerprint': token, 'target': target,
                    'reason': ('Uses physical input and may move your mouse or take keyboard focus. ' if physical else '') +
                              'Review this exact desktop operation before it runs.'}}
        try:
            self._session(state)
            self.client.configure(session=state['session_id'], headed=action.get('headed', False))
            if kind in ('set_value', 'type') and 'value' in target:
                current = self.client.call('desktop_get', {'ref_id': action['ref'], 'property': 'value'})
                if not current.get('ok') or current.get('data', {}).get('value') != target['value']:
                    state['apps'] = {}
                    return {'ok': False, 'status': 'error', 'verified': False,
                            'error': 'The editable value changed or could not be checked. Snapshot again before proposing text input.'}
            args = {key: action[key] for key in ('app', 'window_id') if key in action}
            if kind == 'snapshot':
                args.update(include_bounds=True, compact=True, timeout_ms=8000, max_depth=12)
            elif kind in ('click', 'set_value', 'type'):
                args = {'ref_id': action['ref'], 'timeout_ms': 5000}
                if 'value' in action:
                    args['text' if kind == 'type' else 'value'] = action['value']
            elif kind == 'press':
                args['combo'] = action['combo']
            elif kind == 'mouse_move':
                args = {'xy': action['xy']}
            elif kind == 'launch':
                args['timeout'] = 8000
            if kind == 'launch' and app.lower() in ('code', 'code.exe'):
                code = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Microsoft VS Code/Code.exe'
                if not code.is_file():
                    code = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Microsoft VS Code/Code.exe'
                if not code.is_file():
                    return {'ok': False, 'status': 'error', 'error': 'VS Code was not found in its standard install locations.'}
                args['app'] = str(code)
            envelope = self.client.call('desktop_' + kind, args)
            data = envelope.get('data', {})
            if kind not in READS:
                # Any UI mutation invalidates all saved refs, including other apps affected by it.
                state['apps'] = {}
            if not envelope['ok']:
                error = envelope.get('error', {})
                uncertain = kind not in READS and error.get('disposition', {}).get('delivery') != 'not_delivered'
                return {'ok': False, 'status': 'uncertain' if uncertain else 'error', 'error': error,
                        'verified': False, 'app': app, 'window_id': window_id}
            if kind == 'snapshot':
                window_id = action.get('window_id') or data.get('window', {}).get('id') or data.get('window_id')
                state.setdefault('scopes', {})[app] = window_id
                # Bound persisted/planner evidence while retaining complete refs in the kept region.
                kept, used = [], 0
                for node in nodes(data.get('tree')):
                    flat = {k: v for k, v in node.items() if k != 'children'}
                    size = len(json.dumps(flat))
                    if len(kept) >= 150 or used + size > 18000:
                        break
                    kept.append(flat)
                    used += size
                state['apps'][app] = {'window_id': window_id,
                    'tree': {'children': kept}, 'snapshot_id': data.get('snapshot_id'),
                    'complete': bool(data.get('complete')) and len(kept) == sum(1 for _ in nodes(data.get('tree')))}
                data = state['apps'][app]
            elif kind in READS:
                state['inventory'] = json.dumps(data, ensure_ascii=False)[:12000]
            return {'ok': True, 'status': 'ok', 'verified': kind in READS,
                    'app': app, 'window_id': window_id, 'observation': data, 'cursor': state.get('cursor', False)}
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
            if kind not in READS:
                state['apps'] = {}
            return {'ok': False, 'status': 'error' if kind in READS else 'uncertain',
                    'error': str(error)[:1000], 'verified': False, 'app': app, 'window_id': window_id}

    def close(self, end_session=False):
        try:
            if isinstance(self.client.session, str):
                self.client.configure(session=self.client.session, headed=False)
                self.client.call('desktop_session_end' if end_session else 'desktop_cursor_overlay_disable', {})
        except (OSError, ValueError, KeyError):
            pass
        finally:
            self.client.close()
