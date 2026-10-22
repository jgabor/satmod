# Satisfactory modding on Linux

Two **Arch Linux x86_64** packages that automate the
[Linux setup guide](https://docs.ficsit.app/satisfactory-modding/latest/Development/Linux/LinuxSetup.html)
through command-line **Project Setup**:

- [unreal-engine-css-bin](packages/unreal-engine-css-bin/README.md) packages the
  prebuilt Coffee Stain Studios (CSS) Unreal Engine under `/opt/unreal-engine-css`.
- [satisfactory-modding-setup](packages/satisfactory-modding-setup/README.md)
  adds `satisfactory-modding setup`, which installs the MSVC toolchain and Windows
  SDK under Wine for your user and registers the engine, and
  `satisfactory-modding run`, which runs a command (such as your IDE) with that
  environment. `satisfactory-modding doctor` checks the installation.

## Quick start

1. Install the build tools:

   ```sh
   sudo pacman -S --needed base-devel github-cli python
   ```

2. Set up your accounts. These steps are manual:
   - Link your Epic Games account to your GitHub account.
   - Request access to `satisfactorymodding/UnrealEngine`.
   - Run `gh auth login`.
   - Create an [Audiokinetic account](https://www.audiokinetic.com/). You need
     it later to download Wwise with `wwise-cli`.

   The [setup guide](https://docs.ficsit.app/satisfactory-modding/latest/Development/Linux/LinuxSetup.html)
   explains each step.

3. Run bootstrap from this checkout **as your ordinary user**, not with `sudo`:

   ```sh
   ./scripts/bootstrap
   ```

Bootstrap asks for your sudo password once at the start, and again only if the
build outlasts sudo's timeout. It adds you to the `unreal-engine-css` group, which
can write to the engine. If it tells you to, **log out and back in** before you
continue. Initialize your project next. See [Next: Project Setup](#next-project-setup).

Running bootstrap downloads Microsoft build tools. See
[Licenses and terms](#licenses-and-terms) first.

### Disk space and time

- Building the engine needs about **48 GB** free on the filesystem that holds this
  checkout, since bootstrap builds under `.cache/`. The installed engine takes
  about **30 GB** under `/opt`.
- The Microsoft toolchain download was about **1.5 GB** (5.1 GB extracted) in one
  run. Sizes vary.
- The first run downloads about 8 GB of engine archives and takes a long time. If
  you stop bootstrap, run it again: finished downloads and packages are reused.
- `project init` needs about **15 GB** more: roughly 1.5 GB for the clone, 7 GB for
  the Wwise download cache, and 7 GB for the integrated Wwise plugin. One run
  took about five minutes on a fast connection.
- A `project update` that changes the Wwise version needs about **7 GB** more for
  the new Wwise caches. The new plugin replaces the old one, so it needs no
  extra space. The old caches stay until you remove them.

## What bootstrap does

1. Updates the engine pins to the latest CSS release with
   `scripts/update-engine-release`. A new release changes tracked files, so
   `git status` shows them as modified.
2. Builds each package with `makepkg`, unless a matching package is already in
   `.cache/`.
3. Installs the engine, then the setup package, with `sudo pacman -U`.
4. Adds you to the `unreal-engine-css` group with `sudo gpasswd`, if you are not
   already a member.
5. Runs `satisfactory-modding setup` as your user.

Unreal's build tools write into the engine folder, so the engine package makes
`/opt/unreal-engine-css` writable for the `unreal-engine-css` group. The
[engine guide](packages/unreal-engine-css-bin/README.md#engine-write-access) has
the details.

Run bootstrap again to upgrade. Add `--json` for machine-readable output.
[scripts/README.md](scripts/README.md) has the details.

To check for a new engine release without changing anything:

```sh
./scripts/update-engine-release --check
```

To rerun only the toolchain setup:

```sh
satisfactory-modding setup
```

Run `satisfactory-modding doctor` to check engine access, registration, and the
managed environment when troubleshooting. It does not change files or start Wine.

The package guides cover manual builds. Package install hooks print reminders,
and the engine hook also creates the `unreal-engine-css` group and gives it the
engine files. Hooks never download tools, set up Wine, or change your account.

## Next: Project Setup

After toolchain setup, run:

```sh
satisfactory-modding project init ~/git/SatisfactoryModLoader
```

This clones the Starter Project, downloads the pinned wwise-cli and Wwise SDK,
integrates Wwise, creates the Wwise project and Windows soundbanks under Wine,
and sets audio routing. Only the Audiokinetic login needs input. For unattended
runs, set `WWISE_EMAIL` and `WWISE_PASSWORD` in the environment; `WWISE_USER` and
`WWISE_PASS` work too. Reruns skip completed steps. See the [command details](packages/satisfactory-modding-setup/README.md#initialize-a-project)
for cache paths, version pins, and `--wwise-cli` and `--json` options.

When upstream SML moves on, `satisfactory-modding project update
~/git/SatisfactoryModLoader` fast-forwards the project and updates Wwise to the
versions the new commit needs. It stops without changing anything if you have
local commits or changes of your own. See [update a project](packages/satisfactory-modding-setup/README.md#update-a-project).

Install Rider's **Unreal Project Model Mods Fix** plugin, then open the project:

```sh
satisfactory-modding run rider ~/git/SatisfactoryModLoader/FactoryGame.uproject
```

Compile with **Development**, **Editor**, and **Linux** selected, then open the
editor. `mod new` and `mod build` can create and package mods from the CLI.
The engine package already omits LiveLinkHub. The guide's optional BuildUBT.sh
patch is not applied and was not needed in the verified manual build.

Manual fallback: follow the guide's
[Project Setup](https://docs.ficsit.app/satisfactory-modding/latest/Development/Linux/LinuxSetup.html).
Clone the Starter Project, run wwise-cli download and integrate-ue, create
`SatisfactoryModLoader_WwiseProject` in Wwise Authoring, and generate Windows
soundbanks. In the editor, set Root Output Path to
`../SatisfactoryModLoader_WwiseProject/GeneratedSoundBanks` and audio routing to
**Both Wwise and Unreal audio**. Keep the local `Config/DefaultGame.ini` change
out of commits sent upstream. The manual path has been verified end to end
and is in daily use for mod development. The CLI path ran for real on an
empty directory and matched the manual result.

If Rider shows **Project 'Engine' load failed** with a permission error in its
UnrealBuildTool log, you are not in the `unreal-engine-css` group yet, or you have
not logged in again since joining. Check with `id` and `satisfactory-modding doctor`.

## Build mods from the command line

After Project Setup, run from the Starter Project:

```sh
satisfactory-modding mod new MyMod --cpp
satisfactory-modding mod build MyMod
```

`mod new` creates a library mod from Alpakit's templates; omit `--cpp` for
Blueprint only. Game-feature creation still needs the editor. `mod build`
builds and packages a Windows client mod and copies it into the Steam install,
which it detects automatically. Use `--game DIR` to choose the game directory,
or `--no-copy` to package only. Both commands accept `--project PATH` and
`--json`. Archives land in `Saved/ArchivedPlugins/REF/REF-Windows.zip`.
See the [CLI documentation](packages/satisfactory-modding-setup/README.md#create-a-library-mod)
for options, outputs, and limits. Both commands were tested on a real Starter
Project: `mod new --cpp` followed by `mod build` compiled, packaged, and copied a
new mod into the game, which loaded it, without opening the editor.

SML requires a mod on every player's game unless its descriptor sets
`RequiredOnRemote` to false. A test mod left in `FactoryGame/Mods` therefore keeps
friends without it from joining your session. Delete the mod's folder there when
you are done testing.

## Licenses and terms

- The engine is subject to the
  [Unreal Engine EULA](https://www.unrealengine.com/eula). Access to the source
  repository does not give you the right to redistribute it, so do not publish
  built engine packages.
- `satisfactory-modding setup` downloads Microsoft tools under the
  [Visual Studio terms](https://visualstudio.microsoft.com/license-terms/) and the
  [Windows SDK terms](https://developer.microsoft.com/windows/downloads/windows-sdk/).

## Uninstall

```sh
sudo pacman -Rns satisfactory-modding-setup unreal-engine-css-bin
```

To keep the engine, remove only `satisfactory-modding-setup`.

Removing the packages leaves your toolchain, download cache, Wine prefix,
environment file, `~/.unrealrc` entry, and engine registration in place. The
[setup guide](packages/satisfactory-modding-setup/README.md#remove-user-data)
lists them.

## Development

Run the tests from the repository root. They use fake tools and temporary
directories, so they need no GitHub access and download nothing:

```sh
python3 -m unittest discover -s tests
```

Real runs of `project init` need the Audiokinetic login. Copy `.env.example` to
`.env`, fill it in, and load it with `set -a; . ./.env; set +a`. Git ignores
`.env`, and the tests never read it.

[TODO.md](TODO.md) tracks open verification work.

## License

The [ISC license](LICENSE) covers only the original recipes, scripts, tests, and
documentation in this repository. The Unreal Engine, Microsoft tools, and
upstream files keep their own terms.
