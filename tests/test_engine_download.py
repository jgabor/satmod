#!/usr/bin/env python3
"""Isolated CLI contract tests, with no network or large engine downloads."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HELPER = (
    Path(__file__).resolve().parents[1]
    / "packages/unreal-engine-css-bin/download-gh-asset"
)
URL = "ghasset://satisfactorymodding/UnrealEngine/5.6.1-css-83/436454982"
PAYLOAD = b"engine fixture\x00\xff\n"
MOCK = r"""
import hashlib
import os
from pathlib import Path
import sys

args = sys.argv[1:]
scenario = os.environ["SCENARIO"]
assert not any(k in os.environ for k in ("GH_DEBUG", "DEBUG", "GH_HOST", "GH_REPO", "GH_FORCE_TTY"))
assert os.environ["GH_PROMPT_DISABLED"] == "1"
assert os.environ["GH_TOKEN"] == "fixture-token-secret"
assert "--hostname" in args and args[args.index("--hostname") + 1] == "github.com"
with open(os.environ["CALLS"], "a") as calls:
    calls.write(repr(args) + "\n")

def error():
    # Real gh errors/debug output can include signed redirects. None may escape.
    print("fixture-token-secret Authorization: bearer hidden https://signed.invalid/?secret=value", file=sys.stderr)
    sys.exit(1)

repo = "repos/satisfactorymodding/UnrealEngine"
if args[:2] == ["auth", "status"]:
    assert "--active" in args
    if scenario == "auth":
        error()
elif repo in args:
    assert "--silent" in args
    if scenario == "repo":
        error()
elif repo + "/releases/tags/5.6.1-css-83" in args:
    query = args[args.index("--jq") + 1]
    assert '.assets[]' in query and '436454982' in query and '.digest' in query
    if scenario == "release":
        error()
    if scenario != "missing":
        payload = b"engine fixture\x00\xff\n"
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        if scenario == "no-digest":
            digest = "-"
        elif scenario == "bad-metadata":
            digest = "sha512:not-supported"
        elif scenario == "uppercase":
            digest = "sha256:" + hashlib.sha256(payload).hexdigest().upper()
        print(str(len(payload)) + "\t" + digest)
elif repo + "/releases/assets/436454982" in args:
    assert args[args.index("--header") + 1] == "Accept: application/octet-stream"
    output = Path(os.environ["OUTPUT"])
    if scenario in ("fresh", "fresh-failure"):
        assert not output.exists()
    else:
        assert output.read_bytes() == b"previous output"
    temps = list(output.parent.glob(".ghasset.*"))
    assert len(temps) == 2  # Includes an unrelated sentinel directory.
    payload = b"engine fixture\x00\xff\n"
    if scenario in ("transfer", "truncated", "fresh-failure"):
        payload = payload[:3]
    elif scenario == "corrupt":
        payload = b"X" + payload[1:]
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()
    if scenario in ("transfer", "fresh-failure"):
        error()
    if scenario == "interrupted":
        import signal
        os.kill(os.getppid(), signal.SIGTERM)
else:
    raise AssertionError(args)
"""


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engine-download-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(f"#!{sys.executable}\n" + MOCK)
        gh.chmod(0o755)
        self.output = self.root / "output with spaces" / "engine part.00"
        self.output.parent.mkdir()
        self.output.write_bytes(b"previous output")
        self.sentinel = self.output.parent / ".ghasset.unrelated"
        self.sentinel.mkdir()
        (self.sentinel / "asset").write_bytes(b"not owned")
        self.calls = self.root / "calls"
        self.env = dict(
            os.environ,
            PATH=f"{self.bin}:{os.environ['PATH']}",
            GH_DEBUG="api",
            DEBUG="1",
            GH_HOST="hostile.invalid",
            GH_REPO="other/repo",
            GH_FORCE_TTY="80",
            GH_TOKEN="fixture-token-secret",
            CALLS=str(self.calls),
            OUTPUT=str(self.output),
        )
        # Shell startup files must not replace the isolated fixture PATH.
        self.env.pop("BASH_ENV", None)
        self.env.pop("ENV", None)

    def run_helper(self, scenario="success", url=URL, output=None):
        result = subprocess.run(
            [str(HELPER), url, str(output or self.output)],
            env=dict(self.env, SCENARIO=scenario),
            capture_output=True,
            timeout=10,
        )
        logs = result.stdout + result.stderr
        for secret in (
            b"fixture-token-secret",
            b"Authorization",
            b"signed.invalid",
            b"secret=value",
        ):
            self.assertNotIn(secret, logs)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(list(self.output.parent.glob(".ghasset.*")), [self.sentinel])
        self.assertEqual((self.sentinel / "asset").read_bytes(), b"not owned")
        return result

    def test_success_and_optional_digest(self):
        for scenario in ("success", "no-digest", "uppercase"):
            with self.subTest(scenario=scenario):
                self.output.write_bytes(b"previous output")
                result = self.run_helper(scenario)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.output.read_bytes(), PAYLOAD)

    def test_failures_preserve_output(self):
        cases = {
            "auth": b"authentication",
            "repo": b"repository access",
            "release": b"requested release",
            "missing": b"does not belong",
            "transfer": b"transfer failed",
            "truncated": b"byte count mismatch",
            "corrupt": b"SHA256 mismatch",
            "bad-metadata": b"metadata",
        }
        for scenario, message in cases.items():
            with self.subTest(scenario=scenario):
                result = self.run_helper(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertEqual(self.output.read_bytes(), b"previous output")

    def test_hostile_urls_fail_before_gh(self):
        for url in (
            URL.replace("satisfactorymodding", "attacker"),
            URL.replace("ghasset://", "https://"),
            URL.replace("5.6.1-css-83", ".."),
            URL.replace("5.6.1-css-83", "{owner}"),
            URL.replace("5.6.1-css-83", "%2e%2e"),
            URL.replace("satisfactorymodding", "token@satisfactorymodding"),
            URL + "?token=fixture-token-secret",
            URL + "/extra",
            URL.replace("436454982", "-1"),
            URL + "\n",
        ):
            with self.subTest(url=url):
                result = self.run_helper(url=url)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.calls.exists())
                self.assertEqual(self.output.read_bytes(), b"previous output")

    def test_interrupted_transfer_preserves_output(self):
        result = self.run_helper("interrupted")
        self.assertEqual(result.returncode, 143)
        self.assertEqual(self.output.read_bytes(), b"previous output")

    def test_new_output_success_and_failure(self):
        self.output.unlink()
        result = self.run_helper("fresh-failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        result = self.run_helper("fresh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), PAYLOAD)

    def test_usage(self):
        result = subprocess.run(
            [str(HELPER)], env=self.env, capture_output=True, timeout=10
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"Usage: download-gh-asset URL OUTPUT", result.stderr)
        self.assertFalse(self.calls.exists())

    def test_bad_output_fails_before_gh(self):
        for output in (self.output.parent, self.root / "absent" / "asset"):
            with self.subTest(output=output):
                result = self.run_helper(output=output)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.calls.exists())

    def test_relative_output(self):
        # A relative path beginning with '-' must not become a tool option.
        relative = "-engine part.00"
        target = self.root / relative
        target.write_bytes(b"previous output")
        sentinel = self.root / ".ghasset.unrelated"
        sentinel.mkdir()
        result = subprocess.run(
            [str(HELPER), URL, relative],
            cwd=self.root,
            env=dict(self.env, SCENARIO="success", OUTPUT=str(target)),
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_bytes(), PAYLOAD)
        self.assertEqual(list(self.root.glob(".ghasset.*")), [sentinel])


if __name__ == "__main__":
    unittest.main()
