# satisfactory-modding-setup

This package provides one CLI, `satisfactory-modding`, with these commands:

- `satisfactory-modding setup` installs the MSVC compiler and Windows SDK under
  Wine for your user, registers the engine, and writes the environment the engine
  needs to build mods. Run it yourself; package installation never runs it.
- `satisfactory-modding run` runs any command, such as your IDE, with that
  environment.
- `satisfactory-modding mod new` creates a library mod from Alpakit templates.
- `satisfactory-modding mod build` builds and packages a Windows client mod,
  then optionally copies it into the game.
- `satisfactory-modding doctor` checks the installation without changing files,
  downloading anything, starting Wine, or running smoke tests.

The toolchain wrappers pin the managed Wine prefix and ignore `BASH_ENV` for
their child processes, so a `WINEPREFIX` set in shell startup files does not leak
into builds. Rerun `satisfactory-modding setup` to apply this fix to an existing
toolchain.

It covers the guide up to, but not including, **Project Setup**. Most people get it
through [bootstrap](../../README.md). This page covers building it by hand and
what setup does and how to create and build mods after Project Setup.

## Build and install

Install the [engine package](../unreal-engine-css-bin/README.md) first. Then build
and install this package as your ordinary user:

```sh
cd packages/satisfactory-modding-setup
makepkg -si
```

`makepkg -s` installs the dependencies, including Wine, msitools, and Python. The
build downloads only a small, checksum-pinned snapshot of
[`mircearoata/msvc-wine`](https://github.com/mircearoata/msvc-wine/tree/61b7cbc8cb9413fec8f0016ef433a90e06c37f54)
(see [upstream-inputs.json](../../upstream-inputs.json)). The package contains no
Microsoft files.

## Run setup

Run as your ordinary user, not with `sudo`:

```sh
satisfactory-modding setup
```

This downloads Microsoft tools under the
[Visual Studio terms](https://visualstudio.microsoft.com/license-terms/) and the
[Windows SDK terms](https://developer.microsoft.com/windows/downloads/windows-sdk/).
Setup never prompts. Add `--json` to print a JSON summary instead of one line.

Setup:

1. Downloads MSVC 14.38 and Windows SDK 10.0.22621 from the Visual Studio 17.8
   LTSC channel, using a persistent download cache.
2. Creates a dedicated 64-bit Wine prefix. It never uses or changes `~/.wine`.
3. Installs the toolchain into a staging directory, checks that the expected
   files exist, and compiles, links, and builds a resource file as a smoke test.
   Only then does it move the toolchain into place.
4. Registers `/opt/unreal-engine-css` with the engine, unless it is already
   registered. Your other engine registrations are kept.
5. Writes an environment file that exports `UE_WINE_MSVC`, `WINEPREFIX`, and
   `WINEARCH`, and adds one line to `~/.unrealrc` that loads it. The engine's
   Linux scripts read `~/.unrealrc`, then any `.unrealrc` in the current
   directory. Setup leaves the second one alone.

Run setup again at any time. A finished install is checked again, smoke tests
included, without downloading. If a run fails, run it again: the failed staging
directory (`.msvc-stage-*`, next to the toolchain) is left for inspection, and the
next run starts a fresh one that reuses the download cache. Nothing deletes failed
staging directories, and each can take several GB, so remove them once you are done
with them. Microsoft's manifests are fetched again, so a retry is not
fully offline.

## Locations

| What | Default | Option |
| --- | --- | --- |
| Toolchain | `${XDG_DATA_HOME:-~/.local/share}/satisfactory-modding/msvc` | `--toolchain` |
| Download cache | `${XDG_CACHE_HOME:-~/.cache}/satisfactory-modding/msvc-wine` | `--cache` |
| Wine prefix | `${XDG_DATA_HOME:-~/.local/share}/satisfactory-modding/wineprefix` | `--wineprefix` |
| Environment file | `${XDG_CONFIG_HOME:-~/.config}/satisfactory-modding/environment.sh` | none |
| Engine registration | `~/.config/Epic/UnrealEngine/Install.ini` | none |
| Engine hook | one line in `~/.unrealrc` | none |

If you change a location, pass the same options on every later run. The three
locations must be separate, user-owned, and writable.

**The toolchain path must not contain spaces**, including its parent directories,
because the upstream wrappers cannot handle them. If your home directory has a
space in it, pass a `--toolchain` path without one.

Setup refuses to overwrite a toolchain directory it did not create, or a
non-empty Wine prefix it did not create. To start over, move or delete the old
directory, or choose another path.

## Run other tools with the environment

The engine loads the environment through `~/.unrealrc`. For tools started
outside the engine, such as an IDE, use the launcher:

```sh
satisfactory-modding run /path/to/your/ide
satisfactory-modding run /opt/unreal-engine-css/Engine/Binaries/Linux/UnrealEditor
```

It loads the environment file and runs the command with your arguments as given.
It exits 1 if setup has not run, 2 if no command is given, and otherwise with the
command's own exit status.

Use `satisfactory-modding run --help` for help. To run a command named `--help`,
use `satisfactory-modding run -- --help`. Arguments after the command pass through
unchanged, including spaces and quotes. Bash sources the environment file before
replacing itself with the command, so signals pass through too.

## Check the installation

```sh
satisfactory-modding doctor
satisfactory-modding doctor --json
```

Doctor checks:

- `engine`: the engine directory exists.
- `engine-group`: this process can write to the engine. A failure distinguishes
  missing group membership from a login that needs to be refreshed.
- `registration`: `Install.ini` maps the packaged engine.
- `environment`: the environment file has the exact managed format. Doctor reads
  custom toolchain and Wine prefix paths from it.
- `toolchain`: the completion marker matches the source pin and paths, and the
  managed `msvcenv.sh` block pins the same prefix. Run `satisfactory-modding setup`
  for full revalidation and smoke tests.
- `unrealrc`: the managed hook is present in `~/.unrealrc`.
- `wineprefix-env`: warns if `WINEPREFIX` differs or `BASH_ENV` is set. Wrappers
  pin the managed prefix, but other tools outside `satisfactory-modding run`
  may use the wrong one.

Each check prints one line with its id, `ok`, `warn`, or `fail`, and a message
with a fix when needed. JSON has `status` (`ok` or `fail`) and a `checks` array;
each check has `id`, `status`, and `message`. Doctor exits 1 if any check fails,
and 0 otherwise, including when there are only warnings.

## Exit status and output

A bare `satisfactory-modding` prints help and exits 2. Use `--help` on the CLI or
any subcommand for help.

Setup exits 0 on success, 1 on failure, and 2 on invalid arguments. Progress and
errors go to stderr. On success it prints one summary to stdout. The `--json`
summary includes `status`, `reused`, the paths, the installed `versions`, the
`source_pin`, and `registration` (`registered` or `already-registered`).

## Remove user data

Removing or upgrading the package never touches user data. To remove it by
hand, delete the toolchain, download cache, Wine prefix, and environment file
listed under [Locations](#locations), any `.msvc-stage-*` directories next to the
toolchain, and the line ending in
`# satisfactory-modding-setup` in `~/.unrealrc`. If you only delete the
environment file, that line does nothing. Keep the engine registration in
`Install.ini` unless you also remove the engine.

## Create a library mod

After completing Project Setup, run from the Starter Project or one of its
subdirectories:

```sh
satisfactory-modding mod new MyMod
satisfactory-modding mod new MyCppMod --cpp
```

`REF` is the permanent mod reference. Use only letters, digits, and underscores.
Unreal mount point names (`Game`, `Engine`, `Script`, `Memory`, `Temp`, `Config`)
and existing plugin names are reserved. The command refuses an existing mod
directory or a plugin with the same name anywhere in the project.

The default is Alpakit's **Blueprint Library (Advanced)** template,
`Mods/Alpakit/Templates/BlueprintBlank`. `--cpp` selects **C++ & Blueprint
Library (Advanced)**, `CPPAndBlueprintBlank`. Templates are read from your
project's Alpakit plugin, including when it is under `Plugins` or a configured
additional plugin directory. The command creates `Mods/REF`, replaces
`PLUGIN_NAME` in paths and text, creates an empty `Content` directory, and writes
`REF.uplugin`. The C++ module uses `Runtime` and `Default`, with uppercase API
macros. The editor or `satisfactory-modding mod build REF` compiles its source.
Creation uses a temporary sibling directory and a rename; failures remove the
staging directory instead of leaving a partial mod.

The descriptor follows the wizard defaults: version and semantic version
`1.0.0`, category `Modding`, content enabled, and SML enabled with `^` followed
by the project's SML `VersionName`. Its game constraint is `>=` followed by
`Source/FactoryGame/currentVersion.txt`. The friendly name is `REF`. Description,
author, author URL, and documentation/support/marketplace URLs have no supplied
values, so they are empty; beta, experimental, and installed flags are false.
The template icon, or Alpakit's default icon when available, is copied intact.
The command does not change the project descriptor.

Only library mods are supported. Game-feature mods require a binary
`GameFeatureData` asset created by the Unreal Editor. This command does not
create or fix up Unreal assets.

## Build a mod

```sh
satisfactory-modding mod build MyMod
satisfactory-modding mod build MyMod --no-copy
satisfactory-modding mod build MyMod --project ~/git/SatisfactoryModLoader --game /path/to/Satisfactory
```

Both commands accept `--project PATH`, either a `.uproject` file or its directory.
Without it, they search the current directory and its parents for
`FactoryGame.uproject`. Build discovers plugins recursively in `Mods`, `Plugins`,
and the project's `AdditionalPluginDirectories`, including game-feature mods.

Build first compiles the project's Linux editor target (for the Starter Project,
`FactoryEditor Linux Development`) with the engine's `Linux/Build.sh`, the same
build Rider runs. Packaging cooks the mod in the Linux editor, which needs the
mod's editor module, so a new C++ mod fails to cook without this step. When
nothing changed, it finishes in seconds.

Then build uses `/opt/unreal-engine-css/Engine/Build/BatchFiles/RunUAT.sh` and Alpakit's
`PackagePlugin` command with `Shipping` client/server configuration, `Win64`,
`-build`, `-nocompileeditor`, and `-installed`. Only the Windows client is built
for now. It sources the managed environment file written by
`satisfactory-modding setup`, with `BASH_ENV` and `ENV` removed before starting
bash. Child stdin is `/dev/null`; environment diagnostics and UAT logs go to
stderr.

By default, build detects Steam app 526870 through `libraryfolders.vdf` and
`appmanifest_526870.acf`, starting from `~/.local/share/Steam` and `~/.steam/steam`.
It supports multiple libraries. `--game DIR` overrides discovery. `--no-copy`
skips discovery and copying; it cannot be combined with `--game`. If discovery
fails, supply either option explicitly.

Alpakit writes `Saved/ArchivedPlugins/REF/REF-Windows.zip` under the project.
Copying targets `GAME/FactoryGame/Mods/REF`, or
`GAME/FactoryGame/Mods/GameFeatures/REF` for game-feature mods. Alpakit replaces
an existing game mod folder. The success summary reports only output paths
that exist after UAT finishes. A failed UAT returns exit 1 and reports its exit
code on stderr, without a success summary.

Both commands print one human summary line, or one JSON object with `--json`.
Build JSON has `status`, `mod`, `project`, `outputs` (an array of existing archive
paths), and `game_mod` (an existing copied directory or `null`). New JSON has
`status`, `mod`, `project`, `path`, and `cpp`. Exit codes are 0 for success,
1 for a failed operation, and 2 for bad arguments.

## License

The setup scripts are [ISC](LICENSE), as is the bundled `msvc-wine` snapshot.
Both notices are installed under `/usr/share/licenses/satisfactory-modding-setup/`.
The Microsoft tools that setup downloads keep their own terms.
