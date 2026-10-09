"""Release updater fixtures: real makepkg metadata, fake gh, no archive transfers."""

import base64
import copy
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/update-engine-release"
loader = importlib.machinery.SourceFileLoader("release_updater", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
updater = importlib.util.module_from_spec(spec)
loader.exec_module(updater)


class ReleaseMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="css-updater-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "checkout with spaces"
        self.package = self.root / "packages/unreal-engine-css-bin"
        self.package.mkdir(parents=True)
        (self.root / "scripts").mkdir()
        shutil.copyfile(SCRIPT, self.root / "scripts/update-engine-release")
        shutil.copyfile(
            ROOT / "upstream-inputs.json", self.root / "upstream-inputs.json"
        )
        for name in (
            "PKGBUILD",
            ".SRCINFO",
            "LICENSE.md",
            "setup-dotnet-permissions.patch",
            "download-gh-asset",
            "unreal-engine-css-bin.install",
        ):
            shutil.copyfile(
                ROOT / "packages/unreal-engine-css-bin" / name, self.package / name
            )
        self.pins = json.loads((self.root / "upstream-inputs.json").read_text())
        engine = self.pins["engine"]
        self.release = dict(
            id=engine["release_id"],
            tag_name=engine["tag"],
            draft=False,
            prerelease=False,
            published_at=engine["published_at"],
            target_commitish=engine["target_commitish"],
            assets=[
                dict(
                    id=a["id"],
                    name=a["name"],
                    size=a["bytes"],
                    digest="sha256:" + a["sha256"],
                )
                for a in engine["assets"]
            ],
        )
        self.commit = engine["source_commit"]
        self.notice = (self.package / "LICENSE.md").read_bytes()
        self.bin = Path(self.temp.name) / "bin"
        self.bin.mkdir()
        self.responses = Path(self.temp.name) / "responses.json"
        self.calls = Path(self.temp.name) / "calls.jsonl"
        fake = self.bin / "gh"
        fake.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
assert not any(k in os.environ for k in ('GH_DEBUG','DEBUG','GH_HOST','GH_REPO','GH_FORCE_TTY'))
assert os.environ['GH_PROMPT_DISABLED'] == '1'
with open(os.environ['CALLS'], 'a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')
data = json.loads(Path(os.environ['RESPONSES']).read_text())
if sys.argv[1:] == ['auth','status','--active','--hostname','github.com']:
    if data.get('auth_failure'): print('SECRET https://signed.invalid', file=sys.stderr); sys.exit(1)
    sys.exit(0)
assert sys.argv[1:4] == ['api','--hostname','github.com']
endpoint = sys.argv[4]
if data.get('api_failure') == endpoint: print('SECRET https://signed.invalid', file=sys.stderr); sys.exit(1)
if endpoint not in data: print('SECRET https://signed.invalid', file=sys.stderr); sys.exit(1)
print(json.dumps(data[endpoint]))
""")
        fake.chmod(0o755)
        for name in ("curl", "wget", "download-gh-asset"):
            sentinel = self.bin / name
            sentinel.write_text("#!/bin/sh\nexit 99\n")
            sentinel.chmod(0o755)
        self.env = dict(
            os.environ,
            PATH=str(self.bin) + ":" + os.environ["PATH"],
            CALLS=str(self.calls),
            RESPONSES=str(self.responses),
            GH_DEBUG="api",
            DEBUG="1",
            GH_HOST="invalid",
            GH_REPO="invalid",
            GH_FORCE_TTY="1",
        )
        self.extra = {}

    def write_responses(self):
        data = {
            updater.API + "/releases/latest": self.release,
            updater.API + "/commits/" + self.release["tag_name"]: {"sha": self.commit},
            updater.API + "/contents/LICENSE.md?ref=" + self.commit: dict(
                type="file",
                path="LICENSE.md",
                encoding="base64",
                size=len(self.notice),
                sha=hashlib.sha1(
                    f"blob {len(self.notice)}\0".encode() + self.notice
                ).hexdigest(),
                content=base64.b64encode(self.notice).decode(),
            ),
        }
        data.update(self.extra)
        self.responses.write_text(json.dumps(data))

    def cli(self, *args, ok=True):
        self.write_responses()
        result = subprocess.run(
            ["python3", str(self.root / "scripts/update-engine-release"), *args],
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        if not ok:
            self.assertEqual(result.stdout, "")
            self.assertNotIn("SECRET", result.stderr)
            self.assertNotIn("https://", result.stderr)
        return result

    def snapshot(self):
        return {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }

    def new_release(self):
        self.release["tag_name"] = "5.7.2-css-90"
        self.release["id"] += 1
        self.commit = "a" * 40
        self.notice = b"Updated upstream license notice.\n"
        self.release["assets"] = [
            dict(
                id=900 + i,
                name=f"UnrealEngine-CSS-Editor-Linux.tar.zst.{i:02}",
                size=20 + i,
                digest="sha256:" + str(i) * 64,
            )
            for i in range(3)
        ]
        self.release["assets"].reverse()
        self.release["assets"].append(
            dict(name="UnrealEngine-CSS-Editor-Linux-Debug.tar.zst.00")
        )

    def test_check_and_stable_noop_preserve_all_bytes_and_pkgrel(self):
        before = self.snapshot()
        for args in (("--check", "--json"), ("--json",)):
            result = json.loads(self.cli(*args).stdout)
            self.assertEqual(
                result,
                dict(
                    status="unchanged",
                    changed=False,
                    tag="5.6.1-css-83",
                    pkgver="5.6.1.css83",
                    pkgrel=4,
                ),
            )
            self.assertEqual(before, self.snapshot())

    def test_new_tag_count_numeric_order_license_and_retry(self):
        self.new_release()
        before = self.snapshot()
        preview = json.loads(self.cli("--check", "--json").stdout)
        self.assertEqual(preview["status"], "update-available")
        self.assertEqual(before, self.snapshot())
        result = json.loads(self.cli("--json").stdout)
        self.assertEqual(
            result,
            dict(
                status="updated",
                changed=True,
                tag="5.7.2-css-90",
                pkgver="5.7.2.css90",
                pkgrel=1,
            ),
        )
        manifest = json.loads((self.root / "upstream-inputs.json").read_text())
        self.assertEqual(manifest["msvc_wine"], self.pins["msvc_wine"])
        self.assertEqual(manifest["guide"], self.pins["guide"])
        self.assertEqual(manifest["engine"]["source_commit"], self.commit)
        self.assertEqual(
            [a["id"] for a in manifest["engine"]["assets"]], [900, 901, 902]
        )
        self.assertEqual((self.package / "LICENSE.md").read_bytes(), self.notice)
        recipe = (self.package / "PKGBUILD").read_text()
        old = before["packages/unreal-engine-css-bin/PKGBUILD"].decode()
        self.assertEqual(
            recipe[recipe.index("# makepkg splits") :],
            old[old.index("# makepkg splits") :],
        )
        self.assertTrue(recipe.endswith("}\n"))
        metadata = (self.package / ".SRCINFO").read_text()
        self.assertIn(
            "UnrealEngine-CSS-5.7.2-css-90-Editor-Linux.tar.zst.02::ghasset://",
            metadata,
        )
        after = self.snapshot()
        self.assertEqual(json.loads(self.cli("--json").stdout)["status"], "unchanged")
        self.assertEqual(after, self.snapshot())
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertTrue(
            all(c[0] == "auth" or c[3].startswith(updater.API + "/") for c in calls)
        )
        self.assertFalse(any("/releases/assets/" in " ".join(c) for c in calls))

    def test_same_tag_metadata_change_bumps_once(self):
        self.release["assets"][0]["digest"] = "sha256:" + "f" * 64
        self.assertEqual(json.loads(self.cli("--json").stdout)["pkgrel"], 5)
        after = self.snapshot()
        self.assertEqual(json.loads(self.cli("--json").stdout)["pkgrel"], 5)
        self.assertEqual(after, self.snapshot())

    def test_reject_bad_release_metadata_without_edits(self):
        good = copy.deepcopy(self.release)
        cases = [
            lambda r: r.update(prerelease=True),
            lambda r: r.update(draft=True),
            lambda r: r.update(tag_name="5.7-preview;touch injected"),
            lambda r: r.update(assets=[]),
            lambda r: r["assets"].pop(0),
            lambda r: r["assets"].pop(1),
            lambda r: r["assets"].append(
                dict(r["assets"][0], name="UnrealEngine-CSS-Editor-Linux.tar.zst.0")
            ),
        ]
        for field, value in (
            ("id", 0),
            ("size", 0),
            ("digest", None),
            ("digest", "md5:" + "a" * 32),
            ("digest", "sha256:bad"),
        ):
            cases.append(lambda r, f=field, v=value: r["assets"][0].update({f: v}))
        before = self.snapshot()
        for case in cases:
            with self.subTest(case=case):
                self.release = copy.deepcopy(good)
                case(self.release)
                self.cli("--json", ok=False)
                self.assertEqual(before, self.snapshot())

    def test_numeric_order_and_exact_unpadded_suffixes(self):
        self.new_release()
        self.release["assets"] = [
            dict(
                id=900 + i,
                name=f"UnrealEngine-CSS-Editor-Linux.tar.zst.{i}",
                size=20,
                digest="sha256:" + "a" * 64,
            )
            for i in range(11)
        ]
        self.release["assets"].reverse()
        self.cli("--json")
        manifest = json.loads((self.root / "upstream-inputs.json").read_text())
        self.assertEqual(
            [a["id"] for a in manifest["engine"]["assets"]], list(range(900, 911))
        )
        info = (self.package / ".SRCINFO").read_text()
        aliases = [
            line.strip().split(" = ", 1)[1]
            for line in info.splitlines()
            if "noextract = " in line
        ]
        self.assertEqual(
            [a.rsplit(".", 1)[1] for a in aliases], [str(i) for i in range(11)]
        )
        self.assertEqual(json.loads(self.cli("--json").stdout)["status"], "unchanged")

    def test_auth_api_and_metadata_failure_preserve_bytes(self):
        before = self.snapshot()
        self.extra = {"auth_failure": True}
        self.cli("--json", ok=False)
        self.extra = {"api_failure": updater.API + "/releases/latest"}
        self.cli("--json", ok=False)
        self.extra = {updater.API + "/releases/latest": {}}
        self.cli("--json", ok=False)
        self.extra = {updater.API + "/releases/latest": []}
        self.cli("--json", ok=False)
        self.extra = {}
        self.new_release()
        fake = self.bin / "makepkg"
        fake.write_text("#!/bin/sh\nexit 1\n")
        fake.chmod(0o755)
        self.cli("--json", ok=False)
        fake.write_text("#!/bin/sh\nprintf 'pkgver = wrong\\n'\n")
        self.cli("--json", ok=False)
        self.assertEqual(before, self.snapshot())

    def test_notice_validation_and_patch_change_fail_closed(self):
        endpoint = updater.API + "/contents/LICENSE.md?ref=" + self.commit
        for change in (
            {"type": "dir"},
            {"size": 0},
            {"size": 1048577},
            {"content": "!!"},
            {"sha": "a" * 40},
            {"encoding": "none"},
        ):
            self.write_responses()
            notice = json.loads(self.responses.read_text())[endpoint]
            notice.update(change)
            self.extra = {endpoint: notice}
            before = self.snapshot()
            self.cli("--json", ok=False)
            self.assertEqual(before, self.snapshot())
            self.extra = {}
        (self.package / "setup-dotnet-permissions.patch").write_text(
            "local modification"
        )
        before = self.snapshot()
        self.cli("--json", ok=False)
        self.assertEqual(before, self.snapshot())

    def test_help_requires_no_tools_and_root_is_rejected(self):
        with patch.object(updater.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(ValueError, "non-root"):
                updater.update(False)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            env={"PATH": ""},
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--check", result.stdout)
        self.assertFalse(self.calls.exists())

    def test_unrelated_recipe_sections_preserved_and_extra_sources_rejected(self):
        self.new_release()
        path = self.package / "PKGBUILD"
        text = path.read_text().replace(
            "depends=('glibc'", "depends=('local-extra' 'glibc'"
        )
        text = text.rstrip() + "\n\n# local recipe comment\n"
        path.write_text(text)
        self.cli("--json")
        updated = path.read_text()
        self.assertIn("depends=('local-extra' 'glibc'", updated)
        self.assertTrue(updated.endswith("\n\n# local recipe comment\n"))
        path.write_text(
            updated.replace("  'LICENSE.md'", "  'local-source'\n  'LICENSE.md'")
        )
        before = self.snapshot()
        self.cli("--json", ok=False)
        self.assertEqual(before, self.snapshot())

    def test_publish_rolls_back_on_replace_failure(self):
        first = self.package / "LICENSE.md"
        second = self.package / "PKGBUILD"
        before = self.snapshot()
        original = os.replace
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("fixture write failure")
            return original(source, destination)

        with patch.object(updater.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                updater.publish({first: b"new notice", second: b"new recipe"})
        self.assertEqual(before, self.snapshot())

    def test_mutation_requires_user_owned_regular_pin_files(self):
        with (
            patch.object(updater, "ROOT", self.root),
            patch.object(updater.os, "geteuid", return_value=os.geteuid() + 1),
        ):
            with self.assertRaisesRegex(ValueError, "user-owned"):
                updater.update(False)
        notice = self.package / "LICENSE.md"
        external = Path(self.temp.name) / "external-notice"
        notice.rename(external)
        notice.symlink_to(external)
        before = self.snapshot()
        self.cli("--json", ok=False)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
