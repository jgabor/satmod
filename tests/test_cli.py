"""Read-only doctor and process replacement checks in disposable homes."""
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_setup import cli, RECIPE


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.engine = self.home / 'engine'
        (self.engine / 'Engine').mkdir(parents=True)
        self.root = self.home / 'custom-toolchain'
        self.prefix = self.home / "prefix with 'quotes'"
        (self.root / 'bin/x64').mkdir(parents=True)
        self.config = self.home / 'config with spaces'
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {'HOME': str(self.home), 'XDG_CONFIG_HOME': str(self.config)}).start()
        os.environ.pop('WINEPREFIX', None)
        os.environ.pop('BASH_ENV', None)
        patch.object(cli, 'ENGINE', self.engine).start()
        cli.configure(self.home, self.config / 'satisfactory-modding', self.root, self.prefix)
        self.marker = self.root / cli.MARKER
        self.marker.write_text(json.dumps({'source_pin': cli.PIN, 'selection': cli.SELECTION,
                                         'toolchain': str(self.root), 'wineprefix': str(self.prefix)}))
        self.block = self.root / 'bin/x64/msvcenv.sh'
        self.block.write_text('# upstream\n' + cli.managed_msvcenv_block(self.prefix))
        self.ini = self.home / '.config/Epic/UnrealEngine/Install.ini'
        self.ini.parent.mkdir(parents=True)
        self.ini.write_text(f'[Installations]\nother=/other\ncss={self.engine}/\n')

    def checks(self):
        return {c['id']: c for c in cli.doctor()['checks']}

    def test_all_ok_custom_paths_and_read_only(self):
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
        with patch.object(cli.subprocess, 'run', side_effect=AssertionError('no subprocess')):
            result = cli.doctor()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual([c['id'] for c in result['checks']],
                         ['engine', 'engine-group', 'registration', 'environment', 'toolchain', 'unrealrc', 'wineprefix-env'])
        self.assertTrue(all(c['status'] == 'ok' for c in result['checks']))
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_engine_missing(self):
        (self.engine / 'Engine').rmdir()
        self.assertEqual(self.checks()['engine']['status'], 'fail')

    def test_group_membership_and_stale_login(self):
        user = SimpleNamespace(pw_name='tester', pw_gid=12)
        cases = [([], 34, [12], 'Not in group'), (['tester'], 34, [12], 'log out and back in'),
                 ([], 12, [99], 'log out and back in'), (['tester'], 34, [12, 34], 'not group-writable')]
        for members, gid, groups, phrase in cases:
            with self.subTest(members=members, gid=gid, groups=groups), \
                    patch.object(cli.os, 'access', return_value=False), \
                    patch.object(cli.os, 'getgroups', return_value=groups), \
                    patch.object(cli.os, 'getgid', return_value=groups[0]), \
                    patch.object(cli.pwd, 'getpwuid', return_value=user), \
                    patch.object(cli.grp, 'getgrnam', return_value=SimpleNamespace(gr_mem=members, gr_gid=gid)):
                check = self.checks()['engine-group']
                self.assertEqual(check['status'], 'fail')
                self.assertIn(phrase, check['message'])
        with patch.object(cli.os, 'access', return_value=False), \
                patch.object(cli.grp, 'getgrnam', side_effect=KeyError):
            self.assertIn('Group unreal-engine-css is missing', self.checks()['engine-group']['message'])

    def test_missing_engine_is_not_reported_as_group_problem(self):
        (self.engine / 'Engine').rmdir()
        check = self.checks()['engine-group']
        self.assertEqual(check['status'], 'fail')
        self.assertIn('Cannot check write access', check['message'])

    def test_registration_missing_wrong_and_malformed(self):
        for text in [None, '', '[Installations]\ncss=/wrong\n', 'invalid ini']:
            with self.subTest(text=text):
                if text is None:
                    self.ini.unlink()
                else:
                    self.ini.write_text(text)
                self.assertEqual(self.checks()['registration']['status'], 'fail')

    def test_environment_missing_and_invalid_format(self):
        file = cli.environment_file()
        valid = file.read_text()
        for text in [None, valid + '\n', valid.replace('\n', '\r\n'), valid.replace('win64', 'win32'),
                     valid.replace('export UE_WINE_MSVC=', 'export OTHER='),
                     valid.replace(str(self.root), 'relative'), 'malformed\n',
                     valid.replace('export UE_WINE_MSVC=', 'export UE_WINE_MSVC="')]:
            with self.subTest(text=text):
                if text is None:
                    file.unlink()
                else:
                    file.write_text(text)
                checks = self.checks()
                self.assertEqual(checks['environment']['status'], 'fail')
                self.assertEqual(checks['toolchain']['status'], 'fail')

    def test_marker_missing_invalid_and_mismatched(self):
        valid = json.loads(self.marker.read_text())
        for record in [None, 'invalid', [], dict(valid, source_pin='wrong'),
                       dict(valid, wineprefix='/wrong'), dict(valid, toolchain='/wrong'),
                       dict(valid, selection={})]:
            with self.subTest(record=record):
                if record is None:
                    self.marker.unlink()
                else:
                    self.marker.write_text(record if isinstance(record, str) else json.dumps(record))
                self.assertEqual(self.checks()['toolchain']['status'], 'fail')

    def test_block_missing_wrong_prefix_duplicate_and_not_at_end(self):
        valid = self.block.read_text()
        for text in [None, '# upstream\n', cli.managed_msvcenv_block('/wrong'), valid + valid, valid + 'echo wrong\n']:
            with self.subTest(text=text):
                if text is None:
                    self.block.unlink()
                else:
                    self.block.write_text(text)
                self.assertEqual(self.checks()['toolchain']['status'], 'fail')

    def test_unrealrc_missing_wrong_and_commented(self):
        rc = self.home / '.unrealrc'
        valid = rc.read_text()
        for text in [None, '', '# ' + valid, valid.replace(str(self.config), '/wrong')]:
            with self.subTest(text=text):
                if text is None:
                    rc.unlink()
                else:
                    rc.write_text(text)
                self.assertEqual(self.checks()['unrealrc']['status'], 'fail')

    def test_warning_environment_and_matching_prefix(self):
        for env in [{'WINEPREFIX': '/wrong'}, {'BASH_ENV': '/startup'}, {'BASH_ENV': ''}]:
            with self.subTest(env=env), patch.dict(os.environ, env):
                result = cli.doctor()
                self.assertEqual(result['status'], 'ok')
                self.assertEqual(result['checks'][-1]['status'], 'warn')
                self.assertIn('outside satisfactory-modding run', result['checks'][-1]['message'])
        with patch.dict(os.environ, {'WINEPREFIX': str(self.prefix)}):
            self.assertEqual(self.checks()['wineprefix-env']['status'], 'ok')

    def test_main_json_shape_human_output_and_exit_status(self):
        for fail in [False, True]:
            if fail:
                self.marker.unlink()
            for json_mode in [False, True]:
                output = io.StringIO()
                with patch.object(cli.sys, 'argv', ['satisfactory-modding', 'doctor'] + (['--json'] if json_mode else [])), \
                        contextlib.redirect_stdout(output):
                    self.assertEqual(cli.main(), int(fail))
                if json_mode:
                    result = json.loads(output.getvalue())
                    self.assertEqual(set(result), {'status', 'checks'})
                    self.assertEqual(result['status'], 'fail' if fail else 'ok')
                    for check in result['checks']:
                        self.assertEqual(set(check), {'id', 'status', 'message'})
                        self.assertIn(check['status'], ['ok', 'warn', 'fail'])
                        self.assertNotIn('\n', check['message'])
                else:
                    self.assertEqual(len(output.getvalue().splitlines()), 7)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home))
        self.env.pop('BASH_ENV', None)
        self.file = self.home / 'satisfactory-modding/environment.sh'
        self.file.parent.mkdir()
        self.command = ['python3', str(RECIPE / 'satisfactory-modding')]

    def invoke(self, *args):
        return subprocess.run(self.command + list(args), env=self.env, capture_output=True, text=True)

    def test_help_bare_missing_command_and_missing_environment(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn('usage:', result.stdout)
        for args in [('--help',), ('setup', '--help'), ('doctor', '--help'), ('run', '--help')]:
            self.assertEqual(self.invoke(*args).returncode, 0)
        for args in [('run',), ('run', '--')]:
            result = self.invoke(*args)
            self.assertEqual(result.returncode, 2)
            self.assertIn('supply a command', result.stderr)
        for args in [('setup', '--unknown'), ('doctor', '--unknown'), ('unknown',)]:
            self.assertEqual(self.invoke(*args).returncode, 2)
        result = self.invoke('run', 'true')
        self.assertEqual(result.returncode, 1)
        self.assertIn('satisfactory-modding setup', result.stderr)

    def test_literal_help_command_and_command_help_argument(self):
        self.file.write_text('export TEST_SOURCED=yes\n')
        command = self.home / '--help'
        command.write_text('#!/bin/bash\nprintf "%s" "$TEST_SOURCED"\n')
        command.chmod(0o755)
        self.env['PATH'] = str(self.home) + ':' + self.env['PATH']
        result = self.invoke('run', '--', '--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'yes')
        result = self.invoke('run', 'python3', '-c', 'import sys; print(sys.argv[1:])', '--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--help', result.stdout)

    def test_bash_sourcing_failure_and_command_not_found(self):
        self.file.write_text('export TEST_VALUE="$(printf bash-sourced)"\n')
        result = self.invoke('run', 'bash', '-c', 'printf "%s" "$TEST_VALUE"')
        self.assertEqual(result.stdout, 'bash-sourced')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.invoke('run', 'nonexistent-satisfactory-test-command').returncode, 127)
        self.file.write_text('false\nexport SHOULD_NOT_RUN=yes\n')
        self.assertEqual(self.invoke('run', 'true').returncode, 1)

    def test_signal_is_preserved(self):
        self.file.write_text('export WINEARCH=win64\n')
        result = self.invoke('run', 'python3', '-c', 'import os,signal; os.kill(os.getpid(), signal.SIGTERM)')
        self.assertEqual(result.returncode, -signal.SIGTERM)
