# Implementation TODO

## Objective and scope

Automate the [Linux modding environment setup guide](https://docs.ficsit.app/satisfactory-modding/latest/Development/Linux/LinuxSetup.html)
up to, but not including, **Project Setup**, using two Arch Linux packages:

- `unreal-engine-css-bin`: the prebuilt CSS Unreal Engine, installed under
  `/opt/unreal-engine-css`.
- `satisfactory-modding-setup`: the setup tools and an unattended, user-run command
  that installs MSVC and registers the engine.

Account creation, account linking, repository-access grants, and GitHub login remain
manual prerequisites, along with applicable license terms. User setup must run
without root privileges. Pacman install scripts must not download toolchains, initialize Wine,
or configure user accounts.

AUR publication and project setup are deferred to the **Future** section.

## 1. Inspect upstream inputs and establish the package layout

**Complete, inputs only (2026-10-02):** layout, release/archive/license inputs,
approximate space, ordinary host dependency declarations and guide tools, and the
complete source-tested MSVC pin are checked. This is not an installed engine,
normal GUI startup, MSVC runtime, or two-package completion claim.

- [x] Choose the repository layout for the two package recipes, shared documentation,
  and maintainer scripts. Keep each recipe suitable for its own future AUR package base.
  Layout: `packages/`, `scripts/`, root `upstream-inputs.json`, README/TODO
  documentation, and ignored `.cache/`.
- [x] Recheck the latest stable engine release and its applicability to the current
  Satisfactory modding guide. On 2026-10-02 the guide's release link selected
  `5.6.1-css-83`, four non-debug Linux parts (`.00` through `.03`), 8,264,339,940 bytes.
  This establishes guide selection, not runtime game compatibility.
- [x] Download the engine archive with existing GitHub credentials and inspect its
  layout, licenses, bundled .NET/Clang components, and executable permissions.
  Parts verified; the recipe packages the pinned source pointer notice below.
  See the [pins](upstream-inputs.json).
- [x] Identify and pin the source tag's root `LICENSE.md` pointer notice.
  Tag `5.6.1-css-83` resolves to source commit
  `5271227f38511532213b10dd10d6ed4f0b04fef5`; the notice is pinned in
  `upstream-inputs.json`.
- [x] Document approximate download, build, and installed space from available
  measurements. Download: 8,264,339,940 bytes; extracted payload: 29,969,720,711
  bytes. Allow roughly 48 GB plus overhead for parts, build tree, and one package,
  and roughly 30 GB plus cache/metadata for installation.
- [x] Declare and verify ordinary host runtime dependencies for the editor and tools
  required by the Linux setup guide, including CEF providers. Normal GUI startup
  remains later verification.
- [x] Pin and source-test a complete `mircearoata/msvc-wine` snapshot from `ue-patches`.
  Commit `61b7cbc8cb9413fec8f0016ef433a90e06c37f54`. Preserve the full snapshot,
  including all five patches, not only `vsdownload.py` and the helpers.
  Milestone 1 requires a source-tested pin, not an MSVC installation. No MSVC
  installation, Wine/helper runtime test, or compile/link test was run; those
  remain later work in sections 3 and 5.
- [x] Confirm the guide's toolchain selection before implementation:
  `--msvc-version 17.8`, `--sdk-version 10.0.22621`, and
  `--channel release.ltsc.17.8`. These are vsdownload.py arguments; mutable Microsoft
  manifests mean the source pin alone does not freeze the toolchain payloads.
- [x] Inspect the pinned installer scripts for dependencies, license requirements,
  generated helper executables, and Wine initialization behavior.
  Pass the selection flags to `vsdownload.py`, then invoke `install.sh` via Bash.
  Wine initialization, artifact validation, and wrapper behavior need runtime checks.

## 2. Implement `unreal-engine-css-bin`

**Engine recipe implemented:** the user successfully installed pkgrel 2; the
package query, root ownership, `/opt` directory mode 755 and dotnet permission
guard were checked. The user reports pkgrel 3 is installed and its registration
notice flow tested: commenting out the registration entry then reinstalling printed
the reminder; registering then reinstalling suppressed it. These user-reported
results were not independently rerun here. The cached build passed normal
dependency/integrity checks. The retained package's size and SHA-256 are in the
engine guide. Normal GUI/cache-state startup and clean Arch
checks belong to section 5; user setup is implemented and fixture-tested in section 3.
This completes the engine recipe, not the two-package setup milestone.
See the [engine guide](packages/unreal-engine-css-bin/README.md).

### Release inputs and authenticated downloads

- [x] Define static package metadata, including a normalized upstream version, exact
  release tag, architecture, license identifiers, and dependencies.
  Pkgrel 2 declares the verified ordinary host closure, including CEF providers.
  This is not proof of every optional feature or normal rendered startup.
- [x] Declare each archive part explicitly in `source`, with release-specific local
  filenames, fixed checksums, and corresponding `noextract` entries.
- [x] Implement an authenticated download helper using GitHub CLI and makepkg's
  `DLAGENTS` mechanism. Require existing authentication and repository access.
  The helper and dispatcher are covered by fixtures.
- [x] Keep credentials out of URLs, logs, package metadata, and package contents.
- [x] Download to temporary files and rename only after successful completion.
- [x] Support makepkg's source cache and pre-fetched assets so package builds can run
   without GitHub credentials inside the build environment.
- [x] Add optional `prefetch-engine-sources [SOURCE-CACHE-DIR]`, with at most two
  existing one-asset helpers. Preserve cached files/aliases; normal makepkg checksum
  checks remain required. Packaging/decompression are unchanged; network throughput
  is unmeasured.
- [x] Report missing authentication, inaccessible releases, and missing assets clearly.
  Failure fixtures pass; the real acquisition used existing access.

### Extraction and packaging

- [x] Verify every archive part before extracting it.
- [x] Stream the explicit, ordered part list through `zstd` and `tar` into a dedicated
  directory under `$srcdir`. Avoid a broad glob that could include stale parts.
- [x] Stage the complete engine under `$pkgdir/opt/unreal-engine-css` without an
  unnecessary extra copy or concatenated archive.
- [x] Preserve prebuilt binaries and required static libraries. Validate
  `options=('!strip' '!debug' 'staticlibs')` against the archive.
- [x] Package the pinned upstream license notice under `/usr/share/licenses/unreal-engine-css-bin`.
  Identifier: `LicenseRef-UnrealEngine`; the exact 195-byte source pointer is
  verified unchanged as `LICENSE.md` in the built payload, not a system install.
  Bundled third-party notices remain intact.
- [x] Keep downloads in the source-acquisition phase and installation writes inside
  `$pkgdir`. Do not invoke package managers from PKGBUILD functions.
- [x] Use distinct package paths and names. Do not claim compatibility with generic
  Unreal Engine packages through an inappropriate `provides` entry.

### Unprivileged engine use

- [x] Add instruction-only post-install/upgrade registration reminders. Suppress
  them only for a known non-root `SUDO_USER` with the engine registered in that
  account's `[Installations]` section. Unknown accounts get a conditional reminder;
   no registration or configuration writes run as root. The user reports pkgrel 3
   installation and both real reminder paths tested, as recorded above.
- [x] Set executable modes correctly while packaging.
- [x] Test the bundled .NET setup script for non-owner use of the root-owned engine.
  The unconditional `chmod` failed; the permission guard fixes this failure.
- [x] If required, add a narrow, documented patch that skips `chmod` when the bundled
  executable already has the required permission.
- [x] Document known permission requirements and the limits of current probes that
  affect later project setup. The engine remains non-writable; additional runtime
  write/cache-state verification is tracked in section 5, not a recipe feature blocker.

## 3. Implement `satisfactory-modding-setup`

**Implemented and fixture-tested (2026-10-03):** the setup package builds with normal
makepkg dependency/integrity checks. All requirements below are implemented, including
mandatory artifact and compile/link/dependency smoke gates in the user-run command.
Isolated tests use fake tools and temporary HOME directories. After the pkgrel 2
Wine server wait fix, the user reports successful helper compilation, compile/link/
header/dependency/resource tests, configured completion, and repeat reuse without
downloads (see section 5). These results were not independently rerun;
no agent-run account setup or consent occurred. See the
[setup package guide](packages/satisfactory-modding-setup/README.md).
Sources: [setup guide](https://docs.ficsit.app/satisfactory-modding/latest/Development/Linux/LinuxSetup.html),
[input pins](upstream-inputs.json), and the source-checked
[ue-patches snapshot](https://github.com/mircearoata/msvc-wine/tree/61b7cbc8cb9413fec8f0016ef433a90e06c37f54).
This remains guide-equivalent local setup before Project Setup; AUR is deferred.

- [x] Declare `unreal-engine-css-bin` and actual setup dependencies: Python,
  msitools (`msiextract`, with gcab transitively), Wine, Git, Perl, Bash, working CA
  trust, and ordinary Arch utilities. The guide lists git/msitools/tar/zstd/dos2unix/
  wine: tar/zstd serve engine acquisition; dos2unix serves later SML/Wwise patches.
  `xdg-utils` is already an engine registration dependency, not a guide prerequisite.
  No new pip dependencies, native C++ compiler, winbind/Samba, Mono/Gecko, or unzip
  requirement is established for this path.
- [x] Package the user command and complete pinned fork, including ISC LICENSE/notices,
  all wrappers and relative `.exe` symlinks, both C++ helpers, Perl helpers, and all
  five `patches/` files (missing patches can silently skip). Keep packaged tools
  read-only under `/usr/share` or `/usr/lib`; download Microsoft payloads only as
  the user, never redistribute them or configure users from package functions.
- [x] Preflight non-root execution, required tools, and writable user-owned data/cache
  locations. Reject toolchain destinations containing whitespace before heavy work,
  since current wrappers cannot handle them; do not extend that restriction to cache
  or prefix paths without evidence.
- [x] Use these user-owned defaults:
  toolchain `${XDG_DATA_HOME:-$HOME/.local/share}/satisfactory-modding/msvc`;
  payload cache `${XDG_CACHE_HOME:-$HOME/.cache}/satisfactory-modding/msvc-wine`;
  dedicated Wine prefix `${XDG_DATA_HOME:-$HOME/.local/share}/satisfactory-modding/wineprefix`.
  Set the managed `WINEPREFIX` consistently for setup, wineboot, helper compilation,
  and later engine/launcher use; ensure x64 support and unattended initialization.
  Do not adopt, reset, or migrate `~/.wine` or another existing prefix.
- [x] Use deliberate ordinary-user invocation, normally `satisfactory-modding-setup
  --json`, to request installation under applicable Microsoft terms without prompts.
  Document terms URLs, not legal certification. Keep `--accept-msvc-license` as an
  optional compatibility no-op. Validated completed installations reuse the toolchain
  without downloading. Run these two stages, passing flags only to Python:
  `python3 SOURCE/vsdownload.py --dest DEST --cache CACHE --msvc-version 17.8 --sdk-version 10.0.22621 --channel release.ltsc.17.8 --accept-license`, then
  `bash SOURCE/install.sh DEST`. Bash is required despite the source's sh shebang.
- [x] Retain and recheck cached payload SHA values using explicit `--cache`; use the
  source's normal retries. Do not use `--only-download` as an integrity shortcut.
  Detect partial installs by artifacts, not exit status: license refusal and skipped
  helper compilation can return zero. Preserve unrecognized destinations and prior
  working installations; stage incomplete work if needed, without a transaction framework.
- [x] Validate and record the source pin, selection options, actual versions, and paths.
  Check `bin/x64/msvcenv.sh` against installed tools and requested MSVC 14.38 and
  SDK 10.0.22621.* families; source fallback/directory selection is not proof.
  Verify compiler, linker, SDK `rc.exe`, headers/libraries, wrapper aliases, and
  `bin/msvctricks.exe` plus `bin/process_sourcedependencies.exe` exist and execute.
  Declare completion only after validation, including section 5's smoke test;
  revalidate on repeat runs rather than redownloading a completed toolchain.
- [x] Only after toolchain validation, write
  `${XDG_CONFIG_HOME:-$HOME/.config}/satisfactory-modding/environment.sh`, exporting
  `UE_WINE_MSVC` as the toolchain root (not `bin/x64`) and the managed `WINEPREFIX`.
  Add one quoted, existence-guarded source entry to `$HOME/.unrealrc`, preserving
  content and avoiding duplicates. The engine reads home then CWD `.unrealrc`;
  preserve that intentional override hook. Do not edit project rc files, `.profile`,
  `/etc/environment`, or Rider configuration.
- [x] Provide a minimal wrapper that sources the same environment file and executes
  the supplied command/arguments for IDEs and tools outside the engine shell.
- [x] Skip registration if `/opt/unreal-engine-css` is already mapped; otherwise run
  `/opt/unreal-engine-css/Engine/Binaries/Linux/UnrealVersionSelector -register -unattended`
  as the user and verify the actual `[Installations]` mapping in
  `$HOME/.config/Epic/UnrealEngine/Install.ini` (not under `XDG_CONFIG_HOME`).
  Preserve unrelated mappings before/after the call, including temporarily missing
  paths: native enumeration prunes invalid entries, and return zero does not prove a write.
- [x] Keep pacman install/upgrade messages instruction-only. Removal must preserve
  user toolchains, caches, prefix, and configuration; no package-time Microsoft
  downloads, Wine initialization, or root-run user configuration.
  Suppress the conditional setup reminder only for a verified non-root
  account with a final configured marker and matching default-path static state.
  Unknown/custom-path/partial state keeps the reminder. Legacy markers remain reusable.
  Wine initialization now waits with `wineserver -w` before the win64 registry check.
  Pkgrel 3 prints the normal `satisfactory-modding-setup --json` command and terms notice.
  Document prerequisites, applicable terms, repeat runs, and removal in existing README/TODO.

## 4. Add release maintenance and installation documentation

- [ ] Implement a maintainer script that resolves the latest non-prerelease engine
  release using existing GitHub authentication.
- [ ] Select only `UnrealEngine-CSS-Editor-Linux.tar.zst.<numeric suffix>` assets,
  excluding debug archives, and validate a complete part sequence.
- [ ] Record the exact tag, asset identifiers, filenames, sizes, and SHA-256 digests.
  Fail if required integrity information is unavailable.
- [ ] Update pinned PKGBUILD inputs, `pkgver`, `pkgrel`, and `.SRCINFO`. Avoid network
  calls when sourcing the PKGBUILD or generating metadata.
- [ ] Provide a thin local bootstrap wrapper that updates the pinned recipe, then
  builds and installs the packages in dependency order and runs user setup.
- [ ] Document manual account-access and authentication prerequisites, required build
  tools, installation commands, source caching, applicable terms, and the optional
  compatibility flag.
- [ ] Document upgrades, repeat setup runs, package removal, and separately managed
  user toolchain state.
- [ ] Add package-source licensing and ignore downloaded archives, extracted trees,
  build outputs, caches, and credentials in version control.

## 5. Verify the first two packages

**Partial:** both recipes and `.SRCINFO` files now exist. The setup recipe passed
a normal local makepkg build, checksum/metadata/content/mode tests, Bash syntax,
and ShellCheck. The existing 32 engine tests remain unchanged; isolated setup
tests cover orchestration and preservation, not real Wine/MSVC. namcap's setup
recipe check had no findings; binary-package script-dependency and architecture
warnings are explained in the setup guide. The user confirms engine installation
and both engine registration-reminder paths. Clean-chroot, normal GUI, and full
two-package lifecycle checks below remain open. The user ran the installed CLI with
explicit consent, downloading/extracting 165 packages before the immediate Wine
prefix check failed, before wrapper installation. Later read-only inspection found
the managed registry was win64, with no promoted MSVC root. Asynchronous registry
flush is strongly inferred, not historically timed. Pkgrel 2 adds the server wait;
fixtures cover its order/failures and the read-only completion notice. No agent-run
Microsoft download, consent, or account setup occurred. The optional isolated Wine
probe was skipped. The user subsequently reports pkgrel 2 helper compilation and
compile/link/Windows-header/dependency/resource tests passed, with `status=complete`,
`reused=false`, and native registration already mapped. A second `--json` run returned
`reused=true`, already mapped, without downloads. Reported compiler 19.38.33145,
toolset directory 14.38.33130, and SDK 10.0.22621.0 reflect a legitimate servicing
difference. These runtime checks were not independently rerun. The setup notice on
an actual reinstall remains unverified; only its fixtures were run. Recovery with
`satisfactory-modding-setup --json` reuses the persistent SHA cache with a fresh stage,
leaving the old stage untouched; manifest fetches mean recovery is not guaranteed offline.

- [ ] Run Bash syntax checks and ShellCheck on the PKGBUILDs and helper scripts.
- [ ] Generate and validate `.SRCINFO` for both package recipes.
- [ ] Run namcap on the recipes and built packages; investigate relevant findings.
- [ ] Build both packages in a clean Arch chroot using pre-fetched private assets.
- [ ] Verify checksums, package file ownership, permissions, and declared dependencies.
- [ ] Test rejection of missing access, missing archive parts, and corrupted downloads.
- [x] Install both packages and complete setup as an ordinary user (user-reported).
- [x] Run setup again to verify repeatability and preservation of existing configuration
  (user-reported reuse without downloads; isolated preservation tests).
- [x] Perform an MSVC compile/link smoke test using the installed Wine-backed tools,
  exercising a Windows SDK header and checking dependency-helper output (section 3,
  user-reported, not independently rerun).
- [ ] Check bundled .NET and UnrealBuildTool startup and launch the engine on a
  suitable graphical system. Confirm required engine writes work without root.
  An isolated Xvfb/NullRHI startup failed with no usable default DDC cache nodes
  and failed Zen startup. Its cause is unknown in that limited environment.
  Verify normal startup with usable user-owned cache state; the isolated failure
  does not establish normal GUI behavior.
- [ ] Identify additional engine-local writes during startup and build-tool use.
  Handle required writable state specifically, without making the engine tree
  broadly writable. Full editor startup and project builds remain untested.
- [ ] Test upgrade and removal behavior, including preservation of user-owned data.
- [ ] Record commands, observed results, and any remaining verification gaps.

### Completion criteria

- [ ] Both packages build and install with normal Arch tooling.
- [ ] Engine inputs are pinned and verified, and authenticated downloads work.
- [ ] The user setup command installs the required MSVC/SDK selection, configures
  `UE_WINE_MSVC`, and registers the engine on intentional user invocation without
  interactive prompts, under applicable Microsoft terms.
- [ ] Repeat setup and normal package lifecycle operations preserve unrelated user state.
- [ ] Documentation provides a tested path from granted repository access to the
  beginning of **Project Setup**.

## Future

### AUR publishing

After the first two packages meet their completion criteria:

- [ ] Recheck package-name availability and review the current
  [Arch package guidelines](https://wiki.archlinux.org/title/Arch_package_guidelines),
  [nonfree application guidelines](https://wiki.archlinux.org/title/Nonfree_applications_package_guidelines),
  and [AUR submission guidelines](https://wiki.archlinux.org/title/AUR_submission_guidelines).
- [ ] Prepare separate AUR package repositories with current `.SRCINFO`, maintainer
  information, package-source licensing, and required helper files.
- [ ] Document authenticated downloads and license requirements on the package pages.
- [ ] Publish package recipes and helper sources, excluding engine archives, Microsoft
  toolchains, generated binary packages, and credentials.
- [ ] Establish a reviewed release-update process and a process for handling feedback.

### `satisfactory-modding-project-setup` with Rider

Assess feasibility only after the first two packages are complete. This third
package would assist with or automate **Project Setup**, using Rider as the IDE.

- [ ] Recheck the current guide and define the third package's scope and completion
  criteria before deciding which steps to automate.
- [ ] Assess obtaining a compatible Starter Project without overwriting user work.
- [ ] Assess installing the required `wwise-cli`, Wwise SDK, and Authoring components,
  including license/account requirements and unattended operation.
- [ ] Assess Wwise Unreal integration, Wwise project creation, and sound-bank generation;
  identify steps that still need a graphical application or user input.
- [ ] Assess Rider setup, preferred `.uproject` opening, the required Mods project-model
  plugin, bundled .NET configuration, and any current engine/build-tool workarounds.
- [ ] Assess project compilation and first editor launch, including generated
  sound-bank path configuration.
- [ ] Determine which operations belong in the package and which belong in a user-run,
  project-scoped command. Define how existing projects and IDE settings are preserved.
- [ ] Document the feasibility findings, remaining manual steps, dependency choices,
  and proposed verification plan.
- [ ] Implement `satisfactory-modding-project-setup` after the feasible approach and
  scope have been agreed.
