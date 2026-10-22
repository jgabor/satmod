# unreal-engine-css-bin

This package installs the prebuilt Coffee Stain Studios (CSS) Unreal Engine editor
for Linux under `/opt/unreal-engine-css`. The recipe is pinned to release
`5.6.1-css-83`, packaged as version `5.6.1.css83`.
[`scripts/update-engine-release`](../../scripts/README.md) moves the pin to a
newer release.

Most people get it through [bootstrap](../../README.md). This page covers building
it by hand.

## Prerequisites

- **Access.** Link your Epic Games and GitHub accounts, get access to
  `satisfactorymodding/UnrealEngine`, and run `gh auth login`. The recipe's
  download helper uses your existing `gh` login. It never logs in for you.
- **Tools.** `base-devel` and `github-cli`. `makepkg -s` installs the rest.
- **Disk.** About 48 GB free to build, and about 30 GB for the installed engine.

## Build and install

As your ordinary user:

```sh
cd packages/unreal-engine-css-bin
makepkg -si
```

makepkg downloads the release's archive parts (about 8 GB in total), checks each
against its pinned SHA-256, extracts them, and builds the package. Parts are saved
in makepkg's `SRCDEST`, which is this directory unless you set one. Keep them to
rebuild without downloading again. Bootstrap keeps its parts in
`.cache/engine-recipe/sources/` instead.

To download two parts at a time, prefetch them first. Pass your `SRCDEST` if you
set one:

```sh
./prefetch-engine-sources [SRCDEST]
makepkg -si
```

Prefetch skips files that already exist and does not check them. makepkg still
checks every checksum before building.

The download helper writes to a temporary file and only moves it into place
after the size and upstream SHA-256 match, so an interrupted download never
leaves a partial part under its final name.

## Register the engine

`satisfactory-modding setup` registers the engine for you. If you only install
the engine, register it yourself **as your ordinary user, without sudo**:

```sh
/opt/unreal-engine-css/Engine/Binaries/Linux/UnrealVersionSelector -register -unattended
```

On install and upgrade, the package prints this command, unless it can see that
the account that ran `sudo` has already registered the engine. The hook only
prints. It never writes to your account.

## Engine write access

Unreal's build tools write into the engine folder while generating IDE project
files and building mods, for example under `Engine/Intermediate` and next to each
plugin's build rules. A read-only engine makes Rider fail with permission errors.

So the engine is owned by root and the `unreal-engine-css` group. Directories are
group-writable and setgid, so new files inherit the group. Files are
group-writable. Nothing is writable by everyone. On install and upgrade the
package creates the group if needed and reassigns the engine to it, because
pacman installs files as `root:root`. It also gives every directory a default
group ACL and makes existing files group-writable, so files that builds create
stay writable for the group even under umask 022.

Join the group once, then log out and back in:

```sh
sudo gpasswd -a "$USER" unreal-engine-css
```

Bootstrap does this for you. The install hook prints the command unless it can see
that the account that ran `sudo` is already a member. `id` shows your groups.

A tool that creates a file with an explicit mode such as 0644 still gets that
mode; the next install or upgrade makes it group-writable. That only matters if
several people on one machine share the engine. The filesystem under `/opt` needs
ACL support, which ext4, btrfs, and XFS have by default; otherwise the hook warns
and continues.

Because of this, `pacman -Qkk unreal-engine-css-bin` reports group differences
on engine files. That is expected.

Removing the package keeps the group, and pacman leaves behind any files the build
tools created. Delete `/opt/unreal-engine-css` by hand to remove them.

## What the package changes

- The engine is writable by the `unreal-engine-css` group. See
  [Engine write access](#engine-write-access).
- `Engine/Source/Programs/LiveLinkHub` is left out. Its build rules need a module
  the prebuilt engine does not include, and Rider then refuses to load the
  project. The Satisfactory guide also says to delete it. Modding does not use it.
- `setup-dotnet-permissions.patch` makes `SetupDotnet.sh` skip its `chmod` when
  the bundled `dotnet` is already executable. Without it, the script fails for
  users who do not own the install.
- Prebuilt binaries are not stripped, and static libraries are kept.
- The package ships the upstream `LICENSE.md`, which points to the
  [Unreal Engine EULA](https://www.unrealengine.com/eula), and keeps the bundled
  third-party notices. Do not redistribute built packages.

Rider project generation, a full editor build of the Starter Project, and editor
startup have been tested with this setup. See [TODO.md](../../TODO.md) for what
is still open.
