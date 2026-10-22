"""Read-only doctor and process replacement checks in disposable homes."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_setup import cli, RECIPE

# Spelled out so a change to the CLI's own list cannot weaken these checks.
CREDENTIAL_NAMES = ('WWISE_EMAIL', 'WWISE_PASSWORD', 'WWISE_USER', 'WWISE_PASS')


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

    def test_run_does_not_pass_wwise_credentials(self):
        self.file.write_text('export TEST_SOURCED=yes\n')
        self.env.update(WWISE_EMAIL='private-email', WWISE_PASSWORD='private-password',
                        WWISE_USER='private-user', WWISE_PASS='private-pass')
        result = self.invoke('run', 'python3', '-c',
                             'import os,json; print(json.dumps(dict(os.environ)))')
        self.assertEqual(result.returncode, 0, result.stderr)
        env = json.loads(result.stdout)
        self.assertEqual(env['TEST_SOURCED'], 'yes')
        for name in CREDENTIAL_NAMES:
            self.assertNotIn(name, env)

    def test_signal_is_preserved(self):
        self.file.write_text('export WINEARCH=win64\n')
        result = self.invoke('run', 'python3', '-c', 'import os,signal; os.kill(os.getpid(), signal.SIGTERM)')
        self.assertEqual(result.returncode, -signal.SIGTERM)


class ModTests(unittest.TestCase):
    """Only fixture projects and a fake RunUAT process are used."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.project = self.home / "project with 'quotes'" / 'FactoryGame.uproject'
        self.project.parent.mkdir()
        self.project.write_text('{}')
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {'HOME': str(self.home), 'XDG_CONFIG_HOME': str(self.home / 'config'),
                                'PYTHONDONTWRITEBYTECODE': '1'}).start()
        patch.object(cli, 'STEAM_ROOTS', [self.home / 'steam', self.home / 'alternate']).start()
        self.engine = self.home / 'engine'
        patch.object(cli, 'ENGINE', self.engine).start()
        self.uat = self.engine / 'Engine/Build/BatchFiles/RunUAT.sh'
        self.uat.parent.mkdir(parents=True)
        self.uat.write_text("#!/usr/bin/env python3\n" +
            "import json,os,sys\nfrom pathlib import Path\n" +
            "Path('record.json').write_text(json.dumps({'argv':sys.argv[1:], 'env':dict(os.environ), " +
            "'cwd':os.getcwd(), 'stdin':sys.stdin.read()}))\n" +
            "print('fake UAT stdout'); print('fake UAT stderr',file=sys.stderr)\n" +
            "if os.environ.get('UAT_FAIL'): sys.exit(int(os.environ['UAT_FAIL']))\n" +
            "ref=next(a.split('=',1)[1] for a in sys.argv if a.startswith('-DLCName='))\n" +
            "if not os.environ.get('NO_OUTPUT'):\n" +
            " p=Path('Saved/ArchivedPlugins')/ref/(ref+'-Windows.zip'); " +
            "p.parent.mkdir(parents=True); p.write_bytes(b'zip')\n" +
            "copy=next((a.split('=',1)[1] for a in sys.argv if a.startswith('-CopyToGameDirectory_')),None)\n" +
            "if copy:\n" +
            " gf=(Path('Mods/GameFeatures')/ref).is_dir() or (Path('Plugins/GameFeatures')/ref).is_dir()\n" +
            " p=Path(copy)/'FactoryGame/Mods'; p=p/'GameFeatures' if gf else p; (p/ref).mkdir(parents=True)\n")
        self.uat.chmod(0o755)
        self.editor = self.engine / 'Engine/Build/BatchFiles/Linux/Build.sh'
        self.editor.parent.mkdir(parents=True)
        self.editor.write_text("#!/usr/bin/env python3\n" +
            "import json,os,sys\nfrom pathlib import Path\n" +
            "Path('editor.json').write_text(json.dumps({'argv':sys.argv[1:], 'env':dict(os.environ), " +
            "'uat_ran_before':Path('record.json').exists()}))\n" +
            "if os.environ.get('EDITOR_FAIL'): sys.exit(int(os.environ['EDITOR_FAIL']))\n")
        self.editor.chmod(0o755)
        targets = self.project.parent / 'Source'
        targets.mkdir()
        (targets / 'FactoryEditor.Target.cs').write_text('Type = TargetType.Editor;')
        (targets / 'FactoryGame.Target.cs').write_text('Type = TargetType.Game;')
        self.record = self.project.parent / 'record.json'
        self.game = self.home / 'game with spaces'
        self.game.mkdir()
        file = cli.environment_file()
        file.parent.mkdir(parents=True)
        file.write_text("export WINEPREFIX='/managed prefix'\nexport UE_WINE_MSVC='/managed tools'\n")
        self.plugin('Mods/Example/Example.uplugin', {})
        self.alpakit = self.plugin('Mods/Alpakit/Alpakit.uplugin', {}).parent
        self.plugin('Mods/SML/SML.uplugin', {'VersionName': '3.12.0'})
        version = self.project.parent / 'Source/FactoryGame/currentVersion.txt'
        version.parent.mkdir(parents=True, exist_ok=True)
        version.write_text(' 491125\n')
        for name in ('BlueprintBlank', 'CPPAndBlueprintBlank'):
            template = self.alpakit / 'Templates' / name
            (template / 'Config').mkdir(parents=True)
            (template / 'Config/PluginSettings.ini').write_text('name=PLUGIN_NAME\n')
        cpp = self.alpakit / 'Templates/CPPAndBlueprintBlank/Source/PLUGIN_NAME'
        (cpp / 'Public').mkdir(parents=True)
        (cpp / 'PLUGIN_NAME.Build.cs').write_text('class PLUGIN_NAME : ModuleRules {}')
        (cpp / 'Public/PLUGIN_NAME.h').write_text('class PLUGIN_NAME_API PLUGIN_NAME {};')
        icon = self.alpakit / 'Resources/DefaultIcon128.png'
        icon.parent.mkdir()
        icon.write_bytes(b'\0PLUGIN_NAME binary icon')

    def plugin(self, relative, data):
        path = self.project.parent / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return path

    def invoke(self, *args):
        # A separate Python process retains real stderr file descriptors for child logs.
        code = ("import importlib.machinery,sys; "
                "m=importlib.machinery.SourceFileLoader('cli',sys.argv[1]).load_module(); "
                "m.ENGINE=m.Path(sys.argv[2]); "
                "m.STEAM_ROOTS=[m.Path(sys.argv[3]),m.Path(sys.argv[4])]; "
                "sys.argv=['satisfactory-modding',*sys.argv[5:]]; sys.exit(m.main())")
        return subprocess.run(['python3', '-c', code, str(RECIPE / 'satisfactory-modding'),
                               str(self.engine), str(self.home / 'steam'), str(self.home / 'alternate'),
                               'mod', *args], cwd=self.project.parent, env=os.environ,
                              stdin=subprocess.DEVNULL, text=True, capture_output=True)

    def build(self, *extra):
        return self.invoke('build', 'Example', '--no-copy', '--json', *extra)

    def test_project_discovery_and_explicit_project(self):
        nested = self.project.parent / 'Source/nested'
        nested.mkdir()
        before = Path.cwd()
        try:
            os.chdir(nested)
            self.assertEqual(cli.project_file(), self.project)
            self.assertEqual(cli.project_file(self.project.parent), self.project)
            self.assertEqual(cli.project_file(self.project), self.project)
            os.chdir(self.home)
            with self.assertRaisesRegex(cli.SetupError, '--project'):
                cli.project_file()
        finally:
            os.chdir(before)
        result = self.build('--project', str(self.home / 'missing'))
        self.assertEqual(result.returncode, 1)
        self.assertIn('Missing project', result.stderr)
        self.assertFalse(self.record.exists())

    def test_mod_discovery_and_missing_and_ambiguous(self):
        for root in ('Mods/GameFeatures', 'Mods/nested', 'Plugins/nested'):
            with self.subTest(root=root):
                plugin = self.plugin(f'{root}/Nested/Nested.uplugin', {})
                self.assertEqual(cli.find_mod(self.project, 'Nested'), plugin)
                plugin.unlink()
        extra = self.project.parent / 'extra'
        self.project.write_text(json.dumps({'AdditionalPluginDirectories': ['extra']}))
        plugin = self.plugin('extra/Other/Other.uplugin', {})
        self.assertEqual(cli.find_mod(self.project, 'Other'), plugin)
        with self.assertRaisesRegex(cli.SetupError, 'looked recursively.*Mods.*Plugins.*extra'):
            cli.find_mod(self.project, 'Missing')
        self.plugin('Plugins/Example/Example.uplugin', {})
        result = self.build()
        self.assertEqual(result.returncode, 1)
        self.assertIn('Ambiguous mod', result.stderr)

    def test_build_argv_environment_stdin_logs_and_json(self):
        startup = self.home / 'startup.sh'
        startup.write_text('export WINEPREFIX=/wrong; export STARTUP_RAN=yes\n')
        with patch.dict(os.environ, {'BASH_ENV': str(startup), 'ENV': str(startup),
                                     'WWISE_EMAIL': 'private-email', 'WWISE_PASSWORD': 'private-password',
                                     'WWISE_USER': 'private-user', 'WWISE_PASS': 'private-pass'}):
            result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(set(summary), {'status', 'mod', 'project', 'outputs', 'game_mod'})
        self.assertEqual(summary['status'], 'complete')
        self.assertEqual(summary['mod'], 'Example')
        self.assertEqual(summary['project'], str(self.project))
        self.assertEqual(summary['outputs'], [str(self.project.parent / 'Saved/ArchivedPlugins/Example/Example-Windows.zip')])
        self.assertIsNone(summary['game_mod'])
        record = json.loads(self.record.read_text())
        self.assertEqual(record['argv'], [f'-ScriptsForProject={self.project}', 'PackagePlugin',
            f'-project={self.project}', '-clientconfig=Shipping', '-serverconfig=Shipping', '-utf8output',
            '-DLCName=Example', '-build', '-platform=Win64', '-nocompileeditor', '-installed'])
        self.assertEqual(record['cwd'], str(self.project.parent))
        self.assertEqual(record['stdin'], '')
        self.assertEqual(record['env']['WINEPREFIX'], '/managed prefix')
        self.assertEqual(record['env']['UE_WINE_MSVC'], '/managed tools')
        for key in ('BASH_ENV', 'ENV', 'STARTUP_RAN', *CREDENTIAL_NAMES):
            self.assertNotIn(key, record['env'])
        editor = json.loads((self.project.parent / 'editor.json').read_text())
        for key in CREDENTIAL_NAMES:
            self.assertNotIn(key, editor['env'])
        self.assertIn('fake UAT stdout', result.stderr)
        self.assertIn('fake UAT stderr', result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)

    def test_explicit_game_and_game_feature_copy(self):
        self.plugin('Mods/GameFeatures/Feature/Feature.uplugin', {})
        result = self.invoke('build', 'Feature', '--game', str(self.game), '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['game_mod'], str(self.game / 'FactoryGame/Mods/GameFeatures/Feature'))
        self.assertEqual(json.loads(self.record.read_text())['argv'][-1], f'-CopyToGameDirectory_Windows={self.game}')
        result = self.invoke('build', 'Example', '--game', str(self.game))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.game / 'FactoryGame/Mods/Example'), result.stdout)
        self.assertEqual(len(result.stdout.splitlines()), 1)

    def steam_fixture(self, root='steam', legacy=False):
        steam = self.home / root / 'steamapps'
        steam.mkdir(parents=True, exist_ok=True)
        missing = self.home / 'library without manifest'
        library = self.home / 'second library'
        (library / 'steamapps/common/Satisfactory').mkdir(parents=True, exist_ok=True)
        manifest = library / 'steamapps/appmanifest_526870.acf'
        manifest.write_text('"AppState" { "appid" "526870" "installdir" "Satisfactory" }')
        value = f'"{library}"' if legacy else f'{{ "path" "{library}" "apps" {{ "526870" "123" }} }}'
        (steam / 'libraryfolders.vdf').write_text('"libraryfolders" { // comment\n' +
            f'"0" {{ "path" "{missing}" }} "1" {value} }}')
        return library, manifest

    def test_steam_multiple_libraries_missing_manifest_and_auto_copy(self):
        library, manifest = self.steam_fixture()
        self.assertEqual(cli.steam_game(), library / 'steamapps/common/Satisfactory')
        result = self.invoke('build', 'Example', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['game_mod'], str(library / 'steamapps/common/Satisfactory/FactoryGame/Mods/Example'))
        manifest.unlink()
        self.assertIsNone(cli.steam_game())
        result = self.invoke('build', 'Example')
        self.assertEqual(result.returncode, 1)
        self.assertIn('--game DIR or --no-copy', result.stderr)

    def test_steam_alternate_root_legacy_and_malformed(self):
        library, manifest = self.steam_fixture('alternate', legacy=True)
        self.assertEqual(cli.steam_game(), library / 'steamapps/common/Satisfactory')
        for data in ('bad {', '"AppState" "bad"', '"AppState" { "appid" "526870" "installdir" "../escape" }'):
            manifest.write_text(data)
            self.assertIsNone(cli.steam_game())
        file = self.home / 'escaped.vdf'
        file.write_text(r'"key" "a\\b\"c//d"')
        self.assertEqual(cli.read_vdf(file), {'key': 'a\\b"c//d'})

    def test_no_copy_skips_detection_and_nonexistent_outputs_omitted(self):
        with patch.object(cli, 'steam_game', side_effect=AssertionError('must skip')):
            args = SimpleNamespace(project=self.project, ref='Example', no_copy=True, game=None)
            with patch.object(cli.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
                summary = cli.build_mod(args)
        self.assertEqual(summary['outputs'], [])
        self.assertIsNone(summary['game_mod'])
        with patch.dict(os.environ, {'NO_OUTPUT': '1'}):
            result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['outputs'], [])

    def test_uat_failure_missing_environment_and_wrapper(self):
        with patch.dict(os.environ, {'UAT_FAIL': '37'}):
            result = self.build()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('RunUAT failed (exit code 37)', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        cli.environment_file().unlink()
        result = self.build()
        self.assertEqual(result.returncode, 1)
        self.assertIn('satisfactory-modding setup', result.stderr)
        cli.environment_file().write_text('true\n')
        self.uat.unlink()
        result = self.build()
        self.assertEqual(result.returncode, 1)
        self.assertIn('Missing ' + str(self.uat), result.stderr)

    def test_editor_target_built_first_in_managed_environment(self):
        with patch.dict(os.environ, {'BASH_ENV': str(self.home / 'startup')}):
            result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        editor = json.loads((self.project.parent / 'editor.json').read_text())
        self.assertEqual(editor['argv'], ['FactoryEditor', 'Linux', 'Development',
                                          f'-Project={self.project}', '-WaitMutex'])
        self.assertEqual(editor['env']['WINEPREFIX'], '/managed prefix')
        self.assertNotIn('BASH_ENV', editor['env'])
        self.assertFalse(editor['uat_ran_before'])
        self.assertTrue(self.record.exists())
        self.record.unlink()
        with patch.dict(os.environ, {'EDITOR_FAIL': '5'}):
            result = self.build()
        self.assertEqual(result.returncode, 1)
        self.assertIn('Editor build failed (exit code 5)', result.stderr)
        self.assertFalse(self.record.exists())

    def test_editor_target_must_be_unique(self):
        (self.project.parent / 'Source/Other.Target.cs').write_text('Type = TargetType.Editor;')
        result = self.build()
        self.assertEqual(result.returncode, 1)
        self.assertIn('Expected one Editor target', result.stderr)

    def test_new_blueprint_and_cpp(self):
        for cpp in (False, True):
            ref = 'CppMod' if cpp else 'BlueprintMod'
            result = self.invoke('new', ref, '--json', *(['--cpp'] if cpp else []))
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(set(summary), {'status', 'mod', 'project', 'path', 'cpp'})
            self.assertEqual(summary['cpp'], cpp)
            created = Path(summary['path'])
            self.assertEqual(created, self.project.parent / 'Mods' / ref)
            self.assertTrue((created / 'Content').is_dir())
            self.assertEqual((created / 'Config/PluginSettings.ini').read_text(), f'name={ref}\n')
            self.assertEqual((created / 'Resources/Icon128.png').read_bytes(), b'\0PLUGIN_NAME binary icon')
            descriptor = json.loads((created / f'{ref}.uplugin').read_text())
            self.assertEqual(descriptor['FileVersion'], 3)
            self.assertEqual(descriptor['Version'], 1)
            for key in ('VersionName', 'SemVersion'):
                self.assertEqual(descriptor[key], '1.0.0')
            self.assertEqual(descriptor['FriendlyName'], ref)
            self.assertEqual(descriptor['Category'], 'Modding')
            self.assertEqual(descriptor['GameVersion'], '>=491125')
            self.assertTrue(descriptor['CanContainContent'])
            self.assertEqual(descriptor['Plugins'], [{'Name': 'SML', 'Enabled': True, 'SemVersion': '^3.12.0'}])
            self.assertNotIn('BuiltInInitialFeatureState', descriptor)
            self.assertEqual(descriptor['CreatedBy'], '')
            self.assertEqual(list(created.rglob('*.uasset')), [])
            if cpp:
                self.assertEqual(descriptor['Modules'], [{'Name': ref, 'Type': 'Runtime', 'LoadingPhase': 'Default'}])
                self.assertEqual((created / f'Source/{ref}/{ref}.Build.cs').read_text(), f'class {ref} : ModuleRules {{}}')
                self.assertEqual((created / f'Source/{ref}/Public/{ref}.h').read_text(), f'class {ref.upper()}_API {ref} {{}};')
                self.assertFalse(any('PLUGIN_NAME' in str(p) for p in created.rglob('*')))
            else:
                self.assertNotIn('Modules', descriptor)
            self.assertEqual(self.project.read_text(), '{}')
        result = self.invoke('new', 'HumanCpp', '--cpp')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('the editor or mod build compiles', result.stdout)

    def test_invalid_names_bad_arguments_and_game_feature(self):
        for ref in ('', '../escape', 'a b', 'a-b', 'a.b', 'a;', 'a/child'):
            with self.subTest(ref=ref):
                result = self.invoke('new', ref)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertNotIn('Traceback', result.stderr)
        for ref in ('Game', 'Engine', 'Script', 'Memory', 'Temp', 'Config'):
            self.assertEqual(self.invoke('new', ref).returncode, 2)
        result = self.invoke('new', 'Feature', '--game-feature')
        self.assertEqual(result.returncode, 2)
        self.assertIn('binary GameFeatureData asset', result.stderr)
        self.assertIn('binary GameFeatureData asset', self.invoke('new', '--help').stdout)
        self.assertEqual(self.invoke('build', 'Example', '--no-copy', '--game', str(self.game)).returncode, 2)
        self.assertEqual(self.invoke().returncode, 2)

    def test_overwrite_refused_anywhere_and_case_insensitive(self):
        directory = self.project.parent / 'Mods/Existing'
        directory.mkdir()
        sentinel = directory / 'keep'
        sentinel.write_text('untouched')
        result = self.invoke('new', 'Existing')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(sentinel.read_text(), 'untouched')
        self.plugin('unusual/location/Duplicate.uplugin', {})
        result = self.invoke('new', 'duplicate')
        self.assertEqual(result.returncode, 1)
        self.assertIn('already exists', result.stderr)
        self.assertFalse((self.project.parent / 'Mods/duplicate').exists())
        result = self.invoke('new', 'SML')
        self.assertEqual(result.returncode, 1)

    def test_atomic_creation_on_copy_and_rename_failure(self):
        args = SimpleNamespace(project=self.project, ref='Atomic', cpp=True)
        original = Path.write_bytes
        def fail_after_one(path, data):
            if path.suffix == '.h':
                raise OSError('copy failed')
            return original(path, data)
        for failure in (patch.object(Path, 'write_bytes', fail_after_one),
                        patch.object(Path, 'rename', side_effect=OSError('rename failed'))):
            with failure, self.assertRaises(OSError):
                cli.new_mod(args)
            self.assertFalse((self.project.parent / 'Mods/Atomic').exists())
            self.assertEqual(list((self.project.parent / 'Mods').glob('.Atomic-*')), [])

    def test_missing_template_and_metadata_fail_cleanly(self):
        import shutil
        shutil.rmtree(self.alpakit / 'Templates/BlueprintBlank')
        result = self.invoke('new', 'Missing')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Missing Alpakit template', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertFalse((self.project.parent / 'Mods/Missing').exists())

    def test_invalid_metadata_and_project_have_no_traceback(self):
        version = self.project.parent / 'Source/FactoryGame/currentVersion.txt'
        version.unlink()
        result = self.invoke('new', 'MissingVersion')
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('Traceback', result.stderr)
        self.assertFalse((self.project.parent / 'Mods/MissingVersion').exists())
        for data in ('{', '[]', '{"AdditionalPluginDirectories": "wrong"}'):
            self.project.write_text(data)
            result = self.build()
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertNotIn('Traceback', result.stderr)

    def test_build_existing_hyphen_name_and_patchable_wrapper(self):
        self.plugin('Mods/Existing-Mod/Existing-Mod.uplugin', {})
        result = self.invoke('build', 'Existing-Mod', '--no-copy', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['mod'], 'Existing-Mod')
        with patch.object(cli, 'RUN_UAT', self.home / 'custom.sh'):
            self.assertEqual(cli.uat_arguments(self.project, 'Example')[0], str(self.home / 'custom.sh'))

    def test_new_directory_mode_follows_umask(self):
        for mask in (0o022, 0o027):
            previous = os.umask(mask)
            try:
                result = self.invoke('new', f'Mode{mask}', '--json')
            finally:
                os.umask(previous)
            self.assertEqual(result.returncode, 0, result.stderr)
            created = Path(json.loads(result.stdout)['path'])
            self.assertEqual(created.stat().st_mode & 0o777, 0o777 & ~mask)

    def test_cpp_identifier_and_project_module_collision(self):
        for ref in ('9Invalid', 'FactoryGame', 'factorygame'):
            result = self.invoke('new', ref, '--cpp')
            self.assertEqual(result.returncode, 2 if ref == '9Invalid' else 1)
            self.assertIn('C++ identifier' if ref == '9Invalid' else 'already exists in Source', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse((self.project.parent / 'Mods' / ref).exists())
        module = self.project.parent / 'Source/Nested/ActualModule.Build.cs'
        module.parent.mkdir()
        module.write_text('class ActualModule : ModuleRules {}')
        result = self.invoke('new', 'ActualModule', '--cpp')
        self.assertEqual(result.returncode, 1)
        self.assertIn('already exists in Source', result.stderr)
        for ref in ('9Blueprint', 'FactoryGame'):
            result = self.invoke('new', ref)
            self.assertEqual(result.returncode, 0, result.stderr)


OLD_SDK, OLD_INTEGRATION, OLD_PLUGIN = '2023.1.14.8770', '2023.1.14.3555', '2023.1.14.8770.3555'
NEW_SDK, NEW_INTEGRATION, NEW_PLUGIN = '2025.1.6.9117', '2025.1.6.4248', '2025.1.6.9117.4248'


def build_yml(sdk, integration):
    # Shaped like upstream's workflow, including an unrelated --sdk-version.
    return ('      - name: Install MSVC\n        run: ./vsdownload.py --sdk-version 10.0.22621\n'
            '      - name: Download Wwise\n        run: |\n'
            f'          ./wwise-cli download --sdk-version "{sdk}" --filter Packages=SDK >/dev/null\n'
            f'          ./wwise-cli integrate-ue --integration-version "{integration}" --project "/tmp/work/SML/FactoryGame.uproject" >/dev/null\n')


FAKE_TOOL = r"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
home=Path(os.environ['FIXTURE_HOME'])
name=Path(sys.argv[0]).name
args=sys.argv[1:]
if name in ('wwise-cli','wine'): print('child progress')
with (home/'calls.jsonl').open('a') as f:
 f.write(json.dumps({'name':name,'argv':args,'env':dict(os.environ),'stdin':os.read(0,1).decode()})+'\n')
def touch(p, text='{}'):
 p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text)
if name=='git':
 # Real git against a local origin; a clone of the upstream URL clones that origin.
 if args[0]=='clone': args=['clone',os.environ['FAKE_ORIGIN'],args[-1]]
 os.execv(os.environ['REAL_GIT'],['git',*args])
elif name=='wwise-cli':
 if os.environ.get('FAKE_WWISE_FAIL') in ('1', args[0]): sys.exit(3)
 if args[0]=='download':
  p=Path(os.environ['XDG_CACHE_HOME'])/'wwise-cli/wwise'/args[args.index('--sdk-version')+1]
  for platform in ('x64_vc160','x64_vc170','Linux_x64'): (p/'SDK'/platform).mkdir(parents=True,exist_ok=True)
  touch(p/'Authoring/x64/Release/bin/WwiseConsole.exe'); touch(p/'info.json')
 else:
  integration=args[args.index('--integration-version')+1]
  sdk={'2023.1.14.3555':'2023.1.14.8770','2025.1.6.4248':'2025.1.6.9117'}[integration]
  (Path(os.environ['XDG_CACHE_HOME'])/'wwise-cli/unrealintegration'/integration).mkdir(parents=True,exist_ok=True)
  p=Path(args[-1]).parent
  touch(p/'Plugins/Wwise/Wwise.uplugin', json.dumps({'VersionName':sdk+'.'+integration.split('.')[-1]}))
  (p/'Plugins/WwiseNiagara').mkdir(parents=True,exist_ok=True)
  # Like the real integrations, 2025 puts the SDK libraries in WwiseSoundEngine.
  plugin='WwiseSoundEngine' if integration.startswith('2025.') else 'Wwise'
  for platform in ('x64_vc160','x64_vc170','Linux_x64'): touch(p/'Plugins'/plugin/'ThirdParty'/platform/'library.a')
elif name=='winepath': print(args[-1])
elif name=='wine':
 # WwiseConsole lives in .../wwise-cli/wwise/VERSION/Authoring/x64/Release/bin.
 version=Path(args[0]).parents[4].name
 p=Path(args[-1])
 project='<WwiseDocument Type="Project" WwiseVersion="v%s" WwiseBuild="%s"/>' % tuple(version.rsplit('.',1))
 if args[1]=='create-new-project': touch(p, project)
 elif args[1]=='migrate':
  assert p.is_file()
  if not os.environ.get('FAKE_MIGRATE_NOOP'): touch(p, project)
 else:
  banks=p.parent/'GeneratedSoundBanks'
  touch(banks/'ProjectInfo.xml', '<ProjectInfo><Project Generator="%s"/></ProjectInfo>' % version)
  if not os.environ.get('FAKE_BANKS_MISSING'): touch(banks/'Windows/Init.bnk')
"""


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(patch.stopall)
        self.home = Path(self.temp.name)
        self.project = self.home / "project with 'quotes'"
        self.ini = (b'\xef\xbb\xbf[Other]\r\nAudioRouting=Custom\r\n'
                    b'[/Script/AkAudio.AkSettings]\r\n'
                    b'WwiseProjectPath=(FilePath="SatisfactoryModLoader_WwiseProject/SatisfactoryModLoader_WwiseProject.wproj")\r\n'
                    b'RootOutputPath=(Path="../SatisfactoryModLoader_WwiseProject/GeneratedSoundBanks")\r\n'
                    b'AudioRouting=Custom\r\n[After]\r\nAudioRouting=Custom\r\n')
        self.origin = self.home / 'origin.git'
        patch.dict(os.environ, {'HOME': str(self.home), 'XDG_CACHE_HOME': str(self.home / 'cache'),
            'XDG_CONFIG_HOME': str(self.home / 'config'), 'WWISE_EMAIL': 'secret@example.com',
            'WWISE_PASSWORD': 'secret-password', 'WWISE_USER': '', 'WWISE_PASS': '',
            'BASH_ENV': '/must-not-be-sourced',
            'ENV': '/must-not-be-sourced', 'FIXTURE_HOME': str(self.home),
            'FAKE_ORIGIN': str(self.origin), 'REAL_GIT': shutil.which('git'),
            'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.com',
            'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.com'}).start()
        self.record = self.home / 'calls.jsonl'
        self.seed = self.home / 'seed'
        self.git_setup('init', '--quiet', '--bare', '--initial-branch=master', str(self.origin), cwd=self.home)
        self.git_setup('init', '--quiet', '--initial-branch=master', str(self.seed), cwd=self.home)
        self.git_setup('remote', 'add', 'origin', str(self.origin))
        self.commit({'FactoryGame.uproject': b'{"EngineAssociation": "5.6.1-CSS"}',
                     'Config/DefaultGame.ini': self.ini,
                     '.github/workflows/build.yml': build_yml(OLD_SDK, OLD_INTEGRATION).encode(),
                     '.gitignore': b'Plugins/Wwise*/*\n*_WwiseProject/*\n'}, 'Initial')
        for name, constant in [('git', 'GIT'), ('wine', 'WINE'), ('winepath', 'WINEPATH')]:
            path = self.home / name
            path.write_text(FAKE_TOOL); path.chmod(0o755)
            patch.object(cli, constant, str(path)).start()
        self.binary = FAKE_TOOL.encode()
        import hashlib
        patch.object(cli, 'WWISE_CLI_SIZE', len(self.binary)).start()
        patch.object(cli, 'WWISE_CLI_SHA256', hashlib.sha256(self.binary).hexdigest()).start()
        self.http = patch.object(cli.urllib.request, 'urlopen', side_effect=lambda *a, **kw: io.BytesIO(self.binary)).start()
        file = cli.environment_file()
        file.parent.mkdir(parents=True)
        file.write_text("export WINEPREFIX='/managed prefix'\nexport WINEDEBUG=wrong\n")

    def git_setup(self, *args, cwd=None):
        subprocess.run([shutil.which('git'), *args], cwd=cwd or self.seed, check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

    def commit(self, files, message):
        for name, content in files.items():
            (self.seed / name).parent.mkdir(parents=True, exist_ok=True)
            (self.seed / name).write_bytes(content)
        self.git_setup('add', '--all')
        self.git_setup('commit', '--quiet', '-m', message)
        self.git_setup('push', '--quiet', 'origin', 'HEAD:master')

    def invoke(self, *extra, json_output=True, interactive=False, command='init'):
        output = io.StringIO()
        with tempfile.TemporaryFile(mode='w+') as errors:
            argv = ['satisfactory-modding', 'project', command, str(self.project), *extra]
            if json_output: argv.append('--json')
            with patch.object(cli.sys, 'argv', argv), patch.object(cli.sys.stdin, 'isatty', return_value=interactive), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                code = cli.main()
            errors.seek(0)
            return code, output.getvalue(), errors.read()

    def calls(self):
        return [json.loads(line) for line in self.record.read_text().splitlines()] if self.record.exists() else []


class ProjectInitTests(ProjectFixture):
    def test_wwise_versions_from_build_yml(self):
        self.assertEqual(cli.wwise_versions(build_yml(NEW_SDK, NEW_INTEGRATION), 'build.yml'),
                         (NEW_SDK, NEW_INTEGRATION, NEW_PLUGIN))
        for text, message in [('', 'Expected one'),
                              (build_yml(NEW_SDK, NEW_INTEGRATION) * 2, 'Expected one'),
                              (build_yml(NEW_SDK, NEW_INTEGRATION).replace('wwise-cli download', 'wwise-cli fetch'), 'Expected one'),
                              (build_yml(NEW_SDK, '2025.1.6'), 'Expected one'),
                              (build_yml(NEW_SDK, OLD_INTEGRATION), 'do not match')]:
            with self.subTest(text=text), self.assertRaisesRegex(cli.SetupError, message + '.*build.yml'):
                cli.wwise_versions(text, 'build.yml')

    def test_init_takes_wwise_versions_from_the_clone(self):
        self.commit({'.github/workflows/build.yml': build_yml(NEW_SDK, NEW_INTEGRATION).encode()}, 'New Wwise')
        code, output, error = self.invoke()
        self.assertEqual(code, 0, error)
        argv = [c['argv'] for c in self.calls() if c['name'] == 'wwise-cli']
        self.assertEqual(argv[0][:3], ['download', '--sdk-version', NEW_SDK])
        self.assertEqual(argv[1][:3], ['integrate-ue', '--integration-version', NEW_INTEGRATION])
        self.assertTrue(cli.integration_ready(self.project, NEW_PLUGIN))
        self.assertEqual(cli.soundbanks_version(self.project / cli.WWISE_PROJECT_NAME / 'GeneratedSoundBanks'), NEW_SDK)
        (self.project / '.github/workflows/build.yml').unlink()
        code, output, error = self.invoke()
        self.assertEqual(code, 1); self.assertIn('Missing', error); self.assertIn('build.yml', error)

    def test_fresh_and_rerun_all_skipped(self):
        code, output, error = self.invoke()
        self.assertEqual(code, 0, error)
        result = json.loads(output)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual([s['status'] for s in result['steps']], ['done'] * 7)
        calls = self.calls()
        self.assertEqual([c['name'] for c in calls], ['git', 'wwise-cli', 'wwise-cli', 'winepath', 'wine', 'wine'])
        self.assertEqual(calls[0]['argv'], ['clone', 'https://github.com/satisfactorymodding/SatisfactoryModLoader.git', str(self.project)])
        self.assertEqual(calls[1]['argv'], ['download', '--sdk-version', OLD_SDK,
            '--filter', 'Packages=SDK', '--filter', 'DeploymentPlatforms=Windows_vc160',
            '--filter', 'DeploymentPlatforms=Windows_vc170', '--filter', 'DeploymentPlatforms=Linux',
            '--filter', 'DeploymentPlatforms=', '--filter', 'Packages=Authoring',
            '--filter', 'Packages=Authoring_Windows_x64_Release'])
        self.assertEqual(calls[2]['argv'], ['integrate-ue', '--integration-version', OLD_INTEGRATION,
                                         '--project', str(self.project / 'FactoryGame.uproject')])
        for call in calls:
            self.assertEqual(call['stdin'], '')
            self.assertNotIn('secret', json.dumps(call['argv']))
        for call in calls:
            if call['name'] == 'wwise-cli':
                self.assertEqual(call['env']['WWISE_EMAIL'], os.environ['WWISE_EMAIL'])
                self.assertEqual(call['env']['WWISE_PASSWORD'], os.environ['WWISE_PASSWORD'])
                self.assertNotIn('WWISE_USER', call['env']); self.assertNotIn('WWISE_PASS', call['env'])
            else:
                for key in CREDENTIAL_NAMES:
                    self.assertNotIn(key, call['env'])
        for call in calls[3:]:
            self.assertEqual(call['env']['WINEPREFIX'], '/managed prefix')
            self.assertEqual(call['env']['WINEDEBUG'], '-all')
            self.assertEqual(call['env']['WINEDLLOVERRIDES'], 'mscoree,mshtml=')
            self.assertNotIn('BASH_ENV', call['env']); self.assertNotIn('ENV', call['env'])
        self.assertNotIn('secret', output + error)
        self.assertIn('child progress', error)
        self.assertNotIn('child progress', output)
        changed = self.ini.replace(b'AudioRouting=Custom\r\n[After]', b'AudioRouting=Separate\r\n[After]')
        self.assertEqual((self.project / 'Config/DefaultGame.ini').read_bytes(), changed)
        code, output, error = self.invoke(json_output=False)
        self.assertEqual(code, 0, error)
        self.assertEqual(output.count(': skipped'), 7)
        self.assertIn('Unreal Project Model Mods Fix', output)
        self.assertIn('satisfactory-modding run rider', output)
        self.assertEqual(self.calls(), calls)
        self.assertEqual(self.http.call_count, 1)
        with patch.dict(os.environ, {'WWISE_EMAIL': '', 'WWISE_PASSWORD': ''}):
            code, output, error = self.invoke()
        self.assertEqual(code, 0, error)
        self.assertEqual([s['status'] for s in json.loads(output)['steps']], ['skipped'] * 7)

    def test_partial_resume_and_explicit_cli(self):
        self.assertEqual(self.invoke()[0], 0)
        (self.project / 'Plugins/Wwise/Wwise.uplugin').write_text('{"VersionName":"old"}')
        banks = self.project / cli.WWISE_PROJECT_NAME / 'GeneratedSoundBanks'
        (banks / 'Windows/Init.bnk').unlink()
        path = self.home / 'wwise-cli'; path.write_bytes(self.binary); path.chmod(0o755)
        code, output, error = self.invoke('--wwise-cli', str(path))
        self.assertEqual(code, 0, error)
        self.assertEqual([s['status'] for s in json.loads(output)['steps']],
                         ['skipped', 'skipped', 'skipped', 'done', 'skipped', 'done', 'skipped'])
        # The stale plugin and soundbanks are checked against git before they are replaced.
        self.assertEqual([c['name'] for c in self.calls()[6:]], ['git', 'git', 'wwise-cli', 'winepath', 'git', 'wine'])
        self.assertEqual([c['argv'][-1] for c in self.calls()[6:8]], ['Plugins/Wwise', 'Plugins/WwiseNiagara'])
        self.assertEqual(self.calls()[10]['argv'][-1], f'{cli.WWISE_PROJECT_NAME}/GeneratedSoundBanks')
        self.assertEqual(self.http.call_count, 1)

    def test_tracked_soundbanks_are_not_removed(self):
        self.assertEqual(self.invoke()[0], 0)
        banks = self.project / cli.WWISE_PROJECT_NAME / 'GeneratedSoundBanks'
        (banks / 'Windows/Init.bnk').unlink()
        subprocess.run([shutil.which('git'), '-C', str(self.project), 'add', '--force', str(banks)], check=True)
        code, output, error = self.invoke()
        self.assertEqual(code, 1); self.assertIn('git tracks files in it', error)
        self.assertTrue((banks / 'ProjectInfo.xml').is_file())

    def test_checksum_failure_cleans_temporary_download(self):
        with patch.object(cli, 'WWISE_CLI_SHA256', '0' * 64):
            code, output, error = self.invoke()
        self.assertEqual(code, 1); self.assertEqual(output, '')
        self.assertIn('SHA-256 mismatch', error)
        self.assertEqual(list((cli.cache_home() / 'satisfactory-modding/wwise-cli/v0.2.4').iterdir()), [])
        self.assertEqual([c['name'] for c in self.calls()], ['git'])

    def test_network_error_is_clean(self):
        import urllib.error
        self.http.side_effect = urllib.error.URLError('offline')
        code, output, error = self.invoke()
        self.assertEqual(code, 1); self.assertIn('Cannot download wwise-cli', error)
        self.assertNotIn('Traceback', error)

    def test_user_and_pass_authenticate_wwise_cli_only(self):
        alias = {'WWISE_USER': 'alias-user@example.com', 'WWISE_PASS': 'alias-pass'}
        # An unset, empty, or incomplete first pair does not hide a complete second pair.
        for first in ({'WWISE_EMAIL': None, 'WWISE_PASSWORD': None},
                      {'WWISE_EMAIL': '', 'WWISE_PASSWORD': ''},
                      {'WWISE_EMAIL': 'secret@example.com', 'WWISE_PASSWORD': ''},
                      {'WWISE_EMAIL': '', 'WWISE_PASSWORD': 'secret-password'}):
            with self.subTest(first=first):
                self.record.unlink(missing_ok=True)
                shutil.rmtree(self.project, ignore_errors=True)
                shutil.rmtree(cli.cache_home() / 'wwise-cli', ignore_errors=True)
                with patch.dict(os.environ, {**{k: v for k, v in first.items() if v is not None}, **alias}):
                    for name in [k for k, v in first.items() if v is None]:
                        del os.environ[name]
                    code, output, error = self.invoke()
                self.assertEqual(code, 0, error)
                calls = self.calls()
                self.assertEqual([c['name'] for c in calls].count('wwise-cli'), 2)
                for call in calls:
                    present = sorted(k for k in CREDENTIAL_NAMES if k in call['env'])
                    if call['name'] == 'wwise-cli':
                        self.assertEqual(call['stdin'], '')
                        self.assertEqual(call['env']['WWISE_EMAIL'], 'alias-user@example.com')
                        self.assertEqual(call['env']['WWISE_PASSWORD'], 'alias-pass')
                        self.assertEqual(present, ['WWISE_EMAIL', 'WWISE_PASSWORD'])
                    else:
                        self.assertEqual(present, [])
                    self.assertNotIn('alias', json.dumps(call['argv']))
                self.assertNotIn('alias-', output + error)

    def test_complete_first_pair_wins_over_alias_pair(self):
        with patch.dict(os.environ, {'WWISE_USER': 'alias-user@example.com', 'WWISE_PASS': 'alias-pass'}):
            code, output, error = self.invoke()
        self.assertEqual(code, 0, error)
        for call in self.calls():
            if call['name'] == 'wwise-cli':
                self.assertEqual(call['env']['WWISE_EMAIL'], 'secret@example.com')
                self.assertEqual(call['env']['WWISE_PASSWORD'], 'secret-password')

    def test_incomplete_pairs_are_not_mixed(self):
        for env in ({'WWISE_EMAIL': 'secret@example.com', 'WWISE_PASSWORD': '',
                     'WWISE_USER': 'alias-user@example.com', 'WWISE_PASS': ''},
                    {'WWISE_EMAIL': '', 'WWISE_PASSWORD': 'secret-password',
                     'WWISE_USER': '', 'WWISE_PASS': 'alias-pass'},
                    # One variable from each pair is still not a pair.
                    {'WWISE_EMAIL': '', 'WWISE_PASSWORD': 'secret-password',
                     'WWISE_USER': 'alias-user@example.com', 'WWISE_PASS': ''},
                    {'WWISE_EMAIL': 'secret@example.com', 'WWISE_PASSWORD': '',
                     'WWISE_USER': '', 'WWISE_PASS': 'alias-pass'}):
            with self.subTest(env=env), patch.dict(os.environ, env):
                code, output, error = self.invoke()
                self.assertEqual(code, 1); self.assertEqual(output, '')
                self.assertIn('WWISE_USER and WWISE_PASS', error)
                self.assertNotIn('secret', error); self.assertNotIn('alias-', error)
        self.assertEqual([c['name'] for c in self.calls()], ['git'])

    def test_noninteractive_wwise_cli_gets_devnull_stdin(self):
        original = cli.subprocess.run
        seen = []
        def execute(argv, **kwargs):
            if Path(argv[0]).name == 'wwise-cli':
                seen.append(kwargs.copy())
            return original(argv, **kwargs)
        with patch.object(cli.subprocess, 'run', side_effect=execute):
            code, output, error = self.invoke()
        self.assertEqual(code, 0, error)
        self.assertEqual(len(seen), 2)
        for kwargs in seen:
            self.assertIs(kwargs['stdin'], subprocess.DEVNULL)
            # stdout carries signed download URLs.
            self.assertIs(kwargs['stdout'], subprocess.DEVNULL)

    def test_missing_credentials_non_tty(self):
        for variable in ('WWISE_EMAIL', 'WWISE_PASSWORD'):
            with patch.dict(os.environ, {variable: ''}):
                code, output, error = self.invoke()
            self.assertEqual(code, 1); self.assertEqual(output, '')
            self.assertIn('WWISE_EMAIL and WWISE_PASSWORD', error)
            self.assertNotIn('Traceback', error)
        self.assertEqual([c['name'] for c in self.calls()], ['git'])

    def test_closed_stdin_is_not_a_terminal(self):
        # A parent that closes stdin leaves sys.stdin as None.
        output = io.StringIO()
        with tempfile.TemporaryFile(mode='w+') as errors:
            argv = ['satisfactory-modding', 'project', 'init', str(self.project), '--json']
            with patch.dict(os.environ, {'WWISE_EMAIL': '', 'WWISE_PASSWORD': ''}), \
                    patch.object(cli.sys, 'argv', argv), patch.object(cli.sys, 'stdin', None), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                code = cli.main()
            errors.seek(0)
            error = errors.read()
        self.assertEqual(code, 1); self.assertEqual(output.getvalue(), '')
        self.assertIn('WWISE_USER and WWISE_PASS', error)
        self.assertNotIn('Traceback', error)
        self.assertEqual([c['name'] for c in self.calls()], ['git'])

    def test_wrong_root_path_and_missing_section_key(self):
        self.assertEqual(self.invoke()[0], 0)
        path = self.project / 'Config/DefaultGame.ini'
        for content, message in [(self.ini.replace(b'../SatisfactoryModLoader_WwiseProject/GeneratedSoundBanks', b'wrong'), 'RootOutputPath'),
                                 (self.ini.replace(b'[/Script/AkAudio.AkSettings]', b'[Wrong]'), 'Missing AkSettings'),
                                 (self.ini.replace(b'AudioRouting=Custom', b'Other=Custom'), 'AudioRouting'),
                                 (self.ini.replace(b'FilePath="SatisfactoryModLoader', b'FilePath="Wrong'), 'WwiseProjectPath')]:
            path.write_bytes(content)
            code, output, error = self.invoke()
            self.assertEqual(code, 1); self.assertIn(message, error)
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(len(self.calls()), 6)

    def test_existing_non_project_rejected(self):
        self.project.mkdir()
        code, output, error = self.invoke()
        self.assertEqual(code, 1); self.assertIn('not a Starter Project', error)
        self.assertEqual(self.calls(), []); self.http.assert_not_called()

    def test_missing_generated_file_fails_and_child_failure_is_clean(self):
        with patch.dict(os.environ, {'FAKE_WWISE_FAIL': '1'}):
            code, output, error = self.invoke()
        self.assertEqual(code, 1); self.assertIn('wwise-cli download failed', error)
        self.assertNotIn('secret', error)
        with patch.dict(os.environ, {'FAKE_BANKS_MISSING': '1'}):
            code, output, error = self.invoke()
        self.assertEqual(code, 1); self.assertIn('Windows/Init.bnk and ProjectInfo.xml', error)

    def test_tty_authentication_children_inherit_streams(self):
        # Inspect the subprocess contract without using a real terminal or credentials.
        self.assertEqual(self.invoke()[0], 0)
        (cli.wwise_sdk(OLD_SDK) / 'info.json').unlink()
        (self.project / 'Plugins/Wwise/Wwise.uplugin').unlink()
        original = cli.subprocess.run
        seen = []
        def execute(argv, **kwargs):
            if Path(argv[0]).name == 'wwise-cli':
                seen.append(kwargs.copy())
                kwargs['stdin'] = subprocess.DEVNULL
            return original(argv, **kwargs)
        with patch.dict(os.environ, {'WWISE_PASSWORD': ''}), patch.object(cli.subprocess, 'run', side_effect=execute):
            code, output, error = self.invoke(interactive=True)
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)['status'], 'complete')
        self.assertNotIn('child progress', output)
        self.assertIn('child progress', error)
        self.assertEqual(len(seen), 2)
        for kwargs in seen:
            self.assertIsNone(kwargs['stdin'])
            self.assertIs(kwargs['stdout'], kwargs['stderr'])
            # The prompt asks only for what is missing: the set half goes through, nothing else does.
            self.assertEqual(kwargs['env']['WWISE_EMAIL'], 'secret@example.com')
            self.assertFalse(kwargs['env'].get('WWISE_PASSWORD'))
            self.assertNotIn('WWISE_USER', kwargs['env']); self.assertNotIn('WWISE_PASS', kwargs['env'])

    def test_pins_match_manifest_and_bad_args(self):
        manifest = json.loads((RECIPE.parent.parent / 'upstream-inputs.json').read_text())['wwise']
        # These constants are patched for fixture downloads; compare a fresh module.
        import runpy
        constants = runpy.run_path(str(RECIPE / 'satisfactory-modding'))
        # The Wwise SDK and integration versions come from each Starter Project's build.yml.
        self.assertEqual(set(manifest), {'repository', 'version', 'url', 'asset', 'bytes', 'sha256'})
        for key, constant in [('version', 'WWISE_CLI_VERSION'), ('url', 'WWISE_CLI_URL'),
                              ('bytes', 'WWISE_CLI_SIZE'), ('sha256', 'WWISE_CLI_SHA256')]:
            self.assertEqual(manifest[key], constants[constant])
        with patch.object(cli.sys, 'argv', ['satisfactory-modding', 'project', 'init']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                cli.main()
        self.assertEqual(raised.exception.code, 2)

    def test_bom_on_aksettings_header(self):
        self.project.mkdir()
        (self.project / 'Config').mkdir()
        path = self.project / 'Config/DefaultGame.ini'
        content = self.ini.replace(b'[Other]\r\nAudioRouting=Custom\r\n', b'')
        path.write_bytes(content)
        self.assertEqual(cli.audio_routing(self.project, write=True)[0], 'done')
        self.assertEqual(path.read_bytes(), content.replace(b'AudioRouting=Custom\r\n[After]', b'AudioRouting=Separate\r\n[After]'))

    def test_atomic_audio_routing_preserves_mode_and_cleans_failed_writes(self):
        self.project.mkdir()
        (self.project / 'Config').mkdir()
        path = self.project / 'Config/DefaultGame.ini'
        path.write_bytes(self.ini)
        path.chmod(0o640)
        for operation in ('fchmod', 'replace'):
            with patch.object(cli.os, operation, side_effect=OSError('injected write failure')):
                with self.assertRaisesRegex(OSError, 'injected write failure'):
                    cli.audio_routing(self.project, write=True)
            self.assertEqual(path.read_bytes(), self.ini)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(list(path.parent.iterdir()), [path])
        original_inode = path.stat().st_ino
        cli.audio_routing(self.project, write=True)
        self.assertNotEqual(path.stat().st_ino, original_inode)
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(path.read_bytes(), self.ini.replace(b'AudioRouting=Custom\r\n[After]', b'AudioRouting=Separate\r\n[After]'))
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_missing_sdk_platform_and_empty_integration_platform_resume(self):
        import shutil
        self.assertEqual(self.invoke()[0], 0)
        for platform in cli.WWISE_PLATFORMS:
            shutil.rmtree(cli.wwise_sdk(OLD_SDK) / 'SDK' / platform)
            self.assertFalse(cli.sdk_ready(OLD_SDK))
            code, output, error = self.invoke()
            self.assertEqual(code, 0, error)
            statuses = {step['id']: step['status'] for step in json.loads(output)['steps']}
            self.assertEqual(statuses['wwise-download'], 'done')
            self.assertEqual(statuses['wwise-integrate'], 'skipped')
            self.assertTrue(cli.sdk_ready(OLD_SDK))
            folder = self.project / 'Plugins/Wwise/ThirdParty' / platform
            for file in folder.iterdir(): file.unlink()
            self.assertFalse(cli.integration_ready(self.project, OLD_PLUGIN))
            code, output, error = self.invoke()
            self.assertEqual(code, 0, error)
            statuses = {step['id']: step['status'] for step in json.loads(output)['steps']}
            self.assertEqual(statuses['wwise-download'], 'skipped')
            self.assertEqual(statuses['wwise-integrate'], 'done')
            self.assertTrue(cli.integration_ready(self.project, OLD_PLUGIN))
            shutil.rmtree(folder)
            self.assertFalse(cli.integration_ready(self.project, OLD_PLUGIN))
            self.assertEqual(self.invoke()[0], 0)


class ProjectUpdateTests(ProjectFixture):
    def setUp(self):
        super().setUp()
        install = self.home / '.config/Epic/UnrealEngine/Install.ini'
        install.parent.mkdir(parents=True)
        install.write_text(f'[Installations]\nUE_5.6.1-CSS={cli.ENGINE}\n')
        code, output, error = self.invoke()
        self.assertEqual(code, 0, error)
        self.record.unlink()
        self.old_head = self.head()
        # Upstream drops the BOM and adds a section, as SML did with the Wwise 2025 update.
        self.new_ini = self.ini.removeprefix(b'\xef\xbb\xbf') + b'[/Script/WwisePackaging.WwisePackagingSettings]\r\nbPackageAsBulkData=True\r\n'

    def update(self, *extra, json_output=True):
        return self.invoke(*extra, json_output=json_output, command='update')

    def head(self):
        return subprocess.run([shutil.which('git'), '-C', str(self.project), 'rev-parse', 'HEAD'], check=True,
                              stdout=subprocess.PIPE, text=True).stdout.strip()

    def upstream_wwise_update(self):
        self.commit({'Config/DefaultGame.ini': self.new_ini,
                     '.github/workflows/build.yml': build_yml(NEW_SDK, NEW_INTEGRATION).encode(),
                     'Source/FGGameState.h': b'class AFGGameState;\n'}, 'Update headers and Wwise')

    def separate(self, data):
        return data.replace(b'AudioRouting=Custom\r\n[After]', b'AudioRouting=Separate\r\n[After]')

    def test_update_fast_forwards_and_replaces_wwise_then_skips(self):
        self.upstream_wwise_update()
        stale = self.project / 'Plugins/Wwise/Source/Removed.h'
        stale.parent.mkdir(parents=True); stale.write_text('old')
        # Old banks the new generator does not write again, like the Oct 9 leftovers.
        old_banks = self.project / cli.WWISE_PROJECT_NAME / 'GeneratedSoundBanks/Windows'
        (old_banks / 'English(US)').mkdir(parents=True)
        (old_banks / 'PluginInfo.xml').write_text('old')
        code, output, error = self.update()
        self.assertEqual(code, 0, error)
        result = json.loads(output)
        steps = {s['id']: s for s in result['steps']}
        self.assertEqual([s['id'] for s in result['steps']], ['checkout', 'wwise-cli', 'wwise-download', 'wwise-integrate',
                                                             'wwise-project', 'soundbanks', 'audio-routing'])
        self.assertEqual([s['status'] for s in result['steps']], ['done', 'skipped'] + ['done'] * 5)
        self.assertIn(f'replaced {OLD_PLUGIN}', steps['wwise-integrate']['detail'])
        self.assertIn(f'migrated from {OLD_SDK}', steps['wwise-project']['detail'])
        self.assertEqual(self.head(), self.git_head_of_origin())
        self.assertEqual((self.project / 'Config/DefaultGame.ini').read_bytes(), self.separate(self.new_ini))
        self.assertTrue((self.project / 'Source/FGGameState.h').is_file())
        self.assertFalse(stale.exists())
        self.assertFalse((old_banks / 'English(US)').exists())
        self.assertFalse((old_banks / 'PluginInfo.xml').exists())
        self.assertTrue((old_banks / 'Init.bnk').is_file())
        self.assertTrue(cli.integration_ready(self.project, NEW_PLUGIN))
        wproj = self.project / cli.WWISE_PROJECT_NAME / (cli.WWISE_PROJECT_NAME + '.wproj')
        self.assertEqual(cli.wproj_version(wproj), NEW_SDK)
        self.assertEqual(cli.soundbanks_version(wproj.parent / 'GeneratedSoundBanks'), NEW_SDK)
        old = [cli.cache_home() / 'wwise-cli/wwise' / OLD_SDK, cli.cache_home() / 'wwise-cli/unrealintegration' / OLD_INTEGRATION]
        self.assertEqual([c['path'] for c in result['old_caches']], [str(path) for path in old])
        self.assertTrue(all(path.is_dir() for path in old))
        calls = self.calls()
        wine = [c['argv'][1] for c in calls if c['name'] == 'wine']
        self.assertEqual(wine, ['migrate', 'generate-soundbank'])
        for call in calls:
            self.assertNotIn('secret', json.dumps(call['argv']))
            if call['name'] != 'wwise-cli':
                for key in CREDENTIAL_NAMES:
                    self.assertNotIn(key, call['env'])
        self.assertNotIn('secret', output + error)
        status = subprocess.run([shutil.which('git'), '-C', str(self.project), 'status', '--porcelain'],
                                check=True, stdout=subprocess.PIPE, text=True).stdout
        self.assertEqual(status, ' M Config/DefaultGame.ini\n')
        self.record.unlink()
        code, output, error = self.update(json_output=False)
        self.assertEqual(code, 0, error)
        self.assertEqual(output.count(': skipped'), 7)
        self.assertIn('old Wwise caches kept', output)
        self.assertEqual({c['name'] for c in self.calls()}, {'git'})

    def git_head_of_origin(self):
        return subprocess.run([shutil.which('git'), '-C', str(self.origin), 'rev-parse', 'master'], check=True,
                              stdout=subprocess.PIPE, text=True).stdout.strip()

    def test_current_project_skips_every_step(self):
        code, output, error = self.update()
        self.assertEqual(code, 0, error)
        result = json.loads(output)
        self.assertEqual([s['status'] for s in result['steps']], ['skipped'] * 7)
        self.assertEqual(result['old_caches'], [])
        self.assertEqual({c['name'] for c in self.calls()}, {'git'})

    def test_bom_already_removed_is_tool_owned(self):
        path = self.project / 'Config/DefaultGame.ini'
        path.write_bytes(path.read_bytes().removeprefix(b'\xef\xbb\xbf'))
        self.upstream_wwise_update()
        code, output, error = self.update()
        self.assertEqual(code, 0, error)
        self.assertEqual(path.read_bytes(), self.separate(self.new_ini))

    def test_resume_after_failed_integration(self):
        self.upstream_wwise_update()
        with patch.dict(os.environ, {'FAKE_WWISE_FAIL': 'integrate-ue'}):
            code, output, error = self.update()
        self.assertEqual(code, 1); self.assertIn('wwise-cli integrate-ue failed', error)
        self.assertEqual(self.head(), self.git_head_of_origin())
        self.assertFalse((self.project / 'Plugins/Wwise').exists())
        ini = self.project / 'Config/DefaultGame.ini'
        self.assertEqual(ini.read_bytes(), self.separate(self.new_ini))
        code, output, error = self.update()
        self.assertEqual(code, 0, error)
        statuses = {s['id']: s['status'] for s in json.loads(output)['steps']}
        self.assertEqual(statuses['checkout'], 'skipped')
        self.assertEqual(statuses['wwise-download'], 'skipped')
        self.assertEqual(statuses['wwise-integrate'], 'done')
        self.assertEqual(statuses['audio-routing'], 'skipped')
        self.assertTrue(cli.integration_ready(self.project, NEW_PLUGIN))

    def test_failed_merge_keeps_audio_routing(self):
        self.upstream_wwise_update()
        # An untracked file in the way makes git refuse the fast-forward.
        (self.project / 'Source').mkdir(exist_ok=True)
        (self.project / 'Source/FGGameState.h').write_text('mine')
        before = (self.project / 'Config/DefaultGame.ini').read_bytes()
        code, output, error = self.update()
        self.assertEqual(code, 1); self.assertIn('git merge failed', error)
        self.assertEqual(self.head(), self.old_head)
        self.assertEqual((self.project / 'Config/DefaultGame.ini').read_bytes(), before)
        self.assertEqual((self.project / 'Source/FGGameState.h').read_text(), 'mine')

    def test_failed_migration_is_reported(self):
        self.upstream_wwise_update()
        with patch.dict(os.environ, {'FAKE_MIGRATE_NOOP': '1'}):
            code, output, error = self.update()
        self.assertEqual(code, 1); self.assertIn('did not migrate the Wwise project', error)

    def assert_refused(self, message):
        code, output, error = self.update()
        self.assertEqual(code, 1, output)
        self.assertEqual(output, '')
        self.assertIn(message, error)
        self.assertNotIn('Traceback', error)
        self.assertEqual(self.head(), self.old_head)
        self.assertNotIn('wwise-cli', [c['name'] for c in self.calls()])

    def test_refuses_without_changing_anything(self):
        project = self.project
        git = lambda *args: subprocess.run([shutil.which('git'), '-C', str(project), *args], check=True,
                                           stdout=subprocess.DEVNULL)
        self.upstream_wwise_update()
        ini = project / 'Config/DefaultGame.ini'
        current = ini.read_bytes()
        with self.subTest('foreign change in a tracked file'):
            (project / 'FactoryGame.uproject').write_text('{"EngineAssociation": "5.6.1-CSS", "Mine": 1}')
            self.assert_refused('FactoryGame.uproject')
            git('checkout', '--', 'FactoryGame.uproject')
        with self.subTest('other DefaultGame.ini change'):
            ini.write_bytes(current + b'Mine=1\r\n')
            self.assert_refused('changes besides AudioRouting=Separate')
            self.assertEqual(ini.read_bytes(), current + b'Mine=1\r\n')
            ini.write_bytes(current)
        with self.subTest('staged DefaultGame.ini change'):
            git('add', 'Config/DefaultGame.ini')
            self.assert_refused('Config/DefaultGame.ini')
            git('reset', '--quiet', '--', 'Config/DefaultGame.ini')
        with self.subTest('local commit'):
            (project / 'Local.txt').write_text('mine')
            git('add', 'Local.txt'); git('commit', '--quiet', '-m', 'Mine')
            local = self.head()
            self.old_head = local
            self.assert_refused('HEAD has commits')
            git('reset', '--quiet', '--hard', 'HEAD~1')
            ini.write_bytes(current)
            self.old_head = self.head()
        with self.subTest('unknown ref'):
            code, output, error = self.update('--ref', 'origin/missing')
            self.assertEqual(code, 1); self.assertIn('Unknown ref: origin/missing', error)
        self.assertEqual(ini.read_bytes(), current)

    def test_refuses_missing_credentials_before_checkout(self):
        self.upstream_wwise_update()
        with patch.dict(os.environ, {'WWISE_PASSWORD': ''}):
            self.assert_refused('WWISE_EMAIL and WWISE_PASSWORD')
        self.assertEqual(self.separate(self.ini), (self.project / 'Config/DefaultGame.ini').read_bytes())

    def test_refuses_engine_change(self):
        self.commit({'FactoryGame.uproject': b'{"EngineAssociation": "5.7.0-CSS"}'}, 'New engine')
        self.assert_refused('engine changes are out of scope')

    def test_refuses_unreadable_versions(self):
        self.commit({'.github/workflows/build.yml': b'jobs: {}\n'}, 'Drop Wwise')
        self.assert_refused('Expected one wwise-cli download')

    def test_refuses_target_without_expected_audio_settings(self):
        self.commit({'Config/DefaultGame.ini': self.ini.replace(b'AudioRouting=Custom\r\n[After]', b'[After]')}, 'Drop routing')
        self.assert_refused('AudioRouting')

    def test_refuses_non_projects(self):
        self.project = self.home / 'empty'
        self.project.mkdir()
        code, output, error = self.update()
        self.assertEqual(code, 1); self.assertIn('Not a Starter Project', error)
        self.project = self.home / "project with 'quotes'" / 'Mods'
        self.project.mkdir(exist_ok=True)
        (self.project / 'FactoryGame.uproject').write_text('{}')
        code, output, error = self.update()
        self.assertEqual(code, 1); self.assertIn('Not the top of a git checkout', error)
