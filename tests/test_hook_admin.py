import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import codex_hook_admin as admin
import expression_policy

FAKE = r'''import json, os, sys
from pathlib import Path
root=Path(os.environ['CODEX_HOME'])
for line in sys.stdin:
    obj=json.loads(line)
    if 'id' not in obj: continue
    method=obj['method']
    with (root/'methods.txt').open('a', encoding='utf-8') as f: f.write(method+'\n')
    if method=='initialize': result={}
    elif method=='hooks/list': result={'data':json.loads((root/'entries.json').read_text())}
    elif method=='config/batchWrite':
        (root/'writes.json').write_text(json.dumps(obj['params']))
        result={'status':'ok'}
    else:
        print(json.dumps({'id':obj['id'],'error':{'message':'Unexpected method'}}),flush=True)
        continue
    print(json.dumps({'id':obj['id'],'result':result}),flush=True)
'''


class HookApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.source = self.home/'hooks.json'
        self.program = Path(admin.__file__).resolve().with_name('expression_policy.py')
        self.command = expression_policy.hook_command(sys.executable, self.program, 'codex')
        self.found = [{'key': str(self.source)+':'+event+':0:0', 'eventName': name,
                      'sourcePath': str(self.source), 'source': 'user', 'pluginId': None,
                      'command': self.command, 'currentHash': 'sha256:'+'a'*64,
                      'enabled': True, 'trustStatus': 'untrusted'} for name,event in admin.EVENTS.items()]
        self.fake = self.home/'fake_codex.py'
        self.fake.write_text(FAKE)

    def write_entries(self, entries):
        (self.home/'entries.json').write_text(json.dumps(entries))

    def test_inspection_is_read_only_and_does_not_start_a_model(self):
        self.write_entries(self.found)
        result = admin.manage(str(self.fake), self.home)
        self.assertEqual(len(result['hooks']), 3)
        self.assertFalse(result['approved'])
        self.assertFalse((self.home/'writes.json').exists())
        self.assertEqual((self.home/'methods.txt').read_text().splitlines(), ['initialize','hooks/list'])

    def test_explicit_approval_changes_only_six_scoped_fields(self):
        self.write_entries(self.found)
        result = admin.manage(str(self.fake), self.home, approve=True)
        self.assertTrue(result['approved'])
        write = json.loads((self.home/'writes.json').read_text())
        self.assertEqual(write['filePath'], str(self.home/'config.toml'))
        self.assertEqual(len(write['edits']), 6)
        self.assertEqual({e['keyPath'] for e in write['edits']}, {
            'hooks.state.'+json.dumps(entry['key'])+'.'+field
            for entry in self.found for field in ('enabled','trusted_hash')})
        self.assertEqual((self.home/'methods.txt').read_text().splitlines(),
                         ['initialize','hooks/list','config/batchWrite'])

    def test_foreign_compound_or_plugin_handlers_never_get_selected(self):
        for change in ({'source':'plugin'}, {'pluginId':'foreign'}, {'sourcePath':str(self.home/'other.json')},
                       {'command':self.command+'; echo extra'},
                       {'command':expression_policy.hook_command(sys.executable, self.home/'foreign/expression_policy.py', 'codex')},
                       {'command':expression_policy.hook_command('/bin/bash', self.program, 'codex')},
                       {'command':expression_policy.hook_command(sys.executable, self.program, 'claude')}):
            with self.subTest(change=change):
                item = dict(self.found[0], **change)
                self.assertEqual(admin.select_hooks({'data':[item]},self.source,self.program), [])

    @unittest.skipIf(os.name == 'nt', 'Creating symlinks requires Windows developer/admin permission')
    def test_helper_path_alias_matches_the_same_real_script(self):
        alias = self.home/'linked-source'
        alias.symlink_to(self.program.parent, target_is_directory=True)
        item = dict(self.found[0], command=expression_policy.hook_command(sys.executable, alias/'expression_policy.py', 'codex'))
        self.assertEqual(admin.select_hooks([item], self.source, self.program), [item])

    def test_missing_duplicate_or_mismatched_events_do_not_write_trust(self):
        for entries in (self.found[:2], [self.found[0]]*3,
                        [dict(self.found[0], key='other:session_start:0:0')]+self.found[1:],
                        [dict(self.found[0], currentHash='not-a-native-hash')]+self.found[1:]):
            with self.subTest(entries=entries):
                self.write_entries(entries)
                with self.assertRaises(ValueError):
                    admin.manage(str(self.fake), self.home, approve=True)
                self.assertFalse((self.home/'writes.json').exists())

    def test_cli_does_not_print_unrelated_hook_commands(self):
        self.write_entries([dict(self.found[0],source='plugin',command='PRIVATE_TEST_SENTINEL')])
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            code=admin.main(['--codex',str(self.fake),'--codex-home',str(self.home)])
        self.assertEqual(code,2)
        self.assertNotIn('PRIVATE_TEST_SENTINEL',output.getvalue())


if __name__=='__main__':
    unittest.main()
