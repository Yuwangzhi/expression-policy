import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import install


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)/'home with spaces'
        self.home.mkdir()
        self.prefix = self.home/'.local/share/expression-policy'
        self.bin = self.home/'.local/bin/xpctl'
        self.config = self.home/'.config/expression-policy'
        self.state = self.home/'.local/state/expression-policy'
        self.legacy = self.home/'.local/share/claude-codex-loop/expression.py'
        self.patches = [patch.object(install, 'HOME', self.home),
                        patch.object(install, 'PREFIX', self.prefix),
                        patch.object(install, 'BIN', self.bin),
                        patch.object(install, 'CONFIG', self.config),
                        patch.object(install, 'STATE', self.state),
                        patch.object(install, 'LEGACY', self.legacy)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def settings(self, value):
        path = self.home/'.claude/settings.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def codex_hooks(self, value):
        path = self.home/'.codex/hooks.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def test_fresh_install_preserves_ccl_hooks_and_unrelated_settings(self):
        ccl = {'type': 'command', 'command': str(self.home/'.local/bin/ccl')+' hook', 'timeout': 5}
        settings = {'permissions': {'defaultMode': 'default'}, 'custom': {'keep': True},
                    'env': {'CLAUDE_CODE_PLUGIN_DIRS': str(self.home/'ccl-plugin')},
                    'hooks': {'Stop': [{'hooks': [ccl]}]}}
        self.settings(settings)
        (self.home/'.claude/CLAUDE.md').write_text(
            '<!-- BEGIN claude-codex-loop -->\nCCL rules\n<!-- END claude-codex-loop -->\n')
        monitor = {'hooks': [{'type': 'command', 'command': 'existing-monitor'}]}
        self.codex_hooks({'hooks': {'UserPromptSubmit': [monitor]}, 'custom': {'keep': True}})
        (self.home/'.codex/AGENTS.md').write_text('CCL codex rules\n')
        with contextlib.redirect_stdout(io.StringIO()):
            install.install()
        actual = json.loads((self.home/'.claude/settings.json').read_text())
        self.assertEqual(actual['permissions'], settings['permissions'])
        self.assertEqual(actual['custom'], settings['custom'])
        self.assertEqual(actual['env'], settings['env'])
        self.assertIn(ccl, actual['hooks']['Stop'][0]['hooks'])
        for event in install.EVENTS:
            handlers = [item for group in actual['hooks'][event] for item in group['hooks']]
            self.assertEqual(sum(install.expression_policy.is_hook_command(
                item.get('command'), self.prefix/'expression_policy.py', 'claude') for item in handlers), 1)
        codex = json.loads((self.home/'.codex/hooks.json').read_text())
        self.assertEqual(codex['hooks']['UserPromptSubmit'][0], monitor)
        self.assertEqual(codex['custom'], {'keep': True})
        for event in install.EVENTS:
            handlers = [item for group in codex['hooks'][event] for item in group['hooks']]
            self.assertEqual(sum(install.expression_policy.is_hook_command(
                item.get('command'), self.prefix/'expression_policy.py', 'codex') for item in handlers), 1)
        self.assertIn('claude-codex-loop', (self.home/'.claude/CLAUDE.md').read_text())
        self.assertIn('expression-policy', (self.home/'.claude/CLAUDE.md').read_text())
        self.assertIn('expression-policy', (self.home/'.codex/AGENTS.md').read_text())
        command = actual['hooks']['UserPromptSubmit'][-1]['hooks'][0]['command']
        result = subprocess.run(command, shell=True, input=json.dumps({
            'hook_event_name': 'UserPromptSubmit', 'session_id': 'installed-test',
            'prompt': '暂停表达规范'}), capture_output=True, text=True, encoding='utf-8',
            env=dict(os.environ, EXPRESSION_STATE_DIR=str(self.state), EXPRESSION_CONFIG_DIR=str(self.config)),
            check=True)
        self.assertIn('暂停', json.loads(result.stdout)['systemMessage'])

    def test_reinstall_is_idempotent_and_preserves_custom_rules_and_block(self):
        self.settings({'hooks': {}})
        self.codex_hooks({'hooks': {}})
        self.config.mkdir(parents=True)
        (self.config/'rules.md').write_text('MY_CUSTOM_RULE', encoding='utf-8')
        custom = '<!-- BEGIN expression-policy -->\nKeep my own words\n<!-- END expression-policy -->\n'
        (self.home/'.claude/CLAUDE.md').write_text(custom)
        with contextlib.redirect_stdout(io.StringIO()):
            install.install()
            first = json.loads((self.home/'.claude/settings.json').read_text())
            install.install()
        actual = json.loads((self.home/'.claude/settings.json').read_text())
        self.assertEqual(first, actual)
        self.assertEqual((self.config/'rules.md').read_text(), 'MY_CUSTOM_RULE')
        self.assertTrue((self.home/'.claude/CLAUDE.md').read_text().startswith(custom))
        for event in install.EVENTS:
            handlers = [item for group in actual['hooks'][event] for item in group['hooks']]
            self.assertEqual(len(handlers), 1)

    def test_legacy_prototype_hooks_are_migrated_without_touching_ccl(self):
        ccl = {'type': 'command', 'command': str(self.home/'.local/bin/ccl')+' hook'}
        legacy = install.expression_policy.hook_command(sys.executable, self.legacy, 'claude')
        settings = {'hooks': {'Stop': [{'hooks': [ccl, {'type': 'command', 'command': legacy}]}]}}
        self.settings(settings)
        self.codex_hooks({'hooks': {}})
        with contextlib.redirect_stdout(io.StringIO()):
            install.install()
        actual = json.loads((self.home/'.claude/settings.json').read_text())
        commands = [item['command'] for group in actual['hooks']['Stop'] for item in group['hooks']]
        self.assertIn(ccl['command'], commands)
        self.assertNotIn(legacy, commands)
        self.assertEqual(sum(install.expression_policy.is_hook_command(
            command, self.prefix/'expression_policy.py', 'claude') for command in commands), 1)

    def test_failed_install_restores_settings_and_removes_new_files(self):
        original = {'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'monitor'}]}]}}
        self.settings(original)
        original_codex = self.codex_hooks({'hooks': {}}).read_text()
        with patch.object(install, 'install_prefix', side_effect=RuntimeError('late failure')):
            with self.assertRaisesRegex(RuntimeError, 'late failure'):
                install.install()
        self.assertEqual(json.loads((self.home/'.claude/settings.json').read_text()), original)
        self.assertFalse(self.prefix.exists())
        self.assertFalse(self.bin.exists())
        self.assertEqual((self.home/'.codex/hooks.json').read_text(), original_codex)

    def test_uninstall_removes_only_our_hooks_and_keeps_ccl(self):
        ccl = {'type': 'command', 'command': str(self.home/'.local/bin/ccl')+' hook'}
        self.settings({'hooks': {'Stop': [{'hooks': [ccl]}]}})
        self.codex_hooks({'hooks': {}})
        with contextlib.redirect_stdout(io.StringIO()):
            install.install()
            install.uninstall()
        actual = json.loads((self.home/'.claude/settings.json').read_text())
        self.assertEqual(actual['hooks']['Stop'][0]['hooks'], [ccl])
        self.assertNotIn('expression-policy', (self.home/'.claude/CLAUDE.md').read_text())
        self.assertFalse(self.prefix.exists())
        self.assertFalse(self.bin.exists())

    def test_atomic_copy_failure_never_exposes_partial_runtime(self):
        destination = self.home/'runtime.py'
        destination.write_text('previous')
        def interrupted_copy(source, target):
            Path(target).write_text('partial')
            raise OSError('interrupted')
        with patch.object(install.shutil, 'copy2', side_effect=interrupted_copy):
            with self.assertRaises(OSError):
                install.copy_atomic(install.SOURCE/'expression_policy.py', destination)
        self.assertEqual(destination.read_text(), 'previous')
        self.assertEqual(list(self.home.glob('.expression-install-*')), [])


if __name__ == '__main__':
    unittest.main()
