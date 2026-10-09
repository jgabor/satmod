"""Isolated setup contract tests. Never run real Wine or download Microsoft files."""

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "packages/satisfactory-modding-setup"
loader = importlib.machinery.SourceFileLoader(
    "setup_cli", str(RECIPE / "satisfactory-modding-setup")
)
spec = importlib.util.spec_from_loader(loader.name, loader)
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="setup-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.source = self.base / "source"
        (self.source / "wrappers").mkdir(parents=True)
        self.engine = self.base / "engine"
        self.selector = self.engine / "Engine/Binaries/Linux/UnrealVersionSelector"
        self.selector.parent.mkdir(parents=True)
        self.selector.write_text(
            "#!/usr/bin/env python3\nimport os, pathlib, sys\n"
            'assert sys.argv[1:] == ["-register", "-unattended"]\n'
            'p=pathlib.Path(os.environ["HOME"])/".config/Epic/UnrealEngine/Install.ini"\n'
            "p.parent.mkdir(parents=True, exist_ok=True)\n"
            f'p.write_text("[Installations]\\nnew={self.engine}\\n")\n'
        )
        self.selector.chmod(0o755)
        self.env = dict(
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.home / "config with spaces"),
            XDG_DATA_HOME=str(self.home / "data"),
            XDG_CACHE_HOME=str(self.home / "cache with spaces"),
            WINEPREFIX=str(self.home / ".wine"),
            WINEARCH="win32",
            BASH_ENV="/dev/null",
        )
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, self.env).start()
        patch.object(cli, "SOURCE", self.source).start()
        patch.object(cli, "ENGINE", self.engine).start()
        self.args = argparse.Namespace(
            toolchain=str(self.home / "data/satisfactory-modding/msvc"),
            cache=str(self.home / "cache with spaces/msvc-wine"),
            wineprefix=str(self.home / "prefix with spaces"),
        )
        self.calls = []
        self.bad = None
        real_run = cli.run

        def fake_run(argv, env, cwd=None, capture=False):
            argv = [str(a) for a in argv]
            self.calls.append((argv, dict(env)))
            if argv[0] == "python3" and argv[1].endswith("vsdownload.py"):
                if self.bad != "refusal":
                    self.populate(Path(argv[argv.index("--dest") + 1]))
                return None
            if argv[:2] == ["wine", "wineboot"]:
                # Emulate a pending registry flush, including managed-prefix retries.
                (Path(env["WINEPREFIX"]) / "system.reg").unlink(missing_ok=True)
                self.assertFalse((Path(env["WINEPREFIX"]) / "system.reg").exists())
                return None
            if argv == ["wineserver", "-w"]:
                self.assertEqual(self.calls[-2][0], ["wine", "wineboot", "-u"])
                self.assertEqual(self.calls[-2][1], env)
                if self.bad == "wait":
                    raise cli.SetupError("Wine wait failed")
                if self.bad != "registry":
                    (Path(env["WINEPREFIX"]) / "system.reg").write_text(
                        "#arch=win32\n" if self.bad == "arch" else "#arch=win64\n"
                    )
                return None
            if argv[0] == "bash" and argv[1].endswith("install.sh"):
                self.assertEqual(self.calls[-2][0], ["wineserver", "-w"])
                self.assertIn(
                    "#arch=win64", (Path(env["WINEPREFIX"]) / "system.reg").read_text()
                )
                return None
            return real_run(argv, env, cwd, capture)

        patch.object(cli, "run", fake_run).start()
        patch.object(cli.shutil, "which", return_value="/fake/tool").start()
        self.make_wrappers()

    def make_wrappers(self):
        for name in ("cl", "link", "rc"):
            file = self.source / "wrappers" / name
            file.write_text(
                "#!/usr/bin/env python3\nimport json, pathlib, sys, os\n"
                f"role={name!r}\n"
                "p=pathlib.Path.cwd()\n"
                "root=pathlib.Path(__file__).resolve().parents[2]\n"
                'assert os.environ["WINEARCH"] == "win64"\n'
                'assert os.environ["WINEPREFIX"].endswith("prefix with spaces")\n'
                'if role=="cl":\n'
                ' assert sys.argv[1:]==["/nologo", "/c", "smoke.cpp", "/Fosmoke.obj", "/sourceDependencies", "deps.json"]\n'
                ' (p/"smoke.obj").write_bytes(b"object")\n'
                ' (p/"deps.json").write_text(json.dumps({"Data":{"Source":str(p/"smoke.cpp"),'
                '"Includes":[str(root/"kits/10/include/10.0.22621.0/um/windows.h")]}}))\n'
                'elif role=="link": (p/"smoke.exe").write_bytes(b"exe")\n'
                'else: (p/"smoke.res").write_bytes(b"resource")\n'
            )
            file.chmod(0o755)
            (self.source / "wrappers" / (name + ".exe")).symlink_to(name)
        file = self.source / "wrappers/msvcenv.sh"
        file.write_text("# fixture environment\n")
        file.chmod(0o755)

    def populate(self, root):
        vc = root / "vc/tools/msvc/14.38.33130"
        sdk = root / "kits/10"
        for path in (
            vc / "bin/Hostx64/x64/cl.exe",
            vc / "bin/Hostx64/x64/link.exe",
            vc / "include/vcruntime.h",
            vc / "lib/x64/libcmt.lib",
            sdk / "bin/10.0.22621.0/x64/rc.exe",
            sdk / "include/10.0.22621.0/um/windows.h",
            sdk / "include/10.0.22621.0/shared/windef.h",
            sdk / "include/10.0.22621.0/ucrt/stdio.h",
            sdk / "lib/10.0.22621.0/um/x64/kernel32.lib",
            sdk / "lib/10.0.22621.0/ucrt/x64/libucrt.lib",
            root / "bin/msvctricks.exe",
            root / "bin/process_sourcedependencies.exe",
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        shutil.copytree(self.source / "wrappers", root / "bin/x64", symlinks=True)
        (root / "bin/x64/msvcenv.sh").write_text(
            'BASE_UNIX=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)\n'
            "MSVCVER=14.38.33130\nSDKVER=10.0.22621.0\nARCH=x64\n"
            "BINDIR=$BASE_UNIX/vc/tools/msvc/$MSVCVER/bin/Hostx64/x64\n"
            "SDKBINDIR=$BASE_UNIX/kits/10/bin/$SDKVER/x64\n"
        )
        if self.bad == "helper":
            (root / "bin/msvctricks.exe").unlink()
        elif self.bad == "version":
            file = root / "bin/x64/msvcenv.sh"
            file.write_text(file.read_text().replace("14.38.33130", "14.39.33130"))
        elif self.bad == "deps":
            file = root / "bin/x64/cl"
            file.write_text(
                file.read_text().replace('str(p/"smoke.cpp")', '"Z:\\\\smoke.cpp"')
            )

    def test_managed_msvcenv_fresh_repeat_and_stale_prefix(self):
        cli.setup(self.args)
        script = Path(self.args.toolchain) / "bin/x64/msvcenv.sh"
        fresh = script.read_text()
        block = cli.managed_msvcenv_block(self.args.wineprefix)
        self.assertTrue(fresh.endswith(block))
        self.assertEqual(fresh.count(cli.MSVCENV_BEGIN), 1)
        self.assertEqual(fresh.count(cli.MSVCENV_END), 1)
        cli.setup(self.args)
        self.assertEqual(script.read_text(), fresh)
        script.write_text(fresh.replace(block, cli.managed_msvcenv_block("/wrong")))
        cli.setup(self.args)
        self.assertEqual(script.read_text(), fresh)
        # Completed installs made before this fix have no block at all.
        script.write_text(fresh.replace(block, ""))
        cli.setup(self.args)
        self.assertEqual(script.read_text(), fresh)

    def test_managed_msvcenv_overrides_bash_env_for_wrapper_and_child(self):
        cli.setup(self.args)
        script = Path(self.args.toolchain) / "bin/x64/msvcenv.sh"
        startup = self.base / "bash startup"
        startup.write_text("export WINEPREFIX=/wrong\n")
        result = subprocess.run(
            ["bash", "-c", 'test "$WINEPREFIX" = /wrong || exit 1; '
             '. "$1"; bash -c \'printf %s "$WINEPREFIX"\'', "--", str(script)],
            env=dict(os.environ, BASH_ENV=str(startup), ENV=str(startup),
                     WINEPREFIX=self.args.wineprefix),
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout, self.args.wineprefix)
        self.assertEqual(result.stderr, "")

    def test_validate_rejects_missing_or_mismatched_managed_msvcenv(self):
        cli.setup(self.args)
        root = Path(self.args.toolchain)
        script = root / "bin/x64/msvcenv.sh"
        content = script.read_text()
        block = cli.managed_msvcenv_block(self.args.wineprefix)
        for replacement in ("", cli.managed_msvcenv_block("/wrong")):
            with self.subTest(replacement=replacement):
                script.write_text(content.replace(block, replacement))
                with self.assertRaisesRegex(cli.SetupError, "managed Wine prefix block"):
                    cli.validate(root, cli.wine_environment(self.args.wineprefix))

    def test_root_and_missing_tools_have_no_side_effects(self):
        for kind in ("root", "tools"):
            with self.subTest(kind=kind):
                with (
                    patch.object(
                        cli.os,
                        "getuid",
                        return_value=0 if kind == "root" else os.getuid(),
                    ),
                    patch.object(
                        cli.shutil,
                        "which",
                        return_value=None if kind == "tools" else "/fake/tool",
                    ),
                ):
                    with self.assertRaises(cli.SetupError):
                        cli.setup(self.args)
                self.assertEqual(list(self.home.iterdir()), [])
                self.assertEqual(self.calls, [])

    def test_first_install_without_flag_stages_environment_repeat_and_quoting(self):
        rc = self.home / ".unrealrc"
        rc.write_text("# existing\nexport CUSTOM='yes'\n")
        result = cli.setup(self.args)
        self.assertFalse(result["reused"])
        download = self.calls[0][0]
        stage = download[download.index("--dest") + 1]
        self.assertEqual(
            download,
            [
                "python3",
                str(self.source / "vsdownload.py"),
                "--dest",
                stage,
                "--cache",
                self.args.cache,
                "--msvc-version",
                "17.8",
                "--sdk-version",
                "10.0.22621",
                "--channel",
                "release.ltsc.17.8",
                "--accept-license",
            ],
        )
        self.assertIn(
            ["bash", str(self.source / "install.sh"), stage], [a for a, _ in self.calls]
        )
        for _, env in self.calls:
            self.assertEqual(env["WINEPREFIX"], self.args.wineprefix)
            self.assertEqual(env["WINEARCH"], "win64")
        self.assertFalse((self.home / ".wine").exists())
        self.assertIn("# existing\nexport CUSTOM='yes'\n", rc.read_text())
        self.assertEqual(rc.read_text().count("# satisfactory-modding-setup"), 1)
        self.assertFalse((self.home / "config with spaces/Epic").exists())
        self.assertEqual((Path(result["environment"]).stat().st_mode & 0o777), 0o600)
        marker = Path(self.args.toolchain) / cli.MARKER
        record = json.loads(marker.read_text())
        self.assertEqual(
            record.pop("configured"),
            {"home": str(self.home), "environment": result["environment"]},
        )
        # pkgrel 1 markers lack configured, but remain reusable.
        marker.write_text(json.dumps(record))
        self.calls.clear()
        again = cli.setup(self.args)
        self.assertTrue(again["reused"])
        self.assertIn("configured", json.loads(marker.read_text()))
        self.assertFalse(any(a[0] in ("python3", "wine") for a, _ in self.calls))
        self.assertFalse(any("UnrealVersionSelector" in a[0] for a, _ in self.calls))
        self.assertEqual(rc.read_text().count("# satisfactory-modding-setup"), 1)
        result = subprocess.run(
            [
                "bash",
                "-c",
                '. "$HOME/.unrealrc"; printf "%s\\n" "$UE_WINE_MSVC" "$WINEPREFIX"',
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(
            result.stdout.splitlines(), [self.args.toolchain, self.args.wineprefix]
        )

    def test_artifact_failures_do_not_configure_or_promote(self):
        for bad in ("refusal", "helper", "version", "deps"):
            with self.subTest(bad=bad):
                self.bad = bad
                with self.assertRaises(cli.SetupError):
                    cli.setup(self.args)
                self.assertFalse(Path(self.args.toolchain).exists())
                self.assertFalse((self.home / ".unrealrc").exists())
                self.assertFalse((self.home / ".config/Epic").exists())
                self.assertTrue(Path(self.args.cache).exists())

    def test_cache_and_unrecognized_destination_preserved(self):
        cache = Path(self.args.cache)
        cache.mkdir(parents=True)
        (cache / "payload").write_bytes(b"cached")
        root = Path(self.args.toolchain)
        root.mkdir(parents=True)
        (root / "precious").write_text("leave me")
        with self.assertRaisesRegex(cli.SetupError, "unrecognized"):
            cli.setup(self.args)
        self.assertEqual((root / "precious").read_text(), "leave me")
        self.assertEqual((cache / "payload").read_bytes(), b"cached")
        self.assertEqual(self.calls, [])

    def test_broken_completed_install_never_overwritten(self):
        cli.setup(self.args)
        root = Path(self.args.toolchain)
        (root / "bin/process_sourcedependencies.exe").unlink()
        self.calls.clear()
        with self.assertRaises(cli.SetupError):
            cli.setup(self.args)
        self.assertTrue((root / cli.MARKER).exists())
        self.assertFalse(any(a[0] == "python3" for a, _ in self.calls))

    def test_wineserver_missing_preflight_has_no_side_effects(self):
        with patch.object(
            cli.shutil,
            "which",
            side_effect=lambda t: None if t == "wineserver" else "/fake/tool",
        ):
            with self.assertRaisesRegex(
                cli.SetupError, "Missing required tool: wineserver"
            ):
                cli.setup(self.args)
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_wine_wait_and_registry_failures_preserve_stage_without_advancing(self):
        for bad in ("wait", "registry", "arch"):
            with self.subTest(bad=bad):
                self.bad = bad
                self.calls.clear()
                with self.assertRaises(cli.SetupError):
                    cli.setup(self.args)
                stage = Path(self.calls[0][0][3])
                self.assertTrue(stage.is_dir())
                self.assertFalse(Path(self.args.toolchain).exists())
                self.assertFalse((self.home / ".unrealrc").exists())
                self.assertFalse(any(a[0] == "bash" for a, _ in self.calls))
                registry = Path(self.args.wineprefix) / "system.reg"
                if registry.exists():
                    registry.unlink()

    def test_completion_record_only_after_registration_and_configuration(self):
        marker = Path(self.args.toolchain) / cli.MARKER
        for function in ("register_engine", "configure"):
            with self.subTest(function=function):
                with patch.object(
                    cli, function, side_effect=cli.SetupError("fixture failure")
                ):
                    with self.assertRaisesRegex(cli.SetupError, "fixture failure"):
                        cli.setup(self.args)
                self.assertNotIn("configured", json.loads(marker.read_text()))
                cli.setup(self.args)
                self.assertIn("configured", json.loads(marker.read_text()))

    def test_failed_stage_retry_reuses_cache_without_touching_failed_stage(self):
        cache = Path(self.args.cache)
        cache.mkdir(parents=True)
        (cache / "payload").write_bytes(b"cached")
        self.bad = "helper"
        with self.assertRaises(cli.SetupError):
            cli.setup(self.args)
        stage = Path(self.calls[0][0][3])
        self.assertTrue(stage.is_dir())
        self.bad = None
        self.calls.clear()
        cli.setup(self.args)
        self.assertTrue(stage.is_dir())
        self.assertEqual((cache / "payload").read_bytes(), b"cached")
        self.assertEqual(self.calls[0][0][5], str(cache))

    def test_missing_completed_prefix_does_not_implicitly_initialize_wine(self):
        cli.setup(self.args)
        (Path(self.args.wineprefix) / "system.reg").unlink()
        self.calls.clear()
        with self.assertRaisesRegex(cli.SetupError, "initialized Wine prefix"):
            cli.setup(self.args)
        self.assertEqual(self.calls, [])

    def test_nonwritable_location_fails_before_commands(self):
        with patch.object(cli.os, "access", return_value=False):
            with self.assertRaisesRegex(cli.SetupError, "writable user-owned"):
                cli.setup(self.args)
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_alias_and_generated_path_mismatch_fail_validation(self):
        cli.setup(self.args)
        root = Path(self.args.toolchain)
        alias = root / "bin/x64/cl.exe"
        alias.unlink()
        alias.symlink_to("link")
        with self.assertRaisesRegex(cli.SetupError, "alias"):
            cli.setup(self.args)
        alias.unlink()
        alias.symlink_to("cl")
        script = root / "bin/x64/msvcenv.sh"
        script.write_text(script.read_text().replace("Hostx64/x64", "Hostx64/x86"))
        with self.assertRaisesRegex(cli.SetupError, "installed paths"):
            cli.setup(self.args)

    def test_home_hook_moves_without_modifying_project_or_other_hooks(self):
        rc = self.home / ".unrealrc"
        rc.write_text(". /intentional/custom/environment\n")
        project = self.base / "project"
        project.mkdir()
        (project / ".unrealrc").write_text("# project override\n")
        cli.setup(self.args)
        os.environ["XDG_CONFIG_HOME"] = str(self.home / "new config 'quoted'")
        result = cli.setup(self.args)
        self.assertTrue(
            rc.read_text().startswith(". /intentional/custom/environment\n")
        )
        self.assertEqual(rc.read_text().count("# satisfactory-modding-setup"), 1)
        self.assertIn(shlex.quote(result["environment"]), rc.read_text())
        self.assertEqual((project / ".unrealrc").read_text(), "# project override\n")

    def test_whitespace_and_unmanaged_or_win32_prefix_rejected(self):
        self.args.toolchain += " bad"
        with self.assertRaisesRegex(cli.SetupError, "whitespace"):
            cli.setup(self.args)
        self.assertEqual(self.calls, [])
        self.args.toolchain = self.args.toolchain.removesuffix(" bad")
        prefix = Path(self.args.wineprefix)
        prefix.mkdir()
        (prefix / "system.reg").write_text("#arch=win32\n")
        with self.assertRaisesRegex(cli.SetupError, "unmanaged"):
            cli.setup(self.args)
        (prefix / cli.MARKER).write_text(json.dumps({"source_pin": cli.PIN}))
        with self.assertRaisesRegex(cli.SetupError, "win64"):
            cli.setup(self.args)
        self.assertEqual(self.calls, [])

    def test_registration_preserves_pruned_mappings_and_other_sections(self):
        ini = self.home / ".config/Epic/UnrealEngine/Install.ini"
        ini.parent.mkdir(parents=True)
        ini.write_text(
            "[Installations]\nold=/missing/temporarily\nother=/other/engine\n[Extra]\nkeep=Yes\n"
        )
        cli.setup(self.args)
        parsed = cli.read_ini(ini)
        self.assertEqual(
            dict(parsed.items("Installations")),
            {
                "old": "/missing/temporarily",
                "other": "/other/engine",
                "new": str(self.engine),
            },
        )
        self.assertEqual(parsed.get("Extra", "keep"), "Yes")
        self.assertEqual(ini.stat().st_mode & 0o777, 0o600)

    def test_registration_zero_without_write_restores_original(self):
        ini = self.home / ".config/Epic/UnrealEngine/Install.ini"
        ini.parent.mkdir(parents=True)
        original = b"[Installations]\nold=/missing\n"
        ini.write_bytes(original)
        self.selector.write_text("#!/bin/bash\nexit 0\n")
        with self.assertRaisesRegex(cli.SetupError, "did not write"):
            cli.setup(self.args)
        self.assertEqual(ini.read_bytes(), original)
        self.assertFalse((self.home / ".unrealrc").exists())
        self.assertTrue((Path(self.args.toolchain) / cli.MARKER).exists())
        # Retrying registration must not redownload a completed toolchain.
        self.calls.clear()
        with self.assertRaises(cli.SetupError):
            cli.setup(self.args)
        self.assertFalse(any(a[0] == "python3" for a, _ in self.calls))

    def test_registration_failure_after_pruning_restores_original(self):
        ini = self.home / ".config/Epic/UnrealEngine/Install.ini"
        ini.parent.mkdir(parents=True)
        ini.write_text("[Installations]\nold=/missing\n")
        original = ini.read_bytes()
        self.selector.write_text(self.selector.read_text() + "sys.exit(7)\n")
        with self.assertRaisesRegex(cli.SetupError, "Command failed"):
            cli.setup(self.args)
        self.assertEqual(ini.read_bytes(), original)

    def test_registration_interruption_after_pruning_restores_bytes_and_mode(self):
        ini = self.home / ".config/Epic/UnrealEngine/Install.ini"
        ini.parent.mkdir(parents=True)
        original = b"[Installations]\nold=/missing/temporarily\nother=/other/engine\n"
        ini.write_bytes(original)
        ini.chmod(0o640)
        interruption = KeyboardInterrupt()

        def interrupt_registration(argv, env):
            self.assertEqual(argv, [self.selector, "-register", "-unattended"])
            ini.write_text(f"[Installations]\nnew={self.engine}\n")
            ini.chmod(0o600)
            raise interruption

        with patch.object(cli, "run", side_effect=interrupt_registration):
            with self.assertRaises(KeyboardInterrupt) as caught:
                cli.register_engine(
                    self.home, cli.wine_environment(Path(self.args.wineprefix))
                )
        self.assertIs(caught.exception, interruption)
        self.assertEqual(ini.read_bytes(), original)
        self.assertEqual(ini.stat().st_mode & 0o777, 0o640)

    def test_launcher_arguments_environment_exit_and_help(self):
        cli.setup(self.args)
        command = ["bash", str(RECIPE / "satisfactory-modding-run")]
        result = subprocess.run(
            command
            + [
                "python3",
                "-c",
                'import os,sys,json; print(json.dumps([sys.argv[1:],os.environ["WINEPREFIX"]])); sys.exit(23)',
                "a b",
                "'quoted'",
                "--flag",
                "",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [["a b", "'quoted'", "--flag", ""], self.args.wineprefix],
        )
        self.assertEqual(
            subprocess.run(command + ["--help"], capture_output=True).returncode, 0
        )
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
        process = subprocess.Popen(
            command + ["python3", "-c", "import os; print(os.getpid())"],
            stdout=subprocess.PIPE,
            text=True,
        )
        stdout, _ = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(int(stdout.strip()), process.pid)

    def test_main_defaults_json_and_errors_without_tracebacks(self):
        with (
            patch.object(cli, "setup", return_value={"status": "complete"}) as setup,
            patch.object(cli.sys, "argv", ["setup", "--json"]),
            patch("builtins.print") as output,
        ):
            self.assertEqual(cli.main(), 0)
        args = setup.call_args.args[0]
        self.assertEqual(
            args.toolchain, str(self.home / "data/satisfactory-modding/msvc")
        )
        self.assertEqual(
            args.cache,
            str(self.home / "cache with spaces/satisfactory-modding/msvc-wine"),
        )
        self.assertEqual(
            args.wineprefix, str(self.home / "data/satisfactory-modding/wineprefix")
        )
        self.assertEqual(json.loads(output.call_args.args[0]), {"status": "complete"})
        with (
            patch.object(cli, "setup", side_effect=OSError("failed")),
            patch.object(cli.sys, "argv", ["setup"]),
            patch("builtins.print") as output,
        ):
            self.assertEqual(cli.main(), 1)
        self.assertIn("failed", output.call_args.args[0])
        self.assertEqual(output.call_args.kwargs["file"], cli.sys.stderr)


class SetupRecipeTests(unittest.TestCase):
    def test_install_and_upgrade_print_notice_without_user_state(self):
        for hook in ("post_install", "post_upgrade"):
            with self.subTest(hook=hook), tempfile.TemporaryDirectory() as temp:
                result = subprocess.run(
                    ["bash", "-c", 'source "$1"; "$2"', "notice",
                     str(RECIPE / "satisfactory-modding-setup.install"), hook],
                    env=dict(os.environ, HOME=str(Path(temp) / "nonexistent"),
                             SUDO_USER="nonexistent-satisfactory-user", BASH_ENV="/dev/null"),
                    text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                for text in ("satisfactory-modding-setup --json",
                             "https://visualstudio.microsoft.com/license-terms/",
                             "https://developer.microsoft.com/windows/downloads/windows-sdk/"):
                    self.assertIn(text, result.stdout)

    def test_srcinfo_and_checksums(self):
        result = subprocess.run(
            ["makepkg", "--printsrcinfo"],
            cwd=RECIPE,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout, (RECIPE / ".SRCINFO").read_text())
        fields = {}
        for line in result.stdout.splitlines():
            if " = " in line:
                key, value = line.strip().split(" = ", 1)
                fields.setdefault(key, []).append(value)
        for source, checksum in zip(fields["source"][1:], fields["sha256sums"][1:]):
            self.assertEqual(
                hashlib.sha256((RECIPE / source).read_bytes()).hexdigest(), checksum
            )
        self.assertIn("msitools", fields["depends"])
        self.assertIn("unreal-engine-css-bin", fields["depends"])
        self.assertNotIn("unzip", fields["depends"])
        self.assertEqual(fields["license"], ["ISC"])

    def test_package_complete_source_and_modes(self):
        archive = ROOT / f".cache/upstream/msvc-wine/msvc-wine-{cli.PIN}.tar.gz"
        if not archive.exists():
            self.skipTest(
                "Pinned public archive absent; fetch it into the documented source cache for package test"
            )
        with tempfile.TemporaryDirectory(prefix="setup-package-") as tmp:
            src, pkg = Path(tmp) / "src", Path(tmp) / "pkg"
            src.mkdir()
            pkg.mkdir()
            subprocess.run(["tar", "-xf", str(archive), "-C", str(src)], check=True)
            for name in (
                "satisfactory-modding-setup",
                "satisfactory-modding-run",
                "LICENSE",
            ):
                shutil.copyfile(RECIPE / name, src / name)
            subprocess.run(
                [
                    "bash",
                    "-c",
                    f"source {shlex.quote(str(RECIPE / 'PKGBUILD'))}; package",
                ],
                env=dict(os.environ, srcdir=str(src), pkgdir=str(pkg)),
                check=True,
            )
            upstream = src / f"msvc-wine-{cli.PIN}"
            installed = pkg / "usr/share/satisfactory-modding-setup/msvc-wine"
            self.assertEqual(
                sorted(str(p.relative_to(upstream)) for p in upstream.rglob("*")),
                sorted(str(p.relative_to(installed)) for p in installed.rglob("*")),
            )
            self.assertEqual(
                len([p for p in (installed / "patches").rglob("*") if p.is_file()]), 5
            )
            for name in (
                "msvctricks.cpp",
                "process_sourcedependencies.cpp",
                "lowercase",
                "fixinclude",
                "LICENSE.txt",
            ):
                self.assertTrue((installed / name).is_file())
            for file in upstream.rglob("*"):
                target = installed / file.relative_to(upstream)
                if file.is_symlink():
                    self.assertEqual(os.readlink(target), os.readlink(file))
                    self.assertFalse(os.path.isabs(os.readlink(target)))
                elif file.is_file():
                    self.assertEqual(file.read_bytes(), target.read_bytes())
                    self.assertFalse(target.stat().st_mode & 0o022)
            self.assertEqual(
                (pkg / "usr/bin/satisfactory-modding-setup").stat().st_mode & 0o777,
                0o755,
            )
            self.assertEqual(
                (pkg / "usr/bin/satisfactory-modding-run").stat().st_mode & 0o777, 0o755
            )
            self.assertTrue(
                (
                    pkg
                    / "usr/share/licenses/satisfactory-modding-setup/msvc-wine-LICENSE.txt"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
