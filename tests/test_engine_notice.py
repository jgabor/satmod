"""Install-script fixtures only: no real account lookup or registration."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


INSTALL = (
    Path(__file__).resolve().parents[1]
    / "packages/unreal-engine-css-bin/unreal-engine-css-bin.install"
)
COMMAND = (
    "/opt/unreal-engine-css/Engine/Binaries/Linux/UnrealVersionSelector"
    " -register -unattended"
)


class EngineNoticeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engine-notice-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "ordinary home with spaces"
        self.ini = self.home / ".config/Epic/UnrealEngine/Install.ini"
        self.ini.parent.mkdir(parents=True)
        self.root_home = self.root / "root home"
        root_ini = self.root_home / ".config/Epic/UnrealEngine/Install.ini"
        root_ini.parent.mkdir(parents=True)
        root_ini.write_text("[Installations]\nroot=/opt/unreal-engine-css\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        getent = self.bin / "getent"
        getent.write_text(
            "#!/bin/bash\n"
            "[[ $1 == passwd && $2 == fixture ]] || exit 2\n"
            "[[ ${LOOKUP_FAIL:-0} == 0 ]] || exit 2\n"
            'printf "%s\\n" "$PASSWD_RECORD"\n'
        )
        getent.chmod(0o755)
        self.env = dict(
            os.environ,
            PATH=str(self.bin),
            HOME=str(self.root_home),
            SUDO_USER="fixture",
            INSTALL=str(INSTALL),
            PASSWD_RECORD=f"fixture:x:1000:1000:Fixture:{self.home}:/bin/bash",
        )
        self.env.pop("BASH_ENV", None)

    def snapshot(self):
        return {
            str(p.relative_to(self.root)): (
                p.stat().st_mode,
                p.read_bytes() if p.is_file() else None,
            )
            for p in self.root.rglob("*")
        }

    def check_notice(self, expected=True):
        before = self.snapshot()
        for hook in ("post_install", "post_upgrade"):
            with self.subTest(hook=hook):
                result = subprocess.run(
                    ["/usr/bin/bash", "-c", f'source "$INSTALL"; {hook} 3 2'],
                    env=self.env,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                if expected:
                    self.assertIn(COMMAND, result.stdout)
                    self.assertIn("without sudo", result.stdout)
                    self.assertIn(
                        "If not already registered for your account", result.stdout
                    )
                else:
                    self.assertEqual(result.stdout, "")
                self.assertEqual(self.snapshot(), before, "fixture state changed")

    def test_missing_ini_prints_instruction(self):
        self.check_notice()

    def test_registered_label_or_guid_suppresses_both_hooks(self):
        for key in ("CSS", "{01234567-89AB-CDEF-0123-456789ABCDEF}"):
            with self.subTest(key=key):
                self.ini.write_text(
                    f"[Installations]\nOther=/opt/other\n{key}=/opt/unreal-engine-css\n"
                )
                self.check_notice(expected=False)

    def test_other_engine_prints_instruction(self):
        self.ini.write_text("[Installations]\nCSS=/opt/other-engine\n")
        self.check_notice()

    def test_commented_entries_do_not_suppress(self):
        self.ini.write_text(
            "[Installations]\n;CSS=/opt/unreal-engine-css\n"
            "  #CSS=/opt/unreal-engine-css\n"
        )
        self.check_notice()

    def test_other_sections_do_not_suppress(self):
        self.ini.write_text(
            "CSS=/opt/unreal-engine-css\n[Installations]\nOther=/opt/other\n"
            "[OtherSection]\nCSS=/opt/unreal-engine-css\n"
        )
        self.check_notice()

    def test_crlf_whitespace_trailing_slash_and_no_final_newline(self):
        self.ini.write_bytes(
            b"  [Installations] \r\n  CSS = /opt/unreal-engine-css/ \r"
        )
        self.check_notice(expected=False)

    def test_no_sudo_user_or_root_ignores_home(self):
        for user in (None, "", "root"):
            with self.subTest(user=user):
                self.env.pop("SUDO_USER", None)
                if user is not None:
                    self.env["SUDO_USER"] = user
                self.check_notice()

    def test_lookup_failure_prints_conditional_reminder(self):
        self.env["LOOKUP_FAIL"] = "1"
        self.check_notice()

    def test_invalid_or_root_account_prints_reminder(self):
        self.ini.write_text("[Installations]\nCSS=/opt/unreal-engine-css\n")
        for record in (
            f"fixture:x:0:0:Root:{self.home}:/bin/bash",
            f"other:x:1000:1000:Other:{self.home}:/bin/bash",
            "fixture:x:not-a-uid:1000:Fixture:relative:/bin/bash",
        ):
            with self.subTest(record=record):
                self.env["PASSWD_RECORD"] = record
                self.check_notice()

    def test_failed_ini_read_does_not_fail_hooks(self):
        self.ini.mkdir()
        self.check_notice()


if __name__ == "__main__":
    unittest.main()
