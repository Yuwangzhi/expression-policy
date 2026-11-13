"""Behavioral tests: temporary overrides, isolation, native hooks, install coexistence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import expression_policy


class ExpressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name)/'config'
        self.config.mkdir()
        (self.config/'rules.md').write_text('TEST_RULE: preserve evidence; remove empty hedging.', encoding='utf-8')
        self.env = dict(os.environ, EXPRESSION_STATE_DIR=self.tmp.name+'/state',
                        EXPRESSION_CONFIG_DIR=str(self.config))

    def cli(self, action='status', session='alpha', client='claude'):
        r = subprocess.run([sys.executable, str(ROOT/'expression_policy.py'), action,
                            '--session', session, '--client', client], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def hook(self, prompt='', event='UserPromptSubmit', session='alpha', client='claude', **extra):
        data = dict(hook_event_name=event, session_id=session, prompt=prompt, cwd=self.tmp.name, **extra)
        r = subprocess.run([sys.executable, str(ROOT/'expression_policy.py'), 'hook', '--client', client],
                           input=json.dumps(data), env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_default_and_cli_wiring(self):
        self.assertTrue(self.cli()['effective'])
        self.assertTrue(self.cli()['notice'])

    def test_context_and_visible_input_notice(self):
        out = self.hook('解释原理')
        self.assertIn('TEST_RULE', out['hookSpecificOutput']['additionalContext'])
        self.assertIn('开启', out['systemMessage'])
        self.assertNotIn('decision', out)
        self.assertNotIn('CCL', out['systemMessage'])

    def test_one_turn_pause_restores_on_next_input(self):
        self.hook('本轮暂停表达规范，写一首诗')
        self.assertFalse(self.cli()['effective'])
        self.hook('现在解释原理')
        self.assertTrue(self.cli()['effective'])

    def test_session_pause_isolated_and_resume(self):
        self.hook('暂停表达规范')
        self.hook('继续')
        self.assertFalse(self.cli()['effective'])
        self.assertTrue(self.cli(session='beta')['effective'])
        self.assertTrue(self.cli(client='codex')['effective'])
        self.hook('恢复表达规范')
        self.assertTrue(self.cli()['effective'])

    def test_quoted_or_hypothetical_commands_do_not_toggle(self):
        for prompt in ['请解释“暂停表达规范”是什么意思', '> 暂停表达规范',
                       '```\n暂停表达规范\n```', '如果我说暂停表达规范怎么办？']:
            self.hook(prompt)
            self.assertTrue(self.cli()['effective'])

    def test_notice_toggle_does_not_disable_rules(self):
        out = self.hook('隐藏表达提示')
        self.assertNotIn('systemMessage', out)
        self.assertTrue(self.cli()['effective'])
        out = self.hook('显示表达提示')
        self.assertIn('systemMessage', out)

    def test_stop_reports_status_without_claiming_review_or_looping(self):
        self.hook('暂停表达规范', client='codex')
        out = self.hook(event='Stop', client='codex')
        self.assertIn('暂停', out['systemMessage'])
        self.assertNotIn('decision', out)
        self.assertEqual(self.hook(event='Stop', client='codex', stop_hook_active=True), {})

    def test_cli_once_applies_to_next_turn_only(self):
        self.cli('once')
        self.hook('第一轮')
        self.assertFalse(self.cli()['effective'])
        self.hook('第二轮')
        self.assertTrue(self.cli()['effective'])

    def test_codex_duplicate_turn_does_not_consume_once(self):
        self.cli('once', client='codex')
        self.hook('开始', client='codex', turn_id='turn-1')
        self.hook('开始', client='codex', turn_id='turn-1')
        self.assertFalse(self.cli(client='codex')['effective'])
        self.hook('继续', client='codex', turn_id='turn-2')
        self.assertTrue(self.cli(client='codex')['effective'])

    def test_notifications_cannot_switch_style_or_consume_once(self):
        self.hook('本轮暂停表达规范')
        for extra in ({'isMeta': True}, {'origin': {'kind': 'plugin'}}, {'origin': None}):
            self.assertEqual(self.hook('恢复表达规范', **extra), {})
            self.assertFalse(self.cli()['effective'])
        self.hook('继续', origin={'kind': 'human'})
        self.assertTrue(self.cli()['effective'])

    def test_missing_session_does_not_create_shared_override(self):
        out = self.hook('暂停表达规范', session='')
        self.assertIn('session', out['systemMessage'].lower())
        self.assertTrue(self.cli()['effective'])

    def test_checkout_falls_back_to_bundled_rules(self):
        store = expression_policy.StyleStore(Path(self.env['EXPRESSION_STATE_DIR']), Path(self.tmp.name)/'absent')
        self.assertEqual(store.rules_path(), ROOT/'rules/expression.md')
        self.assertIn('默认表达规范', store.rules()[0])

    def test_hook_command_matching_is_exact(self):
        program = ROOT/'expression_policy.py'
        command = expression_policy.hook_command(sys.executable, program, 'codex')
        self.assertTrue(expression_policy.is_hook_command(command, program, 'codex'))
        self.assertFalse(expression_policy.is_hook_command(command, program, 'claude'))
        self.assertFalse(expression_policy.is_hook_command(command+'; echo keep', program, 'codex'))
        foreign = expression_policy.hook_command(sys.executable, self.tmp.name+'/expression_policy.py', 'codex')
        self.assertFalse(expression_policy.is_hook_command(foreign, program, 'codex'))
        self.assertFalse(expression_policy.is_hook_command('codex exec test', program, 'codex'))


if __name__ == '__main__':
    unittest.main()
