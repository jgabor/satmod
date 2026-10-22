# Maintaining

How to publish engine updates and package changes, and where user feedback
arrives. Both packages are in the AUR under the `aur-jgabor` account:
[unreal-engine-css-bin](https://aur.archlinux.org/packages/unreal-engine-css-bin)
and [satmod](https://aur.archlinux.org/packages/satmod). Every step below runs
as your ordinary user unless it says `sudo`.

## Engine updates

Upstream publishes engine releases in `satisfactorymodding/UnrealEngine`. Look
for one when the AUR package is flagged out of date, when a Starter Project
update needs it, or now and then:

```sh
./scripts/update-engine-release --check
```

Nothing is published until the last step, and each step must pass before the
next.

1. **Update the pins.** `./scripts/update-engine-release` rewrites
   `upstream-inputs.json` and the engine's `PKGBUILD`, `.SRCINFO`, and
   `LICENSE.md`. A new release resets `pkgrel` to 1. See the
   [script guide](scripts/README.md#update-engine-release).
2. **Review the diff.** Compare the tag, part count, asset IDs, sizes, and
   digests with the release page. Read any change to `LICENSE.md`. A new
   `pkgrel` on the same tag means upstream changed metadata, such as a digest,
   on a published release. Find out why before you go on.
3. **Check the engine version.** If only the `css` build number changed (for
   example `5.6.1.css83` to `css84`), go on. If the Unreal version changed (for
   example `5.6.1` to `5.7.0`), stop and plan the extra work first: the Starter
   Project's `EngineAssociation`, the engine registration key, and
   `satmod project update`, which refuses engine changes, all assume
   `5.6.1-CSS`.
4. **Update the tests that pin the release.** `tests/test_engine_recipe.py`
   checks `pkgrel`, and `tests/test_release_maintenance.py` checks the tag,
   `pkgver`, and `pkgrel` of the current pins. Then run the suite:

   ```sh
   python3 -m unittest discover -s tests
   ```

5. **Build in a clean chroot.** This needs `devtools` and about 80 GB free on the
   filesystem that holds `.cache/`:

   ```sh
   C=$PWD/.cache/chroot
   mkdir -p "$C"/{srcdest,out,logs}
   ./packages/unreal-engine-css-bin/prefetch-engine-sources "$C/srcdest"
   sudo mkarchroot -C /usr/share/devtools/pacman.conf.d/extra.conf \
     -M /usr/share/devtools/makepkg.conf.d/x86_64.conf "$C/root" base-devel
   # Level 3 instead of --ultra -20; the package contents are the same.
   echo 'COMPRESSZST=(zstd -c -T0 -)' |
     sudo tee "$C/root/etc/makepkg.conf.d/zz-compress.conf"
   cd packages/unreal-engine-css-bin
   SRCDEST="$C/srcdest" PKGDEST="$C/out" LOGDEST="$C/logs" makechrootpkg -c -r "$C"
   ```

   If you already have the parts on the same filesystem, hardlink them into
   `srcdest` instead of downloading. makechrootpkg mounts `srcdest` into the
   chroot, so symlinks to other folders do not work there.
6. **Check the package.** Run namcap with a temporary folder on disk, because the
   chroot's `/tmp` is too small for it:

   ```sh
   TMPDIR=$PWD/.cache/chroot namcap -i .cache/chroot/out/unreal-engine-css-bin-*.pkg.tar.zst
   ```

   Expect the warnings under [Known namcap warnings](#known-namcap-warnings), and
   nothing new. `bsdtar -tvf` on the package should show only `root:root`
   entries, `2775` engine directories, no world-writable or setuid files, and no
   `Engine/Source/Programs/LiveLinkHub`.
7. **Install and build.** `sudo pacman -U` the new package on your own machine.
   The hook should print no warnings, and `getfacl /opt/unreal-engine-css/Engine`
   should show `default:group::rwx`. Run `satmod doctor`, then build a mod or the
   Starter Project's `FactoryEditor Linux Development` target through
   `satmod run`, and start the editor once.
8. **Publish.** Commit the changes, push to GitHub, then sync the AUR checkout,
   review it, and push it:

   ```sh
   ./scripts/aur-sync unreal-engine-css-bin
   git -C .cache/aur/unreal-engine-css-bin show --stat
   ./scripts/aur-sync unreal-engine-css-bin --push
   ```

9. **Clean up.** The chroot is owned by root. On btrfs it contains subvolumes,
   so remove them with `sudo btrfs subvolume delete`. Delete `out` and
   `srcdest` when you no longer need them.

## satmod changes

1. Change the code with tests, and run the suite.
2. Raise `pkgrel`, or set a new `pkgver` and `pkgrel=1`, in
   `packages/satmod/PKGBUILD`. Update the script's checksum in `sha256sums`
   and regenerate `.SRCINFO` with `makepkg --printsrcinfo > .SRCINFO`. The suite
   fails if either is stale.
3. Build with `makepkg -f`, run namcap on the package, install it, and run
   `satmod doctor` and the command you changed.
4. Commit, push to GitHub, and publish with `./scripts/aur-sync satmod`, review,
   then `--push`.
5. For a new `pkgver`, tag the commit you published and push the tag:
   `git tag -a vPKGVER -m "satmod PKGVER-PKGREL"` and `git push origin vPKGVER`.
   A `pkgrel` change alone, such as a packaging fix, gets no tag. Change code
   with a new `pkgver`, so every code change has a tag.

Never publish engine archives, Microsoft tools, built packages, or credentials.
`aur-sync` only copies files that git tracks in `packages/PKG`.

## Known namcap warnings

These were reviewed on 2026-10-22 and need no fix.

Engine package, all expected for a prebuilt engine under `/opt`:

- Setgid directories, and libraries that are not 644: the group-writable design.
- Unstripped binaries, no full RELRO or PIE, executable stacks in `zen`,
  `zenserver`, and a TechSoft library, and `ELF files outside of a valid path`:
  Epic's binaries, packaged as shipped with `!strip`.
- "Insecure RPATH": mostly relative `${ORIGIN}` paths. A few upstream libraries
  carry absolute build-machine paths (`/src/build/...`, `/Stage/...`, and
  `/tmp/dependencies/...` in musl-only files glibc never loads) or an empty entry
  (`libNNEEditorOnnxTools.so` and two TechSoft libraries).
- "Dependency detected and not included": the engine bundles Python 3.11,
  embree, oneTBB, and OpenSSL 1.1, and namcap matches the host's copies. The rest
  are 32-bit, Android, Java, or toolchain files, or optional Python modules.
- "Dependency included, but may not be needed" for `bash`, `xdg-utils`, and
  `acl`: scripts and the install hook use them.

satmod package and both recipes:

- "Missing Contributor tag": informational.
- "Referenced library bash/sh/perl/python3 is an uninstalled dependency" and
  "Script link detected": namcap does not resolve `#!/usr/bin/env` shebangs. All
  four interpreters are in `depends`.
- "Dependency included, but may not be needed" for every dependency except
  `python`: the CLI and msvc-wine run them as programs, and HTTPS downloads need
  `ca-certificates`.
- "No ELF files and not an any package": `x86_64` on purpose. It only works with
  the x86_64 engine and Wine, and bootstrap expects x86_64 metadata.

## User feedback

- **GitHub issues** on [jgabor/satmod](https://github.com/jgabor/satmod/issues)
  are the main channel. The pinned AUR comments point there.
- **AUR comments.** Turn on notifications on both package pages, so new comments
  reach you by email. Answer there, or move longer reports to an issue.
- **Out-of-date flags** reach the maintainer by email. Treat one as a reason to
  run the engine update check above.
- **Triage.** Ask for `satmod doctor --json` output and the failing command's
  output. Never ask anyone to post a Wwise password, a `gh` token, or the
  contents of `.env`.
