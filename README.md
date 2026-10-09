# Satisfactory modding on Linux

Two **Arch Linux x86_64** packages that automate the
[Linux setup guide](https://docs.ficsit.app/satisfactory-modding/latest/Development/Linux/LinuxSetup.html)
up to, but not including, **Project Setup**:

- [unreal-engine-css-bin](packages/unreal-engine-css-bin/README.md) packages the
  prebuilt Coffee Stain Studios (CSS) Unreal Engine under `/opt/unreal-engine-css`.
- [satisfactory-modding-setup](packages/satisfactory-modding-setup/README.md)
  adds `satisfactory-modding-setup`, which installs the MSVC toolchain and Windows
  SDK under Wine for your user and registers the engine, and
  `satisfactory-modding-run`, which runs a command (such as your IDE) with that
  environment.

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
continue. The remaining steps are manual. See [Next: Project Setup](#next-project-setup).

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

## What bootstrap does

1. Updates the engine pins to the latest CSS release with
   `scripts/update-engine-release`. A new release changes tracked files, so
   `git status` shows them as modified.
2. Builds each package with `makepkg`, unless a matching package is already in
   `.cache/`.
3. Installs the engine, then the setup package, with `sudo pacman -U`.
4. Adds you to the `unreal-engine-css` group with `sudo gpasswd`, if you are not
   already a member.
5. Runs `satisfactory-modding-setup` as your user.

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
satisfactory-modding-setup
```

The package guides cover manual builds. Package install hooks print reminders,
and the engine hook also creates the `unreal-engine-css` group and gives it the
engine files. Hooks never download tools, set up Wine, or change your account.

## Next: Project Setup

This repository stops where the guide's
[Project Setup](https://docs.ficsit.app/satisfactory-modding/latest/Development/Linux/LinuxSetup.html)
section begins. Every step from there on is manual and is not automated here yet.
Follow the guide in this order. The notes below cover what the guide leaves out
or what differs with these packages. The whole path, through a Rider build and
the first editor start, has been tested with the packages.

1. **Download the Starter Project**, for example with
   `git clone https://github.com/satisfactorymodding/SatisfactoryModLoader`.
2. **Install Wwise with wwise-cli.** This step is required. Download the latest
   `wwise-cli` from its [releases page](https://github.com/mircearoata/wwise-cli/releases/latest),
   then run its `download` and `integrate-ue` commands exactly as the guide shows.
   Run `integrate-ue` from the Starter Project folder, with
   `--project ./FactoryGame.uproject`. Both commands ask for your Audiokinetic
   email and password, or read them from `WWISE_EMAIL` and `WWISE_PASSWORD`.
   `integrate-ue` prints nothing when it succeeds. Afterwards `Plugins/Wwise` and
   `Plugins/WwiseNiagara` exist in the project.
3. **Generate the Wwise project and sound banks** in the Wwise Authoring app.
   Start it with plain `wine`, as the guide shows. Running it inside the managed
   Wine prefix has not been tested. Name the project
   `SatisfactoryModLoader_WwiseProject` and create it in the Starter Project
   folder. A new Wwise project only has the Windows platform, so the banks land in
   `GeneratedSoundBanks/Windows/`.
4. **Set up Rider.** Open the `.uproject` through the launcher, so builds can find
   the MSVC toolchain:

   ```sh
   satisfactory-modding-run rider ~/git/SatisfactoryModLoader/FactoryGame.uproject
   ```

   Install the **Unreal Project Model Mods Fix** plugin (by Archengius) from
   Rider's plugin marketplace, or Rider hides the `Mods` folder. The guide also
   says to delete `Engine/Source/Programs/LiveLinkHub` from the engine. The
   engine package already leaves it out. The guide's optional UnrealBuildTool
   patch (`BuildUBT.sh`) is not applied and was not needed.
5. **Compile the project** in Rider with **Development**, **Editor**, and
   **Linux** selected. The first build takes a long time.
6. **Open the editor.** When it asks for the GeneratedSoundBanks folder, click
   **Yes**. In **Wwise > Integration Settings**, set **Root Output Path** to the
   Wwise project's `GeneratedSoundBanks` folder, and set **Unreal Audio Routing**
   to **Both Wwise and Unreal audio**. Unreal stores the path relative to the
   project's `Content` folder, as
   `../SatisfactoryModLoader_WwiseProject/GeneratedSoundBanks`. That is correct.
   These settings change `Config/DefaultGame.ini`, which the Starter Project
   tracks in git, so keep that change out of commits you send upstream.

Copy the wwise-cli commands from the guide rather than from this README, because
the guide updates the Wwise versions. The setup package already installs what
these steps need from the system: Wine, and `dos2unix` for SML's Wwise patches.
The engine loads the MSVC environment itself through `~/.unrealrc`.

If Rider shows **Project 'Engine' load failed** with a permission error in its
UnrealBuildTool log, you are not in the `unreal-engine-css` group yet, or you have
not logged in again since joining. Check with `id`.

## Licenses and terms

- The engine is subject to the
  [Unreal Engine EULA](https://www.unrealengine.com/eula). Access to the source
  repository does not give you the right to redistribute it, so do not publish
  built engine packages.
- `satisfactory-modding-setup` downloads Microsoft tools under the
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

[TODO.md](TODO.md) tracks open verification work.

## License

The [ISC license](LICENSE) covers only the original recipes, scripts, tests, and
documentation in this repository. The Unreal Engine, Microsoft tools, and
upstream files keep their own terms.
