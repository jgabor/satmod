# TODO

## Scope

Automate the
[Linux setup guide](https://docs.ficsit.app/satisfactory-modding/latest/Development/Linux/LinuxSetup.html)
through command-line **Project Setup**, with two Arch packages, both published in
the AUR:

- `unreal-engine-css-bin`: the prebuilt CSS engine under `/opt/unreal-engine-css`.
- `satmod`: provides `satmod setup` to install
  MSVC under Wine, register the engine, and write the build environment. The CLI
  also provides `project init` and `project update` for Starter Project and
  Wwise setup, `run` to
  start tools, `doctor` to check the installation, and `mod new` and `mod build`
  for library scaffolding and Windows client packaging.

Rules that hold throughout:

- Account linking, repository access, `gh auth login`, and the Audiokinetic
  account stay manual.
- User setup runs without root.
- Package install hooks never download tools, set up Wine, or change a user's
  account. The engine hook may create the `unreal-engine-css` group, give it the
  engine files, and make them group-writable with a default ACL. Only bootstrap,
  which the user runs, adds the user to it.
- The engine is writable only by root and the `unreal-engine-css` group, never by
  everyone. Unreal's build tools write all over the engine tree, so a read-only
  engine does not work.
- Engine archives, Microsoft tools, built packages, and credentials stay out of
  version control.

## Open

Finished work is in git history, and [MAINTAINING.md](MAINTAINING.md) covers
releases and feedback.

No open items. Last done (2026-10-22):

- `satmod mod build` follows symlinked mod folders (satmod 1.0.1). It packaged
  SatSync through `Mods/SatSync` on this machine.
- Tags `v1.0.0` and `v1.0.1` mark the published satmod versions.
- `yay -S unreal-engine-css-bin satmod` rebuilt and reinstalled both packages
  from the AUR. The download helper fetched one engine part through the user's
  `gh` login inside yay's build folder, and every checksum passed.
