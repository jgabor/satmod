# TODO

## Scope

Automate the
[Linux setup guide](https://docs.ficsit.app/satisfactory-modding/latest/Development/Linux/LinuxSetup.html)
through command-line **Project Setup**, with two Arch packages:

- `unreal-engine-css-bin`: the prebuilt CSS engine under `/opt/unreal-engine-css`.
- `satisfactory-modding-setup`: provides `satisfactory-modding setup` to install
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
  - In `~/git/satisfactory-sync`, `E2E=1 client/test-linux.sh` passed. All
    WwisePatches applied to the fresh plugin, the Linux editor and Win64 modules
    built, and 34 automation tests passed. Two had expected warnings.
  - The old 2023 caches (6.2 GB and 1.1 GB) are kept until the user removes
    them.

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

- [ ] Build both packages in a clean Arch chroot with prefetched engine parts.
- [ ] Run namcap on both recipes and built packages, and review the findings.
- [ ] Check file ownership, permissions, and declared dependencies in the built
  packages.
- [ ] Test package removal, and confirm user data survives. Upgrade over the
  hand-modified install and later releases already worked.

Not planned, to keep verification proportionate: forced failure runs (missing
repository access, a missing archive part, a corrupted download), a bootstrap
that installs dependencies through sudo or adds a user outside the group, a real
engine update with `update-engine-release`, answering wwise-cli's prompts by
hand in `project init`, and a Rider build of a project from `project init`.
Fixture tests cover the failure, bootstrap, release, and prompt paths, Rider
already built the Starter Project after the packaged fix, and problems will come
in as issues.

## Completion criteria

- [ ] Both packages build and install with normal Arch tooling. Built and
  installed on this machine; a clean chroot build is still open.
- [x] Engine inputs are pinned and verified, and authenticated downloads work.
- [x] One run of `satisfactory-modding setup` installs the pinned MSVC/SDK,
  configures `UE_WINE_MSVC`, and registers the engine without prompts. Based on
  the user's report.
- [ ] Repeat setup runs and package upgrade or removal keep unrelated user state.
  Reruns and upgrades are done; removal is not.
- [x] The docs give a tested path from repository access through Project Setup
  with `project init`. No clean-machine run is planned: the setup is in daily
  use for the mod in `~/git/satisfactory-sync`, and problems will come in as
  issues.

## Future

### AUR publishing

After the completion criteria are met:

- [ ] Recheck package names against the
  [Arch package guidelines](https://wiki.archlinux.org/title/Arch_package_guidelines),
  [nonfree package guidelines](https://wiki.archlinux.org/title/Nonfree_applications_package_guidelines),
  and [AUR submission guidelines](https://wiki.archlinux.org/title/AUR_submission_guidelines).
- [ ] Create one AUR repository per package with its `.SRCINFO`, license, and
  helper files. Never publish engine archives, Microsoft tools, or built packages.
- [ ] Explain the authenticated download and license terms on each package page.
- [ ] Set up a reviewed process for engine updates and for user feedback.
- [ ] Ask the wwise-cli author about its missing license before any redistribution.
