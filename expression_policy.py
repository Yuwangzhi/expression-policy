"""Portable, local-only expression policy and session switches. No model calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import platform_support

VERSION = '1'
COMMANDS = {
    '本轮暂停表达规范': 'once', '这轮暂停表达规范': 'once',
    '本轮不用表达规范': 'once', '暂停表达规范': 'off',
    '关闭表达规范': 'off', '恢复表达规范': 'on', '开启表达规范': 'on',
    '隐藏表达提示': 'quiet', '显示表达提示': 'loud',
}


def control(prompt):
    """Only a direct, leading user command; quoted or hypothetical text is inert."""
    text = prompt.strip()
    for phrase, action in COMMANDS.items():
        if text == phrase or (text.startswith(phrase) and text[len(phrase):len(phrase)+1] in '，,。.!！;；\n'):
            return action
    return None


def hook_command(python, program, client='codex', windows=None):
    argv = [Path(python).as_posix(), '-X', 'utf8', Path(program).as_posix(), 'hook', '--client', client]
    return subprocess.list2cmdline(argv) if (os.name == 'nt' if windows is None else windows) else shlex.join(argv)


def is_hook_command(command, program, client=None):
    if not isinstance(command, str) or any(c in command for c in ('\n', '\r', '`', '$', '%', '!')):
        return False
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    expected = ['hook'] + (['--client', client] if client else [])
    return (len(parts) == 4 + len(expected) and parts[1:3] == ['-X', 'utf8'] and
            re.fullmatch(r'python(?:\d+(?:\.\d+)*)?(?:\.exe)?',
                         parts[0].replace('\\', '/').rsplit('/', 1)[-1], re.I) is not None and
            Path(parts[3]).resolve() == Path(program).resolve() and parts[4:] == expected)


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.expression-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(value, out, ensure_ascii=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class StyleStore:
    def __init__(self, state=None, config=None):
        self.state = Path(state or os.environ.get('EXPRESSION_STATE_DIR',
                          str(Path.home()/'.local/state/expression-policy')))
        self.config = Path(config or os.environ.get('EXPRESSION_CONFIG_DIR',
                          str(Path.home()/'.config/expression-policy')))

    def path(self, client, session):
        if client not in ('claude', 'codex') or not isinstance(session, str) or not session.strip() or len(session) > 512:
            raise ValueError('表达规范需要真实的 client 和 session_id，不能退化成全局开关。')
        key = hashlib.sha256((client+'\0'+session).encode()).hexdigest()
        return self.state/'sessions'/client/(key+'.json')

    def read(self, path):
        if not path.exists():
            return {'enabled': True, 'notice': True, 'effective': True, 'once_pending': False, 'turns': 0, 'turn_id': ''}
        data = json.loads(path.read_text(encoding='utf-8'))
        if any(type(data.get(k)) is not bool for k in ('enabled', 'notice', 'effective', 'once_pending')):
            raise ValueError('表达规范状态文件无效；请从备份恢复后再切换。')
        return data

    def status(self, client, session):
        path = self.path(client, session)
        with platform_support.file_lock(path.with_suffix('.lock')):
            data = self.read(path)
        return dict(data, client=client, session=session, version=VERSION)

    def update(self, client, session, action=None, prompt=None, turn_id=''):
        path = self.path(client, session)
        with platform_support.file_lock(path.with_suffix('.lock')):
            data = self.read(path)
            if prompt is not None:
                if turn_id and data.get('turn_id') == turn_id:
                    return dict(data, client=client, session=session, version=VERSION)
                data['effective'] = data['enabled'] and not data['once_pending']
                data['once_pending'] = False
                data['turns'] = data.get('turns', 0)+1
                data['turn_id'] = turn_id
                action = control(prompt)
            if action == 'off':
                data.update(enabled=False, effective=False, once_pending=False)
            elif action == 'on':
                data.update(enabled=True, effective=True, once_pending=False)
            elif action == 'once':
                data['effective'] = False
                data['once_pending'] = prompt is None
            elif action == 'quiet':
                data['notice'] = False
            elif action == 'loud':
                data['notice'] = True
            elif action not in (None, 'status', 'render'):
                raise ValueError('Unknown expression action')
            atomic(path, data)
        return dict(data, client=client, session=session, version=VERSION)

    def rules_path(self):
        configured = self.config/'rules.md'
        return configured if configured.is_file() else Path(__file__).resolve().parent/'rules/expression.md'

    def rules(self):
        text = self.rules_path().read_text(encoding='utf-8')
        return text, hashlib.sha256(text.encode()).hexdigest()[:12]

    @staticmethod
    def label(data):
        return '开启' if data['effective'] else '本轮暂停' if data['enabled'] else '暂停'

    def context(self, data, full=True):
        label = self.label(data)
        text = '表达规范 v'+VERSION+'：'+label+'；client='+data['client']+'；session='+data['session']+'。\n'
        if not data['effective']:
            text += '本轮暂停本地表达风格/编辑流程，遵守用户本轮文体；真实性与其他任务约束仍有效。\n'
        else:
            rules, digest = self.rules()
            text += '规则sha256='+digest+'；来源='+str(self.rules_path())+'。\n'
            text += rules if full else ('执行：理解任务→起草→删无信息的防御/假对比/模板套话与重复→核对事实、否定关系、'
                                        '主张强度和必要边界→交付。结论先行，具体易懂，术语一致，保持作者文体；'
                                        '不要为可读性虚构、漏信息或隐瞒失败。按全局默认表达规范全文执行。')
        if data['notice']:
            text += '\n面向用户的自由文本回复使用标记【表达规范：'+label+'】；精确JSON/代码/原文输出除外。'
            text += '标记只表示启用状态，不表示已验证输出质量。'
        else:
            text += '\n用户已隐藏表达提示：回复中不加表达状态标记。'
        return text

    def hook(self, payload, client):
        event = payload.get('hook_event_name', '')
        if event == 'Stop' and payload.get('stop_hook_active'):
            return {}
        if event == 'UserPromptSubmit' and (payload.get('isMeta') or ('origin' in payload and
                (not isinstance(payload['origin'], dict) or payload['origin'].get('kind') != 'human'))):
            return {}
        session = payload.get('session_id') or payload.get('thread_id') or ''
        data = (self.update(client, session, prompt=payload.get('prompt', ''), turn_id=payload.get('turn_id', ''))
                if event == 'UserPromptSubmit' else self.status(client, session))
        out = {}
        if event in ('SessionStart', 'UserPromptSubmit', 'PostCompact'):
            out['hookSpecificOutput'] = {'hookEventName': event,
                'additionalContext': self.context(data, full=event != 'UserPromptSubmit' or data.get('turns', 0) <= 1)}
        if data['notice'] and event in ('UserPromptSubmit', 'Stop'):
            out['systemMessage'] = '表达规范 · '+('输入' if event == 'UserPromptSubmit' else '输出')+' · '+self.label(data)
        return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'on', 'off', 'once', 'quiet', 'loud', 'render', 'hook'])
    parser.add_argument('--client', choices=['claude', 'codex'], default='claude')
    parser.add_argument('--session', default='')
    args = parser.parse_args(argv)
    store = StyleStore()
    try:
        if args.action == 'hook':
            output = store.hook(json.load(sys.stdin), args.client)
        else:
            session = args.session or os.environ.get(
                'CLAUDE_SESSION_ID' if args.client == 'claude' else 'CODEX_THREAD_ID', '')
            data = (store.status(args.client, session) if args.action in ('status', 'render')
                    else store.update(args.client, session, args.action))
            output = dict(data, context=store.context(data)) if args.action == 'render' else data
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError) as error:
        output = ({'systemMessage': '表达规范状态不可用：'+str(error)} if args.action == 'hook'
                  else {'error': str(error)})
        print(json.dumps(output, ensure_ascii=False))
        return 0 if args.action == 'hook' else 2


if __name__ == '__main__':
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    sys.exit(main())
