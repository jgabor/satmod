# TODO

## Scope

Automate the
[Linux setup guide](https://docs.ficsit.app/satisfactory-modding/latest/Development/Linux/LinuxSetup.html)
through command-line **Project Setup**, with two Arch packages:

- `unreal-engine-css-bin`: the prebuilt CSS engine under `/opt/unreal-engine-css`.
- `satmod`: provides `satmod setup` to install
  MSVC under Wine, register the engine, and write the build environment. The CLI
  also provides `project init` for Starter Project and Wwise setup, `run` to
  start tools, `doctor` to check the installation, and `mod new` and `mod build`
  for library scaffolding and Windows client packaging.

Rules that hold throughout:

- Account linking, repository access, `gh auth login`, and the Audiokinetic
  account stay manual.
- User setup runs without root.
- Package install hooks never download tools, set up Wine, or change a user's
  account. The engine hook may create the `unreal-engine-css` group and give it
  the engine files. Only bootstrap, which the user runs, adds the user to it.
- The engine is writable only by root and the `unreal-engine-css` group, never by
  everyone. Unreal's build tools write all over the engine tree, so a read-only
  engine does not work.
- Engine archives, Microsoft tools, built packages, and credentials stay out of
  version control.

## Done

Git history has the details.

- **CLI project update (run 2026-10-22).** `project update DIR`
  fast-forwards a Starter Project to `origin/master` or `--ref` and updates Wwise
  to the versions in the target's build.yml. Before it changes anything, it
  refuses local commits, changes it does not own, engine changes, and a missing
  Wwise login. Both commands now read the Wwise versions from the project's
  build.yml instead of hard-coded pins. A changed integration first removes
  `Plugins/Wwise*`, since integrate-ue never deletes files and WwisePatches keeps
  its applied list inside `Plugins/Wwise`. An older Wwise project is migrated
  and soundbanks are regenerated. wwise-cli's stdout is discarded when it does
  not prompt.
  On 2026-10-22, run from the repo, it moved `~/git/SatisfactoryModLoader` from
  `d2162c999b` to `8eebc9e659` and Wwise from 2023.1.14 to 2025.1.6. It took
  three runs, because Wwise 2025 changed two things the fake tests could not
  know. WwiseConsole moved to the `Authoring_Windows_x64_Release` package, and
  the SDK libraries moved to `Plugins/WwiseSoundEngine/ThirdParty`. Each run
  stopped at a readiness check, and the next run resumed. A fourth run skipped
  all seven steps.
  - `WwiseConsole migrate` saved the project as `v2025.1.6` build 9117.
  - The soundbanks report `Generator="2025.1.6.9117"`.
  - The plugin's `VersionName` is `2025.1.6.9117.4248`.
  - `git status` shows only `AudioRouting=Separate`.
  - The logs had no credentials or signed URLs.
  - In `~/git/satsync`, `E2E=1 client/test-linux.sh` passed. All
    WwisePatches applied to the fresh plugin, the Linux editor and Win64 modules
    built, and 34 automation tests passed. Two had expected warnings.
  - The run and its rerun listed the old 2023 caches (6.2 GB and 1.1 GB) under
    `old_caches` and kept them. The user had them removed by hand afterwards.
  - Follow-ups from that run: soundbank generation now first removes
    `GeneratedSoundBanks`, since two files from the 2023 build outlived the
    regenerate, and a failed Wwise step now restores `AudioRouting=Separate`.

- **CLI Project Setup (installed 2026-10-11).** `project init DIR`
  clones the Starter Project, verifies and caches pinned wwise-cli, downloads
  and integrates the guide's distinct SDK and integration versions, creates the
  Wwise project and soundbanks headless under managed Wine, and sets audio
  routing without changing unrelated INI bytes. Fake-tool tests cover reruns,
  resume, credentials, downloads, and settings. Audiokinetic login and Rider setup stay
  manual. Version inputs are recorded under `wwise` in upstream-inputs.json.
  `WWISE_USER` and `WWISE_PASS` work as a second credential pair. Closed
  standard input counts as no terminal, and a login template is committed.
  On 2026-10-11 the installed CLI ran `project init` on an empty directory with
  no terminal input, the login taken from the user's credentials file, and an
  empty download cache. It did a real git clone, downloaded and verified wwise-cli,
  downloaded the Wwise SDK, integrated the plugin, and created the Wwise project
  and soundbanks under the managed Wine prefix. All seven steps reported `done`
  in about five minutes, and a rerun reported all seven `skipped`. `git diff`
  showed one changed line (`AudioRouting=Separate`), the generated soundbanks had
  the same six files as the user's project, and a scan of the logs, caches, and project files
  found no credentials. The integrated plugin matched the user's apart from build
  outputs and source files that the project's own WwisePatches change.

- **CLI mod commands (installed 2026-10-11).** `mod new` scaffolds
  Blueprint or C++ library mods from the project's Alpakit templates. `mod build`
  packages Windows client mods and optionally copies them into the detected
  Steam install. On 2026-10-09 `mod build LinuxTestMod` rebuilt the
  editor-created mod headless, and `mod new CliTestMod --cpp` then `mod build
  CliTestMod` compiled it for Linux and Win64, cooked, packaged, and copied it to
  the game. The first attempt showed that cooking needs the mod's Linux editor
  module, so `mod build` now builds the editor target first. On 2026-10-11 the
  user confirmed that `CliTestMod` loaded in game, then removed it because a friend
  without the mod could not join their session.

- **First mod (2026-10-09).** With the packaged setup, Alpakit packaged a C++ &
  Blueprint test mod for Windows. The Win64 compile ran through MSVC under Wine,
  Alpakit copied the mod into the Steam game, and under Proton SML 3.12.0 logged
  it as loaded and its game feature as active. It also shows in the in-game Mods
  list.

- **Wrapper Wine prefix fix (2026-10-09).** Setup pins the managed prefix in
  `msvcenv.sh` and clears shell startup variables for child wrappers. Fresh
  installs and reruns apply the fix, with regression tests for `BASH_ENV`.

- **Engine package.** Pinned to `5.6.1-css-83` with per-part checksums, an
  authenticated `gh` download helper, optional prefetch, streamed extraction, the
  `SetupDotnet.sh` permission patch, and a registration reminder. The user
  installed it and checked the reminder. A later revision makes the engine
  group-writable and leaves out `LiveLinkHub`, matching what the user first
  applied by hand.
- **Setup package.** Pinned `msvc-wine` snapshot `61b7cbc`, user-run setup with
  staging, validation, and smoke tests, engine registration that keeps other
  mappings, managed `~/.unrealrc` hook, and the `satisfactory-modding run` launcher. The user reports running it
  end to end: the first run installed MSVC 14.38.33130 (compiler 19.38.33145) and SDK
  10.0.22621.0, and a second run reused it without downloading.
- **Scripts.** `update-engine-release` and `bootstrap`. The user reports a read-only
  `--check` against the live API and a full bootstrap that reused cached packages.
- **Project Setup by hand (2026-10-09).** On the first packages, with the group
  and `LiveLinkHub` changes applied by hand, the user ran the guide's Project Setup:
  wwise-cli download and integration, Wwise project and sound bank generation,
  Rider through `satisfactory-modding run` with the Mods Fix plugin, a successful
  Development Editor build of the Starter Project, and editor startup with shader
  compilation. The guide's optional UnrealBuildTool patch was not needed.
- **Packaged fix (2026-10-09).** The group-writable engine and setup packages
  upgraded over the hand-modified install, with only the expected warnings about the already
  deleted `LiveLinkHub` files. Afterwards every engine file belonged to
  `unreal-engine-css`, directories were `2775`, nothing was world-writable, and
  `LiveLinkHub` was gone. Rider built the project and the editor started.
- **Tests.** Fixture tests for every script and hook, using fake tools and
  temporary home directories. They never download engine or Microsoft files.

## Open verification

- [x] Build both packages in a clean Arch chroot with prefetched engine parts
  (2026-10-22). `mkarchroot` with devtools' Arch `[core]`/`[extra]` config and
  `makechrootpkg`, with the four parts hardlinked into a separate SRCDEST and
  zstd at its default level instead of `--ultra -20`. The engine
  (5.6.1.css83-5) built in about 5 minutes, and the setup package (1.0.0-8) built
  with it installed via `-I`, matching the host build's files, modes, and sizes.
  Installing the engine there ran the new hook without warnings: all 33,103
  directories got `default:group::rwx` and setgid, only directories got default
  ACL entries, and every file was group-writable in group `unreal-engine-css`.
  The same package then upgraded this machine's css83-4 install in 69 seconds,
  silently because the user is a member and registered. All 35,041 directories
  got the default ACL, the 3,375 files that builds had left without group write
  became group-writable, and a new file and directory under umask 022 came out
  664 and 2775. `satisfactory-modding doctor` still passed.
- [x] Run namcap on both recipes and both built packages. Nothing to fix.
  Engine package (css83-5), all expected for a prebuilt engine under `/opt`:
  - Setgid on all 33,103 directories and libraries that are not 644: the
    group-writable design.
  - Unstripped, no full RELRO or PIE, three executable stacks (`zen`,
    `zenserver`, a TechSoft library), and `ELF files outside of a valid path`:
    upstream binaries, packaged as shipped with `!strip`.
  - "Insecure RPATH": mostly relative `${ORIGIN}` paths. A few upstream
    libraries have absolute build-machine paths (`/src/build/...`, `/Stage/...`,
    and `/tmp/dependencies/...` in musl-only files glibc never loads) or an empty
    entry (`libNNEEditorOnnxTools.so` and two TechSoft libraries). Left as Epic
    ships them.
  - "Dependency detected and not included": the engine bundles Python 3.11,
    embree, oneTBB, and OpenSSL 1.1, and namcap matched the host's copies. The
    rest are 32-bit, Android, or Java files, the clang sysroot, or optional
    Python modules (`libcrypt.so.1` for `_crypt`; see the next item).
  - "Dependency included, but may not be needed" for `bash`, `xdg-utils`, and
    `acl`: scripts and the install hook use them.
  Setup package and recipes:
  - Both recipes: only "Missing Contributor tag", which is informational.
  - "Referenced library bash/sh/perl/python3 is an uninstalled dependency" and
    "Script link detected": namcap does not resolve `#!/usr/bin/env` shebangs.
    All four interpreters are in `depends`.
  - "Dependency included, but may not be needed" for every non-Python
    dependency: the CLI runs them as programs, and its `TOOLS` list and msvc-wine
    need each one, and HTTPS downloads need `ca-certificates`.
  - "No ELF files and not an any package": kept as `x86_64` on purpose. It only
    works with the x86_64 engine and Wine, and bootstrap expects x86_64
    metadata.
- [x] Check file ownership, permissions, and declared dependencies (2026-10-22).
  `satisfactory-modding-setup` 1.0.0-8: every entry is root:root, directories
  755, files 644 or 755, nothing group- or world-writable, no setuid, no
  dangling symlinks, and every tool the CLI requires belongs to a declared
  dependency. The installed engine: root owns its files apart from those builds
  rewrote (below), the hook set group `unreal-engine-css` on all of them,
  directories are 2775, and nothing is world-writable or setuid. The built
  css83-5 package from the chroot has only root:root entries, 2775 engine
  directories, group-writable files, no world-writable or setuid files, no
  absolute symlinks, and no `LiveLinkHub`. (The css83-4 package in
  `.cache/engine-recipe` was overlooked at first.) Every NEEDED library of the
  engine's x86_64 Linux ELF files resolves inside the dependency closure, except
  optional ones: `libGLU.so.1` for TechSoft CAD import, and old sonames for a few
  bundled Python modules (bz2, crypt, gdbm, curses, readline). The rest are
  Android, ARM, musl, or 32-bit files. The editor ships its own Vulkan loader.
- [x] Keep files that builds create group-writable. The engine hook sets a default
  group ACL on every directory and runs `chmod -R g+w`; `acl` is a new dependency.
  Before, UAT had rewritten 53 package files and builds had added about 5,400
  user-owned files, about 3,400 of them without group write under umask 022.
- [x] Add engine optdepends: `vulkan-driver` for the editor and `glu` for CAD
  import (pkgrel 5).
- [x] Test package removal, and confirm user data survives (2026-10-22). Upgrade
  over the hand-modified install and later releases already worked.
  - `satisfactory-modding-setup` on this machine: `pacman -Rsp` showed `-Rns`
    takes nothing else here. `pacman -Rns` removed the CLI and
    `/usr/share/satisfactory-modding-setup` and left all 59,289 entries under the
    config, data, cache, and wwise-cli directories, `~/.unrealrc`, and
    `Install.ini` unchanged. The staged MSVC `cl` still ran without the package.
    Reinstalling 1.0.0-8 passed `doctor`; only Wine prefix timestamps from that
    `cl` run differed.
  - `unreal-engine-css-bin` in a throwaway chroot copy, to leave the engine in
    daily use alone: a group member registered the engine, built into
    `Engine/Intermediate`, and overwrote a package file. `pacman -R` removed all
    245,193 package paths, including the overwritten file, and the license. Only
    the member's build output (664, its group kept) and its four directories
    stayed, along with the group. The member's home was unchanged. Reinstalling
    over the leftovers reported no conflicts, restored the overwritten file, kept
    the build output, and the hook made everything group-writable again.

Not planned, to keep verification proportionate: forced failure runs (missing
repository access, a missing archive part, a corrupted download), a bootstrap
that installs dependencies through sudo or adds a user outside the group, a real
engine update with `update-engine-release`, answering wwise-cli's prompts by
hand in `project init`, and a Rider build of a project from `project init`.
Fixture tests cover the failure, bootstrap, release, and prompt paths, Rider
already built the Starter Project after the packaged fix, and problems will come
in as issues.

## Completion criteria

- [x] Both packages build and install with normal Arch tooling. Built and
  installed on this machine, and built in a clean Arch chroot on 2026-10-22.
- [x] Engine inputs are pinned and verified, and authenticated downloads work.
- [x] One run of `satmod setup` installs the pinned MSVC/SDK,
  configures `UE_WINE_MSVC`, and registers the engine without prompts. Based on
  the user's report.
- [x] Repeat setup runs and package upgrade or removal keep unrelated user state.
  Reruns, upgrades, and removal are done.
- [x] The docs give a tested path from repository access through Project Setup
  with `project init`. No clean-machine run is planned: the setup is in daily
  use for the mod in `~/git/satsync`, and problems will come in as
  issues.

## Future

### AUR publishing

After the completion criteria are met:

- [x] Recheck package names against the
  [Arch package guidelines](https://wiki.archlinux.org/title/Arch_package_guidelines),
  [nonfree package guidelines](https://manual.archlinux.page/package-guidelines/non-free/),
  and [AUR submission guidelines](https://wiki.archlinux.org/title/AUR_submission_guidelines)
  (2026-10-22). Both names stand:
  - Neither name is taken in the AUR or the official repositories, and both use
    only lowercase letters and hyphens.
  - `unreal-engine-css-bin`: the AUR requires `-bin` for prebuilt deliverables
    when the sources exist, and the CSS engine source is in
    `satisfactorymodding/UnrealEngine` (private, behind Epic account linking).
    It follows the existing `unreal-engine`, `unreal-engine-bin`, and
    `unreal-engine-src-5.x` pattern. It installs to `/opt/unreal-engine-css`, so
    it neither conflicts with nor provides those packages. The nonfree
    guidelines allow `/opt` for a directory a group writes into, which is this
    design. `vercmp` orders `5.6.1.css83` before `css84`, `css100`, and later
    engine versions.
  - `satisfactory-modding-setup` (now `satmod`): built from pinned sources, so
    no suffix. It does not collide with the `satisfactory-mod-manager*` packages.
- [x] Rename `satisfactory-modding-setup` to `satisfactory-modding`, matching its
  command, and fix its metadata (1.0.0-1). `pkgdesc` now covers Project Setup and
  mod builds, and `url` is this repository. The markers the CLI writes into
  `~/.unrealrc`, the environment file, and the toolchain's `msvcenv.sh` kept the
  old name.
- [x] Rename package, command, and GitHub repo to `satmod` (1.0.0-1), before
  anything is published. Everything follows, with no migration code: the
  recipe at `packages/satmod`, `/usr/bin/satmod`, `/usr/share/satmod`, the user
  folders `~/.config/satmod`, `~/.local/share/satmod`, and `~/.cache/satmod`, the
  `.satmod.json` markers, and the `# satmod` markers in `~/.unrealrc`, the
  environment file, and `msvcenv.sh`. This machine was migrated by hand. The
  name is free in the AUR, the official repositories, and on GitHub. msvc-wine
  stays bundled: `msvc-wine-git` tracks a different, unpinned upstream and
  installs a system-wide MSVC during makepkg.
- [x] Prepare one AUR repository per package with its `.SRCINFO`, license, and
  helper files (2026-10-22). `scripts/aur-sync` copies each recipe's tracked
  files, minus `README.md`, into `.cache/aur/PKG` and commits; it pushes only
  with `--push`. Both PKGBUILDs name
  `Jonathan Gabor <jgabor@users.noreply.github.com>` as maintainer, for the
  `aur-jgabor` account. The engine recipe gained an ISC `LICENSE` and a
  `REUSE.toml` that marks Epic's notice and the patch as
  `LicenseRef-UnrealEngine`. satmod ships its script in the AUR repository, so
  one PKGBUILD serves bootstrap and the AUR.
- [ ] Push both AUR repositories with `scripts/aur-sync unreal-engine-css-bin satmod
  --push`, after `jgabor/satmod` is public (satmod's `url` points there). Never
  publish engine archives, Microsoft tools, or built packages.
- [ ] Explain the authenticated download and license terms on each package page.
- [ ] Set up a reviewed process for engine updates and for user feedback.
