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

- [ ] Let `satmod mod build` find mods linked into `Mods/` or `Plugins/` with a
  symlink. The SatSync plugin lives in `~/git/satsync` and is linked into the
  Starter Project as `Mods/SatSync`; plugin discovery does not follow the link,
  so satsync packages with a hand-written `RunUAT.sh` command instead (see its
  `docs/identity-test.md`). When this works, satsync can switch to
  `satmod mod build`.
- [ ] Tag the published satmod version on GitHub (`v1.0.0` for AUR 1.0.0-1), so
  bug reports and releases can name the exact commit. Decide whether later
  releases get a tag for each new `pkgver`.
- [ ] Install both packages through an AUR helper, for example
  `paru -S unreal-engine-css-bin satmod`. All builds so far ran `makepkg` from
  this repository or the AUR checkouts; the engine's `ghasset` download through
  `download-gh-asset` and the user's `gh` login has not run inside a helper's own
  build directory. Prefetch the parts into the helper's clone to skip the 8 GB
  download.
