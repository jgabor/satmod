"""Isolated bootstrap fixtures. No installed package, network, or sudo calls."""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import grp
import pwd
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ENGINE = "unreal-engine-css-bin"
SETUP = "satisfactory-modding"

STUB = r"""
import json, os, pathlib, subprocess, sys
args = sys.argv[1:]
tool = pathlib.Path(sys.argv[0]).name
root = pathlib.Path(os.environ["FIXTURE_ROOT"])
name = pathlib.Path.cwd().name
kind = "engine" if name == "unreal-engine-css-bin" else "setup"
event = "gpasswd" if tool == "sudo" and args[:1] == ["gpasswd"] else tool
effective = None
if tool == "makepkg":
    assert args[0] == "--config"
    values = subprocess.check_output(
        ["/usr/bin/bash", "-c", 'source /usr/share/makepkg/util/config.sh; load_makepkg_config "$1"; printf "%s\\n" "${PACMAN_AUTH[*]}" '
         '"${COMPRESSZST[*]}" "$SRCDEST" "$PKGDEST" "$BUILDDIR" "$LOGDEST" "$TMPDIR"',
         "fixture", args[1]], text=True, stdin=subprocess.DEVNULL).splitlines()
    effective = dict(zip(("auth", "compression", "SRCDEST", "PKGDEST", "BUILDDIR", "LOGDEST", "TMPDIR"), values))
    assert effective["auth"] == "sudo", effective
    for key in ("SRCDEST", "PKGDEST", "BUILDDIR", "LOGDEST", "TMPDIR"):
        assert effective[key] == os.environ[key], effective
    event = ("metadata-" if "--printsrcinfo" in args else
             "list-" if "--packagelist" in args else "build-") + kind
elif tool == "sudo":
    event = "gpasswd" if args[:1] == ["gpasswd"] else (
        "sudo-check" if args == ["-v"] else (
            "install-engine" if "unreal-engine-css-bin" in args[-1] else "install-setup"))
elif tool == "satisfactory-modding":
    event = "sdk"
with (root / "events").open("a") as stream:
    stream.write(json.dumps({"event": event, "args": args, "cwd": str(pathlib.Path.cwd()),
                            "uid": os.geteuid(), "effective": effective, "env": {k: os.environ.get(k) for k in
                            ("SRCDEST", "PKGDEST", "BUILDDIR", "LOGDEST", "TMPDIR",
                             "XDG_DATA_HOME", "XDG_CACHE_HOME")}}) + "\n")
if os.environ.get("FAIL") == event:
    print("fixture failure: " + event, file=sys.stderr)
    print("fixture stdout failure: " + event)
    sys.exit(23)
if tool == "makepkg":
    version = "5.6.1.css83" if kind == "engine" else "1.0.0"
    if kind == "engine" and (root / "updated-release").exists():
        version = "5.6.1.css84"
    dest = pathlib.Path(os.environ["PKGDEST"])
    artifact = dest / (name + "-" + version + "-3-x86_64.pkg.tar.zst")
    if "--printsrcinfo" in args:
        print("pkgbase = " + name + "\n\tpkgver = " + version +
              "\n\tpkgrel = 3\n\tarch = x86_64\npkgname = " + name)
        if os.environ.get("SPLIT_METADATA"):
            print("pkgname = extra")
    elif "--packagelist" in args:
        print(artifact)
        if os.environ.get("MULTIPLE"):
            print(dest / "extra.pkg.tar.zst")
    else:
        assert "--syncdeps" in args and "--noconfirm" in args
        assert not any(a in args for a in ("--nodeps", "--skipinteg", "--force"))
        artifact.write_text("tiny fake package")
        print("build diagnostic")
elif tool == "pacman":
    assert args[0] == "-Qip"
    name = "unreal-engine-css-bin" if "unreal-engine-css-bin" in args[1] else "satisfactory-modding"
    version = "5.6.1.css83-3" if name == "unreal-engine-css-bin" else "1.0.0-3"
    print("Name : " + ("wrong" if os.environ.get("BAD_NAME") else name))
    print("Version : " + ("0-1" if os.environ.get("BAD_VERSION") else version))
    print("Architecture : " + ("aarch64" if os.environ.get("BAD_ARCH") else "x86_64"))
elif tool == "sudo" and event.startswith("install-"):
    assert args[:4] == ["pacman", "-U", "--needed", "--noconfirm"]
    if event == "install-setup":
        sdk = root / "bin/satisfactory-modding"
        sdk.write_bytes((root / "bin/makepkg").read_bytes())
        sdk.chmod(0o755)
elif tool == "sudo" and args[:2] == ["gpasswd", "-a"]:
    assert args == ["gpasswd", "-a", "fixture", "unreal-engine-css"]
    event = "gpasswd"
elif tool == "satisfactory-modding":
    assert args == ["setup", "--json"]
    print(os.environ.get("SDK_JSON", '{"status":"complete","reused":true}'))
else:
    assert tool == "sudo" and args == ["-v"], tool
"""

UPDATER = """import json, os, pathlib, sys
root = pathlib.Path(os.environ["FIXTURE_ROOT"])
assert sys.argv[1:] == ["--json"]
with (root / "events").open("a") as stream:
    stream.write(json.dumps({"event": "update"}) + "\\n")
if os.environ.get("FAIL") == "update":
    print("fixture failure: update", file=sys.stderr)
    sys.exit(23)
print('{"status":"unchanged","changed":false}')
if os.environ.get("UPDATE_RELEASE"):
    (root / "updated-release").write_text("5.6.1-css-84")
"""

AUTH_STUB = r"""
import json, os, pathlib, sys
root = pathlib.Path(os.environ["FIXTURE_ROOT"])
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "events").open("a") as stream:
    stream.write(json.dumps({"event": tool, "args": args}) + "\n")
if tool == "sudo":
    assert "-n" not in args and "-k" not in args, args
    if args == ["-v"]:
        sys.exit(0)
    assert args[0] == str(root / "bin/pacman") and "-S" in args, args
    print("fixture sudo: authentication unavailable", file=sys.stderr)
    sys.exit(23)  # Never execute the requested command.
if tool == "pacman":
    assert args[0] == "-T", args  # No real pacman, even for queries.
    print("bootstrap-fixture-missing-dependency")
    sys.exit(127)
assert tool == "pacman-conf" and args == ["DBPath"], (tool, args)
print(root / "db")
"""


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="bootstrap fixture spaces ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "scripts").mkdir()
        (self.root / "bin").mkdir()
        for name in (ENGINE, SETUP):
            (self.root / "packages" / name).mkdir(parents=True)
        script = self.root / "scripts/bootstrap"
        shutil.copyfile(ROOT / "scripts/bootstrap", script)
        loader = importlib.machinery.SourceFileLoader("bootstrap_fixture", str(script))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        self.cli = importlib.util.module_from_spec(spec)
        loader.exec_module(self.cli)
        (self.root / "scripts/update-engine-release").write_text(UPDATER)
        for tool in ("makepkg", "pacman", "sudo", "gh"):
            path = self.root / "bin" / tool
            path.write_text("#!" + sys.executable + "\n" + STUB)
            path.chmod(0o755)
        (self.root / "bin/python3").symlink_to(sys.executable)
        self.member = True
        self.primary_member = False
        self.session_member = True
        self.env = dict(
            os.environ,
            PATH=str(self.root / "bin"),
            FIXTURE_ROOT=str(self.root),
            XDG_DATA_HOME=str(self.root / "user data"),
            XDG_CACHE_HOME=str(self.root / "user cache"),
        )
        # Do not let the caller's fixture controls influence these stubs.
        for key in (
            "FAIL",
            "BAD_NAME",
            "BAD_VERSION",
            "BAD_ARCH",
            "SDK_JSON",
            "MULTIPLE",
            "SPLIT_METADATA",
            "UPDATE_RELEASE",
        ):
            self.env.pop(key, None)

    def invoke(self, *args, uid=1000):
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(self.cli.os, "geteuid", return_value=uid),
            patch.object(self.cli.os, "getuid", return_value=1000),
            patch.object(self.cli.os, "getgid", return_value=2000 if self.primary_member else 1000),
            patch.object(self.cli.os, "getgroups", return_value=(
                [1000, 2000] if self.member and self.session_member else [1000])),
            patch.object(self.cli.pwd, "getpwuid", return_value=pwd.struct_passwd(
                ("fixture", "x", 1000, 2000 if self.primary_member else 1000,
                 "", str(self.root), "/bin/bash"))),
            patch.object(self.cli.grp, "getgrnam", return_value=grp.struct_group(
                ("unreal-engine-css", "x", 2000, ["fixture"] if self.member else []))),
            patch.object(sys, "argv", ["bootstrap", *args]),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            # subprocess diagnostics require a real fd, unlike StringIO.
            original = self.cli.subprocess.run

            def capture(*a, **kw):
                self.assertEqual(kw.get("stdin"), self.cli.subprocess.DEVNULL)
                forward = kw.get("stdout") is err
                kw["stderr"] = self.cli.subprocess.PIPE
                if forward:
                    kw["stdout"] = self.cli.subprocess.PIPE
                result = original(*a, **kw)
                err.write(result.stderr or "")
                if forward:
                    err.write(result.stdout or "")
                return result

            with patch.object(self.cli.subprocess, "run", side_effect=capture):
                code = self.cli.main()
        return code, out.getvalue(), err.getvalue()

    def events(self):
        path = self.root / "events"
        return (
            [json.loads(line) for line in path.read_text().splitlines()]
            if path.exists()
            else []
        )

    def cached(self):
        for name, version, dest in (
            (ENGINE, "5.6.1.css83-3", ".cache/engine-recipe/packages"),
            (SETUP, "1.0.0-3", ".cache/upstream/msvc-wine"),
        ):
            directory = self.root / dest
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"{name}-{version}-x86_64.pkg.tar.zst").write_text(
                "fake cached archive"
            )

    def test_build_order_output_and_user_setup(self):
        code, output, diagnostics = self.invoke("--json")
        self.assertEqual(code, 0, diagnostics)
        result = json.loads(output)
        self.assertEqual(result["status"], "complete")
        self.assertFalse(result["relogin_required"])
        self.assertFalse(any(e["event"] == "gpasswd" for e in self.events()))
        self.assertEqual([p["reused"] for p in result["packages"]], [False, False])
        events = self.events()
        self.assertEqual(
            [e["event"] for e in events],
            [
                "sudo-check",
                "update",
                "metadata-engine",
                "list-engine",
                "build-engine",
                "pacman",
                "install-engine",
                "metadata-setup",
                "list-setup",
                "build-setup",
                "pacman",
                "install-setup",
                "sdk",
            ],
        )
        self.assertIn('"status":"unchanged"', diagnostics)
        sdk = events[-1]
        self.assertEqual(sdk["args"], ["setup", "--json"])
        self.assertEqual(sdk["uid"], os.geteuid())
        self.assertEqual(sdk["env"]["XDG_DATA_HOME"], self.env["XDG_DATA_HOME"])
        self.assertEqual(sdk["env"]["XDG_CACHE_HOME"], self.env["XDG_CACHE_HOME"])
        setup_build = next(e for e in events if e["event"] == "build-setup")
        for key in ("SRCDEST", "PKGDEST"):
            self.assertEqual(
                setup_build["env"][key], str(self.root / ".cache/upstream/msvc-wine")
            )
        engine_calls = [
            e
            for e in events
            if e["event"] in ("metadata-engine", "list-engine", "build-engine")
        ]
        self.assertTrue(
            all(
                e["args"][0] == "--config"
                and Path(e["args"][1]).parent.parent
                == self.root / ".cache/engine-recipe"
                and "bootstrap-config-" in e["args"][1]
                for e in engine_calls
            )
        )
        self.assertTrue(all(e["env"] == engine_calls[0]["env"] for e in engine_calls))
        self.assertTrue(
            all(e["args"][1] == engine_calls[0]["args"][1] for e in engine_calls)
        )
        self.assertFalse(Path(engine_calls[0]["args"][1]).exists())

    def test_cached_packages_and_existing_config_preserved(self):
        self.cached()
        config = self.root / ".cache/engine-recipe/makepkg.conf"
        text = "source /etc/makepkg.conf\nCOMPRESSZST=(zstd -c -T2 -3 -)\nPACMAN_AUTH=(sudo -k)\n"
        config.write_text(text)
        fragments = config.with_name(config.name + ".d")
        fragments.mkdir()
        fragment = fragments / "override.conf"
        fragment_text = "PACMAN_AUTH=(sudo -k)\nCOMPRESSZST=(zstd -c -T2 -4 -)\nSRCDEST=/external\nPKGDEST=/external\nBUILDDIR=/external\nLOGDEST=/external\nTMPDIR=/external\n"
        fragment.write_text(fragment_text)
        code, output, diagnostics = self.invoke("--json")
        self.assertEqual(code, 0, diagnostics)
        self.assertTrue(all(p["reused"] for p in json.loads(output)["packages"]))
        self.assertFalse(any(e["event"].startswith("build-") for e in self.events()))
        self.assertEqual(config.read_text(), text)
        self.assertEqual(fragment.read_text(), fragment_text)
        for event in self.events():
            if event["event"] in ("metadata-engine", "list-engine"):
                self.assertEqual(event["effective"]["compression"], "zstd -c -T2 -4 -")
                self.assertEqual(event["effective"]["auth"], "sudo")
        self.assertEqual(
            [e["event"] for e in self.events() if e["event"].startswith("install-")],
            ["install-engine", "install-setup"],
        )

    def test_root_and_missing_tools_have_no_effects(self):
        for root in (True, False):
            with self.subTest(root=root):
                if not root:
                    (self.root / "bin/gh").unlink()
                code, output, diagnostics = self.invoke(
                    "--json", uid=0 if root else 1000
                )
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(output)["status"], "error")
                self.assertIn("ordinary user" if root else "gh", diagnostics)
                self.assertEqual(self.events(), [])
                self.assertFalse((self.root / ".cache").exists())

    @unittest.skipUnless(
        Path("/usr/bin/makepkg").is_file() and os.geteuid() != 0,
        "requires installed Arch makepkg and an ordinary user",
    )
    def test_installed_makepkg_dependency_auth_uses_sudo(self):
        # Use installed makepkg, but never execute real sudo or pacman.
        (self.root / "bin/makepkg").unlink()
        (self.root / "bin/makepkg").symlink_to("/usr/bin/makepkg")
        for tool in ("sudo", "pacman", "pacman-conf"):
            path = self.root / "bin" / tool
            path.write_text("#!" + sys.executable + "\n" + AUTH_STUB)
            path.chmod(0o755)
        self.env.update(
            PATH=str(self.root / "bin") + ":/usr/bin",
            PACMAN="pacman",
            HOME=str(self.root),
            MAKEPKG_LIBRARY="/usr/share/makepkg",
            LC_ALL="C",
        )
        recipe = self.root / "packages" / ENGINE
        (recipe / "PKGBUILD").write_text(
            "pkgname=unreal-engine-css-bin\npkgver=5.6.1.css83\npkgrel=3\n"
            "arch=(x86_64)\ndepends=(bootstrap-fixture-missing-dependency)\n"
            "source=()\nsha256sums=()\npackage() { return 99; }\n"
        )
        for existing in (False, True):
            with self.subTest(existing=existing):
                config = self.root / ".cache/engine-recipe/makepkg.conf"
                if existing:
                    config.write_text(
                        "source /etc/makepkg.conf\nPACMAN_AUTH=(sudo -k)\n"
                        "COMPRESSZST=(zstd -c -T2 -3 -)\n"
                    )
                before = config.read_bytes() if existing else None
                code, output, diagnostics = self.invoke("--json")
                # makepkg reports dependency installation failure as exit 8.
                self.assertEqual(code, 8, diagnostics)
                self.assertEqual(json.loads(output)["status"], "error")
                self.assertIn("fixture sudo: authentication unavailable", diagnostics)
                self.assertIn("sudo can prompt", diagnostics)
                events = self.events()
                sudo = [e for e in events if e["event"] == "sudo"]
                self.assertEqual(len(sudo), 2)
                self.assertEqual(sudo[-1]["args"][0], str(self.root / "bin/pacman"))
                self.assertNotIn("-k", sudo[-1]["args"])
                self.assertIn("-S", sudo[-1]["args"])
                self.assertNotIn("-U", sudo[-1]["args"])
                self.assertEqual(events[-1]["event"], "sudo")
                self.assertFalse(
                    (self.root / "bin/satisfactory-modding").exists()
                )
                self.assertFalse(list(self.root.glob(".cache/**/*.pkg.tar.zst")))
                self.assertFalse(list(config.parent.glob("bootstrap-config-*")))
                if existing:
                    self.assertEqual(config.read_bytes(), before)
                (self.root / "events").unlink()

    def test_failures_propagate_and_stop(self):
        stages = [
            "sudo-check",
            "update",
            "metadata-engine",
            "list-engine",
            "build-engine",
            "pacman",
            "install-engine",
            "metadata-setup",
            "list-setup",
            "build-setup",
            "install-setup",
            "sdk",
        ]
        for stage in stages:
            with self.subTest(stage=stage):
                events = self.root / "events"
                if events.exists():
                    events.unlink()
                # Ensure each iteration exercises the build stage too.
                for package in self.root.glob(".cache/**/*.pkg.tar.zst"):
                    package.unlink()
                self.env["FAIL"] = stage
                code, output, diagnostics = self.invoke("--json")
                self.assertEqual(code, 23, diagnostics)
                self.assertEqual(self.events()[-1]["event"], stage)
                self.assertEqual(json.loads(output)["status"], "error")
                self.assertIn("fixture failure: " + stage, diagnostics)
                if stage != "update":
                    self.assertIn("fixture stdout failure: " + stage, diagnostics)
                if stage.startswith("install-") or stage == "sudo-check":
                    self.assertIn("sudo can prompt", diagnostics)
        self.assertFalse((self.root / ".cache/upstream/engine").exists())

    def test_bad_archive_metadata_not_overwritten_or_installed(self):
        self.cached()
        for key in ("BAD_NAME", "BAD_VERSION", "BAD_ARCH"):
            with self.subTest(key=key):
                self.env[key] = "1"
                code, output, diagnostics = self.invoke("--json")
                self.assertEqual(code, 1)
                self.assertIn("not overwritten", diagnostics)
                self.assertFalse(
                    any(
                        e["event"].startswith(("build-", "install-"))
                        for e in self.events()
                    )
                )
                self.env.pop(key)

    def test_multiple_artifacts_or_packages_rejected(self):
        for key in ("MULTIPLE", "SPLIT_METADATA"):
            with self.subTest(key=key):
                self.env[key] = "1"
                code, output, diagnostics = self.invoke("--json")
                self.assertEqual(code, 1)
                self.assertIn("expected", diagnostics)
                self.assertFalse(
                    any(
                        e["event"].startswith(("build-", "install-"))
                        for e in self.events()
                    )
                )
                self.env.pop(key)

    def test_invalid_sdk_response(self):
        self.cached()
        for response in ("not JSON", '{"status":"error"}', "[]"):
            with self.subTest(response=response):
                self.env["SDK_JSON"] = response
                code, output, diagnostics = self.invoke("--json")
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(output)["status"], "error")
                self.assertIn("setup", diagnostics)

    def test_no_old_raw_source_aliases_created(self):
        raw = (
            self.root
            / ".cache/upstream/engine/UnrealEngine-CSS-Editor-Linux.tar.zst.00"
        )
        raw.parent.mkdir(parents=True)
        raw.write_text("old release, never alias to new release")
        self.env["UPDATE_RELEASE"] = "1"
        self.env["FAIL"] = "build-engine"
        code, output, diagnostics = self.invoke("--json")
        self.assertEqual(code, 23, diagnostics)
        self.assertTrue((self.root / "updated-release").exists())
        self.assertEqual(
            list((self.root / ".cache/engine-recipe/sources").iterdir()), []
        )
        self.assertEqual(raw.read_text(), "old release, never alias to new release")

    def test_non_member_added_once_after_engine_install(self):
        self.member = False
        code, output, diagnostics = self.invoke("--json")
        self.assertEqual(code, 0, diagnostics)
        self.assertTrue(json.loads(output)["relogin_required"])
        events = [e["event"] for e in self.events()]
        self.assertEqual(events.count("gpasswd"), 1)
        self.assertEqual(events[events.index("install-engine") + 1], "gpasswd")

    def test_primary_group_member_needs_no_gpasswd(self):
        self.member = False
        self.primary_member = True
        code, output, diagnostics = self.invoke("--json")
        self.assertEqual(code, 0, diagnostics)
        self.assertFalse(json.loads(output)["relogin_required"])
        self.assertNotIn("gpasswd", [e["event"] for e in self.events()])

    def test_member_without_new_login_is_told_to_relogin(self):
        self.session_member = False
        code, output, diagnostics = self.invoke("--json")
        self.assertEqual(code, 0, diagnostics)
        self.assertTrue(json.loads(output)["relogin_required"])
        self.assertNotIn("gpasswd", [e["event"] for e in self.events()])

    def test_membership_failure_stops_bootstrap(self):
        self.member = False
        self.env["FAIL"] = "gpasswd"
        code, output, diagnostics = self.invoke("--json")
        self.assertEqual(code, 23, diagnostics)
        self.assertEqual(json.loads(output)["status"], "error")
        self.assertNotIn("install-setup", [e["event"] for e in self.events()])

    def test_non_member_human_output_requests_relogin(self):
        self.member = False
        code, output, diagnostics = self.invoke()
        self.assertEqual(code, 0, diagnostics)
        self.assertIn("Log out and back in before opening the project in an IDE.", output)

    def test_human_output(self):
        self.cached()
        code, output, diagnostics = self.invoke()
        self.assertEqual(code, 0, diagnostics)
        self.assertEqual(output.count("\n"), 1)
        self.assertIn("Bootstrap complete", output)


if __name__ == "__main__":
    unittest.main()
