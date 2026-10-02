"""Tiny trusted recipe/helper fixtures; no network or real engine assets."""

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RECIPE = Path(__file__).resolve().parents[1] / "packages/unreal-engine-css-bin"
URLS = [f"ghasset://satisfactorymodding/UnrealEngine/fixture/{i + 1}" for i in range(4)]
ALIASES = [f"part ü引擎 {i:02}" for i in range(4)]
HELPER = r"""
import fcntl
import json
import os
from pathlib import Path
import sys
import time

url, output = sys.argv[1:]
def event(kind):
    with open(os.environ["EVENTS"], "a+") as log:
        fcntl.flock(log, fcntl.LOCK_EX)
        log.write(json.dumps([kind, url, output]) + "\n")
        log.flush()

event("start")
if os.environ.get("OVERLAP"):
    deadline = time.monotonic() + 5
    while True:
        with open(os.environ["EVENTS"]) as log:
            starts = sum(json.loads(line)[0] == "start" for line in log)
        if starts >= 2:
            break
        if time.monotonic() > deadline:
            event("timeout")
            sys.exit(1)
        time.sleep(0.01)
time.sleep(0.02 if url == os.environ.get("FAIL_URL") else 0.15)
failed = os.environ.get("FAIL_ALL") or url == os.environ.get("FAIL_URL")
if not failed:
    Path(output).write_bytes(url.encode())
event("end")
sys.exit(1 if failed else 0)
"""


class EnginePrefetchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engine-prefetch-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.recipe = self.root / "recipe with spaces ü引擎"
        self.recipe.mkdir()
        self.cache = self.root / "source cache ü引擎"
        self.cache.mkdir()
        self.script = self.recipe / "prefetch-engine-sources"
        shutil.copy2(RECIPE / self.script.name, self.script)
        helper = self.recipe / "download-gh-asset"
        helper.write_text(f"#!{sys.executable}\n" + HELPER)
        helper.chmod(0o755)
        sources = [f"{alias}::{url}" for alias, url in zip(ALIASES, URLS)]
        sources += ["LICENSE.md", "setup-dotnet-permissions.patch"]
        hashes = [hashlib.sha256(url.encode()).hexdigest() for url in URLS]
        for name in sources[4:]:
            (self.recipe / name).write_bytes(b"fixture")
            hashes.append(hashlib.sha256(b"fixture").hexdigest())
        self.metadata = (
            "pkgname=engine-prefetch-fixture\npkgver=1\npkgrel=1\n"
            "pkgdesc='tiny fixture'\narch=('any')\nlicense=('MIT')\n"
            f"source=({' '.join(map(shlex.quote, sources))})\n"
            f"noextract=({' '.join(map(shlex.quote, ALIASES))})\n"
            f"sha256sums=({' '.join(hashes)})\n"
            "package() { echo package-called >&2; return 99; }\n"
        )
        (self.recipe / "PKGBUILD").write_text(self.metadata)
        self.events_path = self.root / "events"
        self.env = dict(
            os.environ, EVENTS=str(self.events_path), PYTHONDONTWRITEBYTECODE="1"
        )
        self.guard = self.root / "forbidden commands"
        self.guard.mkdir()
        for name in ("gh", "curl", "wget", "sudo", "pacman", "makepkg"):
            sentinel = self.guard / name
            sentinel.write_text(
                '#!/bin/bash\nprintf forbidden-command >> "$EVENTS"\nexit 99\n'
            )
            sentinel.chmod(0o755)

    def run_prefetch(self, *args, **env):
        return subprocess.run(
            [str(self.script), *map(str, args)],
            cwd=self.root,
            env=dict(self.env, PATH=str(self.guard) + ":" + self.env["PATH"], **env),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def events(self):
        if not self.events_path.exists():
            return []
        return [json.loads(line) for line in self.events_path.read_text().splitlines()]

    def fill_cache(self, cache=None):
        for alias, url in zip(ALIASES, URLS):
            ((cache or self.cache) / alias).write_bytes(url.encode())

    def test_two_workers_overlap_and_exact_url_output_pairs(self):
        result = self.run_prefetch(self.cache, OVERLAP="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.events()
        self.assertCountEqual(
            [event[1:] for event in events if event[0] == "start"],
            [[url, str(self.cache / alias)] for alias, url in zip(ALIASES, URLS)],
        )
        active = peak = 0
        for kind, _, _ in events:
            self.assertIn(kind, ("start", "end"))
            active += 1 if kind == "start" else -1
            peak = max(peak, active)
            self.assertLessEqual(active, 2)
        self.assertEqual((peak, active), (2, 0))
        for alias, url in zip(ALIASES, URLS):
            self.assertEqual((self.cache / alias).read_bytes(), url.encode())

    def test_single_uncached_part(self):
        self.fill_cache()
        (self.cache / ALIASES[2]).unlink()
        result = self.run_prefetch(self.cache)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.events(),
            [
                [kind, URLS[2], str(self.cache / ALIASES[2])]
                for kind in ("start", "end")
            ],
        )

    def test_cached_files_and_valid_broken_aliases_are_untouched_offline(self):
        target = self.root / "original part"
        target.write_bytes(b"original")
        entries = [self.cache / alias for alias in ALIASES]
        entries[0].write_bytes(b"corrupt cached bytes")
        entries[1].symlink_to(target)
        entries[2].symlink_to(self.root / "missing target")
        entries[3].write_bytes(b"cached")
        before = [path.lstat() for path in entries]
        result = self.run_prefetch(self.cache, FAIL_ALL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), [])
        self.assertEqual([path.lstat() for path in entries], before)
        self.assertEqual(entries[0].read_bytes(), b"corrupt cached bytes")
        self.assertEqual(target.read_bytes(), b"original")
        self.assertEqual(entries[2].readlink(), self.root / "missing target")

    def test_default_is_adjacent_recipe_not_working_directory(self):
        self.fill_cache(self.recipe)
        result = self.run_prefetch(FAIL_ALL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events(), [])
        self.assertFalse((self.root / ALIASES[0]).exists())

    def test_creates_requested_cache_directory(self):
        cache = self.root / "new cache ü引擎"
        result = self.run_prefetch(cache)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all((cache / alias).is_file() for alias in ALIASES))

    def test_failure_propagates_after_all_workers_finish(self):
        result = self.run_prefetch(self.cache, FAIL_URL=URLS[0])
        self.assertNotEqual(result.returncode, 0)
        events = self.events()
        for kind in ("start", "end"):
            self.assertCountEqual(
                [url for event, url, _ in events if event == kind], URLS
            )
        self.assertFalse((self.cache / ALIASES[0]).exists())
        self.assertTrue(all((self.cache / alias).is_file() for alias in ALIASES[1:]))

    def test_normal_makepkg_verification_still_rejects_corrupt_cached_bytes(self):
        result = self.run_prefetch(self.recipe)
        self.assertEqual(result.returncode, 0, result.stderr)

        def verify():
            return subprocess.run(
                ["makepkg", "--verifysource"],
                cwd=self.recipe,
                env=self.env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

        result = verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.events()
        bad = self.recipe / ALIASES[0]
        bad.write_bytes(b"corrupt")
        result = self.run_prefetch(FAIL_ALL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(bad.read_bytes(), b"corrupt")
        self.assertEqual(self.events(), calls)
        result = verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout + result.stderr)
        self.assertNotIn("package-called", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
