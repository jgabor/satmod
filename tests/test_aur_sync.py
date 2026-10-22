"""aur-sync against local bare repositories. No network or AUR access."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")
SATMOD = ["LICENSE", "PKGBUILD", ".SRCINFO", "satmod", "satmod.install"]
ENGINE = [".SRCINFO", "LICENSE", "LICENSE.md", "PKGBUILD", "REUSE.toml", "download-gh-asset",
          "prefetch-engine-sources", "setup-dotnet-permissions.patch",
          "unreal-engine-css-bin.install"]


class AurSyncTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="aur-sync-fixture-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.com",
                        GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.com",
                        AUR_REMOTE=str(self.base / "aur") + "/")
        self.repo = self.base / "repo"
        tracked = subprocess.run([GIT, "ls-files", "packages", "scripts/aur-sync"], cwd=ROOT,
                                 check=True, capture_output=True, text=True).stdout.split()
        for path in set(tracked) | {"scripts/aur-sync", "packages/unreal-engine-css-bin/LICENSE",
                                     "packages/unreal-engine-css-bin/REUSE.toml"}:
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, self.repo / path)
        self.git("init", "--quiet", "--initial-branch=main")
        # The repository's identity, not the environment's, authors AUR commits.
        self.git("config", "user.name", "Repo Owner")
        self.git("config", "user.email", "owner@example.com")
        for key in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            del self.env[key]
        self.commit("Fixture")
        for name in ("satmod", "unreal-engine-css-bin"):
            self.git("init", "--quiet", "--bare", "--initial-branch=master",
                     str(self.base / "aur" / f"{name}.git"), cwd=self.base)

    def git(self, *args, cwd=None):
        return subprocess.run([GIT, *args], cwd=cwd or self.repo, env=self.env, check=True,
                              capture_output=True, text=True).stdout

    def commit(self, message):
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", message)

    def sync(self, *args):
        result = subprocess.run(["python3", str(self.repo / "scripts/aur-sync"), *args, "--json"],
                                env=self.env, capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout), result.stderr

    def srcinfo(self, name, key):
        text = (self.repo / "packages" / name / ".SRCINFO").read_text()
        return next(line.split(" = ", 1)[1] for line in text.splitlines()
                    if line.strip().startswith(key + " = "))

    def checkout(self, name):
        return self.repo / ".cache/aur" / name

    def remote_log(self, name):
        return self.git("--git-dir", str(self.base / "aur" / f"{name}.git"), "log",
                        "--format=%s", "master", cwd=self.base).splitlines()

    def test_first_import_rerun_and_push(self):
        code, result, error = self.sync("satmod", "unreal-engine-css-bin")
        self.assertEqual(code, 0, error)
        satmod, engine = result["packages"]
        version = self.srcinfo("satmod", "pkgver") + "-" + self.srcinfo("satmod", "pkgrel")
        self.assertEqual(satmod["version"], version)
        self.assertTrue(satmod["committed"] and engine["committed"])
        self.assertFalse(satmod["pushed"])
        self.assertEqual(satmod["unpushed"], 1)
        for name, expected in (("satmod", SATMOD), ("unreal-engine-css-bin", ENGINE)):
            work = self.checkout(name)
            self.assertEqual(sorted(self.git("ls-files", cwd=work).split()), sorted(expected))
            self.assertEqual(self.git("log", "--format=%s", cwd=work).splitlines(),
                             ["Initial import " + (satmod if name == "satmod" else engine)["version"]])
            self.assertEqual(self.git("branch", "--show-current", cwd=work).strip(), "master")
            self.assertEqual(self.git("log", "--format=%an <%ae>|%cn <%ce>", cwd=work).strip(),
                             "Repo Owner <owner@example.com>|Repo Owner <owner@example.com>")
            for path in expected:
                self.assertEqual((work / path).read_bytes(),
                                 (self.repo / "packages" / name / path).read_bytes())
            # Nothing reaches the AUR without --push.
            with self.assertRaises(subprocess.CalledProcessError):
                self.remote_log(name)
        # Modes carry over; the engine's helpers must stay executable.
        self.assertTrue(os.access(self.checkout("unreal-engine-css-bin") / "prefetch-engine-sources",
                                  os.X_OK))
        code, result, error = self.sync("satmod")
        self.assertEqual(code, 0, error)
        self.assertFalse(result["packages"][0]["committed"])
        self.assertEqual(result["packages"][0]["unpushed"], 1)
        code, result, error = self.sync("satmod", "--push")
        self.assertEqual(code, 0, error)
        self.assertTrue(result["packages"][0]["pushed"])
        self.assertEqual(self.remote_log("satmod"), ["Initial import " + version])

    def test_update_commits_changes_and_drops_removed_files(self):
        (self.repo / "packages/satmod/notes.txt").write_text("extra\n")
        self.commit("Extra file")
        self.assertEqual(self.sync("satmod", "--push")[0], 0)
        self.assertIn("notes.txt", self.git("ls-files", cwd=self.checkout("satmod")))
        recipe = self.repo / "packages/satmod"
        pkgbuild = recipe / "PKGBUILD"
        pkgver = self.srcinfo("satmod", "pkgver")
        pkgbuild.write_text(pkgbuild.read_text().replace("pkgrel=1\n", "pkgrel=2\n"))
        (recipe / ".SRCINFO").write_text(subprocess.run(
            ["makepkg", "--printsrcinfo"], cwd=recipe, check=True, capture_output=True,
            text=True).stdout)
        self.git("rm", "--quiet", "packages/satmod/notes.txt")
        self.commit("Bump")
        # Leftovers from a local build in the checkout are cleaned away.
        (self.checkout("satmod") / "src").mkdir()
        code, result, error = self.sync("satmod", "--push")
        self.assertEqual(code, 0, error)
        self.assertEqual(result["packages"][0]["version"], pkgver + "-2")
        self.assertNotIn("notes.txt", self.git("ls-files", cwd=self.checkout("satmod")))
        self.assertFalse((self.checkout("satmod") / "src").exists())
        self.assertEqual(self.remote_log("satmod"), [f"Update to {pkgver}-2", f"Initial import {pkgver}-1"])

    def test_refuses_dirty_or_stale_recipes_before_cloning(self):
        pkgbuild = self.repo / "packages/satmod/PKGBUILD"
        original = pkgbuild.read_text()
        pkgbuild.write_text(original + "# edit\n")
        code, result, error = self.sync("satmod")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "error")
        self.assertIn("uncommitted changes", error)
        pkgbuild.write_text(original.replace("pkgrel=1\n", "pkgrel=9\n"))
        self.commit("Stale")
        code, result, error = self.sync("satmod")
        self.assertEqual(code, 1)
        self.assertIn(".SRCINFO is stale", error)
        self.assertFalse(self.checkout("satmod").exists())

    def test_unknown_package_is_rejected(self):
        result = subprocess.run(["python3", str(self.repo / "scripts/aur-sync"), "other"],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
