# satisfactory-modding-setup

This package provides two commands:

- `satisfactory-modding-setup` installs the MSVC compiler and Windows SDK under
  Wine for your user, registers the engine, and writes the environment the engine
  needs to build mods. Run it yourself; package installation never runs it.
- `satisfactory-modding-run` runs any command, such as your IDE, with that
  environment.

It covers the guide up to, but not including, **Project Setup**. Most people get it
through [bootstrap](../../README.md). This page covers building it by hand and
what setup does.

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
satisfactory-modding-setup
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
satisfactory-modding-run /path/to/your/ide
satisfactory-modding-run /opt/unreal-engine-css/Engine/Binaries/Linux/UnrealEditor
```

It loads the environment file and runs the command with your arguments as given.
It exits 1 if setup has not run, 2 if no command is given, and otherwise with the
command's own exit status.

## Exit status and output

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

## License

The setup scripts are [ISC](LICENSE), as is the bundled `msvc-wine` snapshot.
Both notices are installed under `/usr/share/licenses/satisfactory-modding-setup/`.
The Microsoft tools that setup downloads keep their own terms.
