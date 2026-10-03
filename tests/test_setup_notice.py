"""Read-only pacman notice fixtures, with no real account lookup or Wine."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

import test_setup

HOOK = test_setup.RECIPE / "satisfactory-modding-setup.install"


class SetupNoticeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="setup-notice-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "account with ' spaces"
        self.root = self.home / ".local/share/satisfactory-modding/msvc"
        self.prefix = self.root.parent / "wineprefix"
        self.environment = self.home / ".config/satisfactory-modding/environment.sh"
        self.marker = self.root / test_setup.cli.MARKER
        self.bin = self.base / "bin"
        self.bin.mkdir()
        getent = self.bin / "getent"
        getent.write_text(
            "#!/bin/bash\n[[ $1 == passwd && $2 == fixture ]] || exit 1\n"
            'printf "%s\\n" "$ACCOUNT"\n'
        )
        getent.chmod(0o755)
        self.account = f"fixture:x:1000:1000::{self.home}:/bin/bash"

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def complete(self):
        pin = test_setup.cli.PIN
        record = dict(
            source_pin=pin,
            selection=test_setup.cli.SELECTION,
            versions={"msvc": "14.38.33130", "sdk": "10.0.22621.0"},
            toolchain=str(self.root),
            wineprefix=str(self.prefix),
            configured={"home": str(self.home), "environment": str(self.environment)},
        )
        self.write(self.marker, json.dumps(record))
        self.write(self.prefix / test_setup.cli.MARKER, json.dumps({"source_pin": pin}))
        self.write(
            self.prefix / "system.reg", "WINE REGISTRY Version 2\n\n#arch=win64\n"
        )
        # Reuse the existing artifact fixture without its process/account patches.
        fixture = test_setup.SetupTests()
        fixture.source = self.base / "source"
        fixture.bad = None
        (fixture.source / "wrappers").mkdir(parents=True)
        for name in ("cl", "link", "rc"):
            (fixture.source / "wrappers" / name).write_text("fixture")
        fixture.populate(self.root)
        self.write(
            self.environment,
            "# Managed by satisfactory-modding-setup\n"
            f"export UE_WINE_MSVC={shlex.quote(str(self.root))}\n"
            f"export WINEPREFIX={shlex.quote(str(self.prefix))}\nexport WINEARCH=win64\n",
        )
        self.write(
            self.home / ".unrealrc",
            f"[ ! -f {shlex.quote(str(self.environment))} ] || . "
            f"{shlex.quote(str(self.environment))} # satisfactory-modding-setup\n",
        )
        self.write(
            self.home / ".config/Epic/UnrealEngine/Install.ini",
            "[Installations]\nfixture=/opt/unreal-engine-css\n",
        )

    def notice(self, function="post_install", sudo_user="fixture"):
        def contents(p):
            try:
                return p.read_bytes()
            except PermissionError:
                return None

        before = {
            p: (contents(p), p.stat().st_mtime_ns)
            for p in self.home.rglob("*")
            if p.is_file()
        }
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; "$2"', "--", str(HOOK), function],
            env=dict(
                PATH=str(self.bin) + ":/usr/bin",
                HOME="/root",
                XDG_DATA_HOME="/root/unknown",
                XDG_CONFIG_HOME="/root/unknown",
                SUDO_USER=sudo_user,
                ACCOUNT=self.account,
                PYTHONPATH=str(self.base),
                PYTHONOPTIMIZE="1",
            ),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        after = {
            p: (contents(p), p.stat().st_mtime_ns)
            for p in self.home.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)
        return result.stdout

    def assert_notice(self, **kwargs):
        output = self.notice(**kwargs)
        self.assertIn(
            "If setup is not already complete for your account, run as your ordinary user, without sudo:",
            output,
        )
        self.assertIn("ordinary user, without sudo", output)
        self.assertIn("  satisfactory-modding-setup --json\n", output)
        self.assertNotIn("--accept-msvc-license", output)
        self.assertIn(
            "Running setup downloads Microsoft MSVC/Windows SDK tools subject to applicable Microsoft license terms.",
            output,
        )
        self.assertIn("https://visualstudio.microsoft.com/license-terms/", output)

    def test_complete_install_and_upgrade_silent_readonly(self):
        self.complete()
        for function in ("post_install", "post_upgrade"):
            self.assertEqual(self.notice(function), "")

    def test_missing_partial_corrupt_and_failed_configuration(self):
        self.assert_notice()
        self.complete()
        original = self.marker.read_text()
        for content in (
            "{broken",
            "[]",
            "{}",
            original.replace("configured", "not_configured"),
            "x" * 65537,
        ):
            self.marker.write_text(content)
            self.assert_notice()
        self.marker.write_text(original)
        for path in (
            self.environment,
            self.home / ".unrealrc",
            self.prefix / "system.reg",
            self.root / "bin/msvctricks.exe",
        ):
            original = path.read_bytes()
            path.unlink()
            self.assert_notice()
            path.write_bytes(original)

    def test_wrong_config_registration_and_custom_paths(self):
        self.complete()
        environment = self.environment.read_text()
        self.environment.write_text("touch /must-not-execute\n")
        self.assert_notice()
        self.environment.write_text(environment)
        ini = self.home / ".config/Epic/UnrealEngine/Install.ini"
        registration = ini.read_text()
        ini.write_text("[Installations]\nother=/opt/other\n")
        self.assert_notice()
        ini.write_text(registration)
        record = json.loads(self.marker.read_text())
        record["configured"]["environment"] = "/custom/environment.sh"
        self.marker.write_text(json.dumps(record))
        self.assert_notice()

    def test_unknown_root_and_invalid_account_never_infer_home(self):
        self.complete()
        for sudo_user in ("", "root", "unknown"):
            self.assert_notice(sudo_user=sudo_user)
        for account in (
            f"fixture:x:0:0::{self.home}:/bin/bash",
            f"other:x:1000:1000::{self.home}:/bin/bash",
            "fixture:x:1000:1000::relative:/bin/bash",
            "corrupt",
        ):
            self.account = account
            self.assert_notice()

    def test_unreadable_state_fails_open(self):
        self.complete()
        self.marker.chmod(0)
        if os.getuid() == 0:
            self.skipTest("root can read mode 000 files")
        self.assert_notice()


if __name__ == "__main__":
    unittest.main()
