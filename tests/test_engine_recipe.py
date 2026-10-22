"""Small engine-recipe fixtures. No real assets, authentication or full build."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "packages/unreal-engine-css-bin"
SCRIPT = "Engine/Build/BatchFiles/Linux/SetupDotnet.sh"
CONTEXT = (
    '\t[ $(uname -m) == "arm64" ] && ARCH=arm64 \n\n'
    '\texport UE_DOTNET_DIR="$CUR_DIR/../../../Binaries/ThirdParty/DotNet/8.0.300/linux-$ARCH"\n'
    '\tchmod u+x "$UE_DOTNET_DIR/dotnet"\n'
    '\texport PATH="$UE_DOTNET_DIR:$PATH"\n'
    '\texport DOTNET_ROOT="$UE_DOTNET_DIR"\n\n'
)


class EngineRecipeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engine-recipe-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.recipe = self.root / "recipe with spaces ü引擎"
        self.recipe.mkdir()
        for name in (
            "PKGBUILD",
            "LICENSE.md",
            "setup-dotnet-permissions.patch",
            "unreal-engine-css-bin.install",
        ):
            shutil.copyfile(RECIPE / name, self.recipe / name)
        self.src = self.root / "external source cache"
        self.src.mkdir()
        self.pkg = self.root / "pkg"
        self.pkg.mkdir()
        for name in ("LICENSE.md", "setup-dotnet-permissions.patch"):
            shutil.copyfile(self.recipe / name, self.src / name)
        self.env = dict(
            os.environ, RECIPE=str(self.recipe), SRC=str(self.src), PKG=str(self.pkg)
        )
        self.bin = self.root / "network sentinels"
        self.bin.mkdir()
        for name in ("gh", "curl", "wget", "download-gh-asset"):
            sentinel = self.bin / name
            sentinel.write_text(
                '#!/bin/bash\nprintf network-called >> "$SRC/network-called"\nexit 99\n'
            )
            sentinel.chmod(0o755)
        self.env["PATH"] = str(self.bin) + ":" + os.environ["PATH"]

    def bash(self, code, ok=True):
        result = subprocess.run(
            ["bash", "-c", code],
            cwd=self.recipe,
            env=self.env,
            text=True,
            capture_output=True,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.src / "network-called").exists())
        return result

    def metadata(self):
        output = self.bash("makepkg --printsrcinfo").stdout
        data = {}
        for line in output.splitlines():
            if " = " in line:
                key, value = line.strip().split(" = ", 1)
                data.setdefault(key, []).append(value)
        return output, data

    def test_metadata_pins_notice_and_no_network(self):
        output, data = self.metadata()
        self.assertEqual(output, (RECIPE / ".SRCINFO").read_text())
        self.assertEqual(data["install"], ["unreal-engine-css-bin.install"])
        pins = json.loads((ROOT / "upstream-inputs.json").read_text())["engine"]
        self.assertEqual(len(data["source"]), 6)
        for index, asset in enumerate(pins["assets"]):
            alias = f"UnrealEngine-CSS-{pins['tag']}-Editor-Linux.tar.zst.{index:02}"
            self.assertEqual(
                data["source"][index],
                f"{alias}::ghasset://{pins['repository']}/{pins['tag']}/{asset['id']}",
            )
            self.assertEqual(data["noextract"][index], alias)
            self.assertEqual(data["sha256sums"][index], asset["sha256"])
        notice = (RECIPE / "LICENSE.md").read_bytes()
        self.assertEqual(len(notice), 195)
        self.assertEqual(hashlib.sha256(notice).hexdigest(), data["sha256sums"][4])
        patch = (RECIPE / "setup-dotnet-permissions.patch").read_bytes()
        self.assertEqual(hashlib.sha256(patch).hexdigest(), data["sha256sums"][5])
        self.assertEqual(data["options"], ["!strip", "!debug", "staticlibs"])
        self.assertEqual(data["pkgrel"], ["5"])
        self.assertEqual(
            data["depends"],
            [
                "glibc",
                "libgcc",
                "libstdc++",
                "dbus",
                "systemd-libs",
                "bash",
                "xdg-utils",
                "alsa-lib",
                "at-spi2-core",
                "libxcomposite",
                "libxdamage",
                "libxkbcommon",
                "libxrandr",
                "mesa",
                "nss",
                "pango",
                "acl",
            ],
        )
        self.assertEqual(data["optdepends"], ["vulkan-driver: run the editor", "glu: TechSoft CAD import"])
        self.assertEqual(data["makedepends"], ["github-cli", "zstd", "patch"])
        self.assertNotIn("provides", data)
        self.bash(
            "source ./PKGBUILD; [[ $(set -o | grep pipefail) == *off ]]; "
            "[[ $install == unreal-engine-css-bin.install && -f $install ]]"
        )

    def test_actual_makepkg_agent_spaces_unicode_and_external_cache(self):
        helper = self.recipe / "download-gh-asset"
        helper.write_text(
            '#!/bin/bash\n[[ $# == 2 ]] || exit 12\nprintf "%s\\n" "$1" > "$2"\n'
        )
        helper.chmod(0o755)
        self.bash(
            "source /usr/share/makepkg/util/source.sh; "
            "source /usr/share/makepkg/source/file.sh; "
            'DLAGENTS=("https::/usr/bin/false %u %o"); source ./PKGBUILD; '
            "[[ ${DLAGENTS[0]} == https::* ]] || exit 13; "
            'startdir=$RECIPE; SRCDEST=$SRC; cd "$SRCDEST"; '
            'download_file "${source[0]}"; '
            "# Cached reuse must not call the helper again.\n"
            'rm "$RECIPE/download-gh-asset"; download_file "${source[0]}"'
        )
        _, data = self.metadata()
        alias, url = data["source"][0].split("::")
        self.assertEqual((self.src / alias).read_text(), url + "\n")

    def fixture(self, broken_patch=False):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name, payload, mode in (
                (
                    SCRIPT,
                    (("\n" * 44 + CONTEXT) if not broken_patch else "wrong\n").encode(),
                    0o755,
                ),
                (
                    "Engine/Binaries/ThirdParty/DotNet/8.0.300/linux-x64/dotnet",
                    b"executable",
                    0o755,
                ),
                ("Engine/libfixture.a", b"!<arch>\n", 0o644),
                ("Engine/Source/Programs/LiveLinkHub/LiveLinkHub.Target.cs", b"rules", 0o644),
                ("Engine/Source/ThirdParty/Licenses/fixture.txt", b"notice\n", 0o644),
            ):
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(payload), mode
                archive.addfile(info, io.BytesIO(payload))
            info = tarfile.TarInfo("Engine/fixture-link")
            info.type, info.linkname = tarfile.SYMTYPE, "libfixture.a"
            archive.addfile(info)
            info = tarfile.TarInfo("Engine/setgid-directory")
            info.type, info.mode = tarfile.DIRTYPE, 0o2775
            archive.addfile(info)
        compressed = subprocess.run(
            ["zstd", "-q", "-c"],
            input=stream.getvalue(),
            capture_output=True,
            check=True,
        ).stdout
        _, data = self.metadata()
        hashes = []
        for index, alias in enumerate(data["noextract"]):
            piece = compressed[
                len(compressed) * index // 4 : len(compressed) * (index + 1) // 4
            ]
            (self.src / alias).write_bytes(piece)
            hashes.append(hashlib.sha256(piece).hexdigest())
        self.env["FIXTURE_HASHES"] = " ".join(hashes)
        # A broad glob would consume this stale part and fail.
        (self.src / "UnrealEngine-CSS-stale-Editor-Linux.tar.zst.04").write_bytes(
            b"stale"
        )
        return data

    def package(self, ok=True, extra=""):
        return self.bash(
            "source ./PKGBUILD; srcdir=$SRC; pkgdir=$PKG; "
            'read -ra fixture_hashes <<< "$FIXTURE_HASHES"; '
            "for i in 0 1 2 3; do sha256sums[i]=${fixture_hashes[i]}; done; "
            + (extra + "; " if extra else "")
            + "package",
            ok=ok,
        )

    def test_repeat_package_patch_modes_and_static_archive(self):
        self.fixture()
        for _ in range(2):
            self.package()
            engine = self.pkg / "opt/unreal-engine-css"
            self.assertIn(
                '[ -x "$UE_DOTNET_DIR/dotnet" ] || chmod', (engine / SCRIPT).read_text()
            )
            self.assertEqual(
                (engine / "Engine/setgid-directory").stat().st_mode & 0o7777, 0o2775
            )
            self.assertEqual((engine / SCRIPT).stat().st_mode & 0o7777, 0o775)
            self.assertEqual(
                (engine / "Engine/libfixture.a").read_bytes(), b"!<arch>\n"
            )
            self.assertEqual(
                (
                    self.pkg / "usr/share/licenses/unreal-engine-css-bin/LICENSE.md"
                ).read_bytes(),
                (RECIPE / "LICENSE.md").read_bytes(),
            )
            self.assertFalse((engine / "Engine/Source/Programs/LiveLinkHub").exists())
            self.assertEqual((engine / "Engine/libfixture.a").stat().st_mode & 0o7777, 0o664)
            self.assertTrue((engine / "Engine/fixture-link").is_symlink())
            self.assertEqual(os.readlink(engine / "Engine/fixture-link"), "libfixture.a")
            for path in engine.rglob("*"):
                if path.is_symlink():
                    continue
                mode = path.stat().st_mode & 0o7777
                self.assertFalse(mode & 0o002, str(path))
                self.assertTrue(mode & 0o020, str(path))
                if path.is_dir():
                    self.assertEqual(mode, 0o2775, str(path))
            self.assertEqual(list(self.src.glob("engine-stage.*")), [])
            # makepkg clears pkgdir before package()/--repackage.
            shutil.rmtree(self.pkg)
            self.pkg.mkdir()

    def test_makepkg_verify_build_and_repackage_small_fixture(self):
        data = self.fixture()
        recipe = (self.recipe / "PKGBUILD").read_text()
        for real_hash, fixture_hash in zip(
            data["sha256sums"], self.env["FIXTURE_HASHES"].split()
        ):
            recipe = recipe.replace(real_hash, fixture_hash)
        (self.recipe / "PKGBUILD").write_text(recipe)
        config = self.root / "makepkg.conf"
        config.write_text(
            Path("/etc/makepkg.conf").read_text()
            + "\n"
            + f"SRCDEST={shlex.quote(str(self.src))}\n"
            + f"BUILDDIR={shlex.quote(str(self.root / 'build'))}\n"
            + f"PKGDEST={shlex.quote(str(self.root / 'output'))}\n"
            + "PKGEXT='.pkg.tar.zst'\n"
        )
        self.env["CONFIG"] = str(config)
        self.bash('makepkg --config "$CONFIG" --verifysource')
        # Only these kilobyte fixtures are built. Host dependency checking is
        # not part of this packaging-lifecycle test, so use --nodeps.
        self.bash('makepkg --config "$CONFIG" --nodeps --force')
        self.bash('makepkg --config "$CONFIG" --nodeps --force --repackage')
        package = next((self.root / "output").glob("*.pkg.tar.zst"))
        listing = subprocess.run(
            ["tar", "--zstd", "-tf", str(package)],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        self.assertIn("opt/unreal-engine-css/Engine/libfixture.a", listing)
        self.assertIn("usr/share/licenses/unreal-engine-css-bin/LICENSE.md", listing)
        self.assertNotIn("download-gh-asset", listing)
        (self.src / data["noextract"][0]).write_bytes(b"corrupt after build")
        failure = self.bash(
            'makepkg --config "$CONFIG" --nodeps --force --repackage', ok=False
        )
        self.assertIn("FAILED", failure.stdout + failure.stderr)

    def test_corrupt_part_rejected_before_extraction(self):
        data = self.fixture()
        (self.src / data["noextract"][2]).write_bytes(b"corrupt")
        self.package(ok=False)
        self.assertEqual(list(self.src.glob("engine-stage.*")), [])
        self.assertEqual(list(self.pkg.iterdir()), [])

    def test_pipeline_failure_cleans_stage(self):
        self.fixture()
        self.package(
            ok=False,
            extra='printf broken > "$srcdir/${_parts[0]}"; '
            'sha256sums[0]=$(sha256sum "$srcdir/${_parts[0]}"); '
            "sha256sums[0]=${sha256sums[0]%% *}",
        )
        self.assertEqual(list(self.src.glob("engine-stage.*")), [])
        self.assertEqual(list(self.pkg.iterdir()), [])

    def test_patch_failure_cleans_stage(self):
        self.fixture(broken_patch=True)
        self.package(ok=False)
        self.assertEqual(list(self.src.glob("engine-stage.*")), [])
        self.assertEqual(list(self.pkg.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
