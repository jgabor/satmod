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
        with patch.dict(os.environ, {'BASH_ENV': str(startup), 'ENV': str(startup)}):
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
        for key in ('BASH_ENV', 'ENV', 'STARTUP_RAN'):
            self.assertNotIn(key, record['env'])
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
