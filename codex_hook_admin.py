"""Inspect narrowly scoped local expression hooks. --approve records explicit trust.

Uses only the local Codex app-server management API, never a model turn.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time

import expression_policy
import platform_support

EVENTS = {'sessionStart': 'session_start', 'userPromptSubmit': 'user_prompt_submit', 'stop': 'stop'}


def entries(value):
    if isinstance(value, dict):
        if 'currentHash' in value:
            yield value
        else:
            for child in value.values():
                yield from entries(child)
    elif isinstance(value, list):
        for child in value:
            yield from entries(child)


def select_hooks(response, source, program):
    """Never select a plugin, foreign config, or compound/custom shell command."""
    return [entry for entry in entries(response)
            if entry.get('source') == 'user' and not entry.get('pluginId')
            and Path(entry.get('sourcePath', '')).resolve() == source.resolve()
            and expression_policy.is_hook_command(entry.get('command'), program, 'codex')]


def approval_edits(found):
    if len(found) != 3 or {entry.get('eventName') for entry in found} != set(EVENTS):
        raise ValueError('Expected exactly three expression lifecycle hooks; no approvals written')
    edits = []
    for entry in found:
        key, digest = entry.get('key'), entry.get('currentHash')
        pattern = re.escape(entry['sourcePath']) + ':' + EVENTS[entry['eventName']] + r':\d+:\d+'
        if not isinstance(key, str) or not re.fullmatch(pattern, key):
            raise ValueError('Native hook key does not match its source/event')
        if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
            raise ValueError('Missing or unsupported native hook hash')
        for field, value in [('trusted_hash', digest), ('enabled', True)]:
            edits.append({'keyPath': 'hooks.state.' + json.dumps(key) + '.' + field,
                          'value': value, 'mergeStrategy': 'replace'})
    return edits


def manage(codex, codex_home, approve=False):
    source = codex_home/'hooks.json'
    env = dict(os.environ, CODEX_HOME=str(codex_home))
    process = subprocess.Popen(platform_support.executable_argv([codex, 'app-server']), env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding='utf-8', **platform_support.process_options())
    messages = queue.Queue()

    def reader():
        try:
            for line in process.stdout:
                try:
                    messages.put(json.loads(line))
                except json.JSONDecodeError:
                    pass
        finally:
            messages.put(None)

    threading.Thread(target=reader, daemon=True).start()
    seq = 0

    def request(method, params):
        nonlocal seq
        seq += 1
        process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': seq, 'method': method, 'params': params})+'\n')
        process.stdin.flush()
        deadline = time.monotonic() + 35
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Codex local API timed out: ' + method)
            reply = messages.get(timeout=remaining)
            if reply is None:
                raise RuntimeError('Codex app-server exited before replying: ' + method)
            if reply.get('id') == seq:
                if 'error' in reply:
                    raise RuntimeError(json.dumps(reply['error']))
                return reply.get('result')

    try:
        request('initialize', {'clientInfo': {'name': 'expression-policy-config', 'version': '1.0'},
                              'capabilities': {'experimentalApi': True}})
        process.stdin.write('{"jsonrpc":"2.0","method":"initialized","params":{}}\n')
        process.stdin.flush()
        found = select_hooks(request('hooks/list', {'cwd': str(Path.home())}), source,
                             Path(__file__).resolve().with_name('expression_policy.py'))
        # Do not print unrelated hook declarations, which can contain private values.
        result = {'hooks': [{k: e.get(k) for k in ('key', 'eventName', 'enabled', 'trustStatus', 'currentHash')}
                            for e in found], 'approved': False}
        if approve:
            response = request('config/batchWrite', {'edits': approval_edits(found),
                'filePath': str(codex_home/'config.toml'), 'reloadUserConfig': True})
            if response.get('status') != 'ok':
                raise RuntimeError('Codex did not confirm the approval write')
            result['approved'] = True
        return result
    finally:
        platform_support.terminate_tree(process)
        for stream in (process.stdin, process.stdout):
            stream.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex', default=os.environ.get('EXPRESSION_CODEX_BIN', 'codex'))
    parser.add_argument('--codex-home', type=Path,
                        default=Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex'))))
    parser.add_argument('--approve', action='store_true', help='Explicitly trust only the three displayed hooks')
    args = parser.parse_args(argv)
    try:
        result = manage(args.codex, args.codex_home.expanduser().resolve(), args.approve)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if len(result['hooks']) == 3 else 2
    except (ValueError, OSError, RuntimeError, TimeoutError, queue.Empty) as error:
        print(json.dumps({'error': str(error) or 'Codex local API timed out'}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
