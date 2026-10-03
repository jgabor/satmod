# satisfactory-modding-setup

An Arch package with a noninteractive, **user-run** MSVC/SDK installer and a
minimal environment launcher. It stops before Project Setup. AUR publication,
release maintenance, and bootstrap automation are deferred.

## Build and install

Install the [engine package](../unreal-engine-css-bin/README.md) first. The existing
`5.6.1.css83-3` installation does not need a rebuild. Account creation, linking,
repository grants, and GitHub authentication remain manual prerequisites for the
engine. This setup recipe uses only a small public source archive, not Microsoft
payloads. Build as an ordinary user with Arch's `base-devel` tools:

```sh
cd packages/satisfactory-modding-setup
makepkg -s
# Optional installation, performed by you:
sudo pacman -U satisfactory-modding-setup-1.0.0-3-x86_64.pkg.tar.zst
```

Runtime dependencies include Python, msitools (and its gcab dependency), Wine,
Git, Perl, Bash, CA trust, and ordinary Arch utilities. tar/zstd and dos2unix
retain the guide's tool list, although dos2unix is for later project patches.
No pip modules, native C++ compiler, Mono/Gecko, Samba, or unzip are required.

The complete ISC-licensed `mircearoata/msvc-wine` source is pinned to
`61b7cbc8cb9413fec8f0016ef433a90e06c37f54`. It includes the wrappers and relative
`.exe` aliases, Perl scripts, both helper sources, and all five patches. Package
files live under `/usr/share/satisfactory-modding-setup`; the package distributes
**no Microsoft toolchain payloads**. ISC covers the setup code and upstream
scripts, not the downloaded tools. Notices are under `/usr/share/licenses`.

For offline builds, set `SRCDEST` to a directory containing the checksum-pinned
`msvc-wine-61b7cbc8cb9413fec8f0016ef433a90e06c37f54.tar.gz`. The local verification
archive is in `../../.cache/upstream/msvc-wine/` (46,445 bytes). makepkg checks
both this archive and local command/license checksums.

## Run setup yourself

Run this command as your ordinary user for both first installation and repeat setup:

```sh
satisfactory-modding-setup --json
```

Deliberately invoking setup requests installation of Microsoft MSVC/Windows SDK
tools under the applicable Microsoft license terms. Read the
[Visual Studio terms](https://visualstudio.microsoft.com/license-terms/) and
[Windows SDK information and terms](https://developer.microsoft.com/windows/downloads/windows-sdk/).
These links are notices, not legal certification. Setup never prompts.
`--accept-msvc-license` remains an optional compatibility flag; it is not required
and has no effect. `--json` is also optional; without it, setup prints a human-readable summary.

Pacman hooks do not run this command. They only read small completion records and
print conditional instructions. The reminder is suppressed only for a verified
non-root `SUDO_USER` account with completed setup at default HOME data/config paths,
matching environment and home hook, engine registration, and required artifacts.
Unknown accounts, custom XDG or toolchain/prefix paths, old markers, and missing,
unreadable, or corrupt state retain the reminder. The hook ignores root's HOME/XDG
defaults, never sources user files, and does not perform runtime validation.
This is a best-effort reminder, not a security boundary or a runtime health check.

Defaults (empty XDG variables also fall back to HOME):

| State | Default |
| --- | --- |
| Toolchain root | `${XDG_DATA_HOME:-$HOME/.local/share}/satisfactory-modding/msvc` |
| Persistent payload cache | `${XDG_CACHE_HOME:-$HOME/.cache}/satisfactory-modding/msvc-wine` |
| Dedicated Wine prefix | `${XDG_DATA_HOME:-$HOME/.local/share}/satisfactory-modding/wineprefix` |
| Managed environment | `${XDG_CONFIG_HOME:-$HOME/.config}/satisfactory-modding/environment.sh` |
| Native engine registration | `$HOME/.config/Epic/UnrealEngine/Install.ini` (not XDG_CONFIG_HOME) |

Use `--toolchain PATH`, `--cache PATH`, or `--wineprefix PATH` to change installation
locations. These must be separate, writable user-owned locations. **The toolchain
path cannot contain whitespace**, including its parent directories, because of
upstream wrapper bugs. Cache and prefix paths can contain spaces. Choose a
no-space `--toolchain` if your home or XDG data directory contains spaces.
Keep the same locations when repeating setup.

The dedicated prefix is marked as managed and initialized for win64. Setup refuses
unmanaged existing prefixes and never adopts, resets, or migrates `~/.wine`.
It overrides inherited `WINEPREFIX`/`WINEARCH`, ignores shell startup files for
setup subprocesses, and disables Mono/Gecko prompts during Wine initialization.
It runs `wine wineboot -u`, then `wineserver -w` with the same managed environment
before checking the win64 registry. The wait lets Wine flush its registry files;
the win64 requirement is unchanged.
The managed environment exports the toolchain **root** as `UE_WINE_MSVC`, along
with `WINEPREFIX` and `WINEARCH=win64` for the engine and launcher.

Setup runs two separate upstream stages:

1. `python3 SOURCE/vsdownload.py --dest STAGE --cache CACHE --msvc-version 17.8 --sdk-version 10.0.22621 --channel release.ltsc.17.8 --accept-license`
2. `bash SOURCE/install.sh STAGE`

Python always receives the selection flags and upstream `--accept-license` for a
new installation; Bash receives only the destination.
The explicit cache retains upstream SHA checks and retries. No `--only-download`
shortcut is used. The source pin does not freeze mutable Microsoft manifests.

Setup verifies the selected MSVC 14.38 and SDK 10.0.22621 families, generated paths,
compiler/linker, SDK tools/headers/libraries, aliases, and both helper executables.
It compiles a Windows-header smoke source with `/sourceDependencies`, verifies
usable Unix dependency paths, links it, and compiles an SDK resource through the
actual wrappers. It does not build a project or run the resulting Windows program.
An upstream zero exit alone cannot establish completion.

## Repeat runs and configuration

```sh
satisfactory-modding-setup --json
satisfactory-modding-run /path/to/your/IDE 'argument with spaces'
satisfactory-modding-run /opt/unreal-engine-css/Engine/Binaries/Linux/UnrealEditor
```

A completed installation is revalidated, including smoke tests, without redownloading.
A simple toolchain marker records the source pin,
requested selection, actual versions, and paths. It is retry bookkeeping, not
tamper protection or a Microsoft manifest certification.
The marker gains a `configured` home/environment record only after registration
and configuration succeed. Valid pkgrel 1 markers remain reusable and gain this
record on a successful rerun. A failed registration/configuration rerun leaves no
configured record, so it cannot suppress the reminder.

New installs use a sibling staging directory. Failed stages remain for inspection;
retry creates a fresh stage and reuses the payload cache. Unrecognized destinations
and broken previously completed installations are preserved, never overwritten.
Repair them explicitly or choose a new toolchain path; do not delete a working
toolchain just to retry registration. Successful promotion is revalidated at the
final path before the toolchain marker is written; full configuration is recorded
after registration and the environment/home hook are written.

After validation, setup registers the engine if needed, verifies the actual native
mapping, and merges it with prior mappings, including paths that the selector
prunes because they are temporarily absent. On registration failure it restores
the original INI bytes. Registration retries reuse a completed toolchain.

Setup writes a mode-600 environment file and one quoted, existence-guarded managed
entry in `$HOME/.unrealrc`. It preserves other home rc content. The engine's later
CWD `.unrealrc` remains an intentional override; setup does not change it, `.profile`,
system configuration, or Rider settings. The launcher sources the managed file
using the current XDG_CONFIG_HOME and `exec`s your exact argv, preserving the command's
exit status and signal behavior. Normal Bash startup settings still apply to the launcher.

Both commands support `--help` without prompting. Setup emits diagnostics and child
logs on stderr and one success summary on stdout; `--json` selects a JSON object
with `status`, `reused`, paths, versions, source pin, and registration status.
Setup exits 0 on success, 1 on setup/preflight failures, and 2 on invalid arguments.
The launcher exits 1 for a missing environment, 2 for a missing command, or the
executed command's status (Bash uses 126/127 for execution errors).

Upgrades do not run setup automatically. Removing the package leaves all user
toolchains, caches, prefixes, markers, and configuration intact. Remove those
separately only if you no longer need them. The existence guard keeps a stale
managed home hook harmless if you remove its environment file.

## Verification and limits

From the checkout root:

```sh
python3 -m unittest discover -s tests -v
python3 tests/test-engine-download.py -v
bash -n packages/satisfactory-modding-setup/{PKGBUILD,satisfactory-modding-run,satisfactory-modding-setup.install}
shellcheck -s bash packages/satisfactory-modding-setup/{PKGBUILD,satisfactory-modding-run,satisfactory-modding-setup.install}
```

The tests use temporary HOME directories, minimal fake SDK artifacts, fake wrappers,
and a fake selector. They do not download Microsoft payloads or run real Wine.
The package-content test uses the pinned small public archive and skips if it is
absent. Local development invokes the new file, for example
`python3 packages/satisfactory-modding-setup/satisfactory-modding-setup --help`,
not an installed command. Its source is located beside the Python file in a built
package; use package staging when testing the real packaged source layout.

The local normal makepkg build passed dependency and integrity checks without
`--nodeps`. Package ownership, modes, full source contents, and metadata parity were
checked. namcap's recipe check had no findings. Its binary-package warnings reflect
the x86_64 setup contract without ELF payloads and incomplete detection of script
runtime dependencies (including `/usr/bin/env` interpreters on this host); the
declared tools were checked by makepkg and remain required.

The user ran the installed pkgrel 1 CLI with explicit consent: 165 Microsoft
packages (about 1.5 GB downloaded, 5.1 GB extracted) reached a preserved stage,
then the immediate Wine prefix check failed before wrapper installation. A later
read-only inspection found `system.reg` with `#arch=win64` and the expected managed
prefix marker, but no promoted toolchain. An asynchronous registry flush is the
strong inference, not a proven measurement of the original failure timing.
Pkgrel 2 waits for the Wine server before checking the registry.

For recovery after installing the update yourself, run
`satisfactory-modding-setup --json`. It reuses the
persistent SHA-checked cache and creates a new stage; the old failed stage stays
untouched. This is not guaranteed offline because manifest fetches may still occur.

The user reports that pkgrel 2 subsequently compiled both SDK helpers and passed
compile/link, Windows header, dependency-output, and resource tests. Setup returned
`status=complete`, `reused=false`, and an already-mapped native engine registration.
A second `--json` run returned `reused=true`, again already mapped, without downloading.
Reported versions were compiler 19.38.33145, toolset directory 14.38.33130, and SDK
10.0.22621.0; the compiler/toolset servicing difference is legitimate. These runtime
results were not independently rerun here.

No agent-run Microsoft download, license acceptance, or account setup was performed.
The optional isolated Wine probe was skipped; Wine wait is fixture-tested here.
**Normal engine GUI startup, clean-chroot build, full package lifecycle verification,
and the setup notice on an actual reinstall remain unverified.** The notice is
fixture-tested only. See
[TODO.md](../../TODO.md) and [input pins](../../upstream-inputs.json).
