# Scripts

Three scripts for installing, maintaining, and publishing the packages. Run them as your ordinary
user, not with `sudo`. They find the repository from their own location, so you
can run them from any directory. See the [root guide](../README.md) for
prerequisites and terms.

## bootstrap

```sh
./scripts/bootstrap [--json]
```

Installs or upgrades everything in one go. It needs `python3`, `gh`, `makepkg`,
`pacman`, and `sudo`, and must run in a terminal so sudo can ask for your
password.

1. Runs `sudo -v`, so the password prompt comes before the long build.
2. Runs `update-engine-release` to move the engine pins to the latest release.
   This always runs, so bootstrap needs a working `gh` login and network access
   even when every package is cached. If a new release has come out, a rerun
   picks it up and builds it.
3. For the engine and then `satmod`: reuses the package in `.cache/` if
   one with the expected name, version, and architecture exists. Otherwise it
   builds one with `makepkg --syncdeps`. Then it installs it with
   `sudo pacman -U --needed`.
4. Right after the engine is installed, adds you to the `unreal-engine-css` group
   with `sudo gpasswd -a`, unless you are already a member. The group can write
   to the engine, which Unreal's build tools need.
5. Runs `satmod setup --json` as your user.

If your current login does not have the group yet, bootstrap tells you to log out
and back in before you open the project in an IDE. Setup itself does not need
the group.

If a step fails, bootstrap stops and exits with that step's status. Run it again
to continue: finished downloads and packages are reused. Reused packages are
matched on metadata only, not contents, so only keep packages you built yourself
in `.cache/`.

### Cache layout

| Path | Contents |
| --- | --- |
| `.cache/engine-recipe/sources/` | Engine archive parts |
| `.cache/engine-recipe/packages/` | Built engine packages |
| `.cache/upstream/msvc-wine/` | `msvc-wine` snapshot and built `satmod` packages |
| `.cache/*-recipe/{build,logs,tmp}/` | makepkg working directories |
| `.cache/*-recipe/makepkg.conf` | Created on first run. Edit it to change build settings, such as compression. |

Bootstrap always uses these paths, even if your own makepkg configuration sets
others. It also always uses `sudo` to install build dependencies.

### Output

Without `--json`, bootstrap prints one line when it finishes, plus a second line
asking you to log out and back in when that is needed. With `--json`, it prints
one JSON object on stdout, and build logs go to stderr:

```json
{"status": "complete",
 "packages": [{"name": "...", "version": "...", "path": "...", "reused": true}],
 "setup": {"status": "complete", "...": "..."},
 "relogin_required": false}
```

`relogin_required` is true when your current login session does not have the
`unreal-engine-css` group yet.

On failure, `--json` prints `{"status": "error", "error": "..."}`. The `setup`
object is the output of `satmod setup --json`.

## update-engine-release

```sh
./scripts/update-engine-release --check   # Report only. Changes nothing.
./scripts/update-engine-release           # Update the pins.
```

Moves the engine recipe to GitHub's latest non-draft, non-prerelease release of
`satisfactorymodding/UnrealEngine`. It needs `gh` with an existing login, and
`makepkg`. It reads release metadata only: it does not download archives, build,
install, or commit.

The release must have archive parts named
`UnrealEngine-CSS-Editor-Linux.tar.zst.00`, `.01`, and so on, numbered from zero
with no gaps, and each part must have an upstream SHA-256 digest. Debug archives
are ignored. If anything is missing or unexpected, the script changes nothing and
exits 1.

An update rewrites these files and nothing else:

- the engine fields and `checked_on` date in [upstream-inputs.json](../upstream-inputs.json)
- `packages/unreal-engine-css-bin/PKGBUILD`, `.SRCINFO`, and `LICENSE.md`

A new release resets `pkgrel` to 1. New metadata for the same release raises it
by one. If nothing changed, no file is touched. The script refuses to run if the
local recipe has edits it does not expect, such as a changed patch or extra
sources.

The output is one line, such as
`unchanged: <tag> (pkgver=<version>, pkgrel=<n>)`. With `--json` it is one
JSON object instead: `status` (`unchanged`, `updated`, or `update-available`), `changed`,
`tag`, `pkgver`, and `pkgrel`.

After an update, review `git diff` and commit it yourself. The release API cannot
tell whether a new engine still builds with the pinned patch or works with the
pinned MSVC version. The engine build checks the patch.

## aur-sync

```sh
./scripts/aur-sync PKG... [--push] [--json]
```

Copies a package recipe into its AUR checkout under `.cache/aur/PKG` and commits
any change. `PKG` is `unreal-engine-css-bin` or `satmod`. It pushes only with
`--push`, and a push publishes, so review the commits first:

```sh
./scripts/aur-sync unreal-engine-css-bin satmod
git -C .cache/aur/satmod show --stat
./scripts/aur-sync unreal-engine-css-bin satmod --push
```

1. Refuses a package whose directory has uncommitted changes or whose
   `.SRCINFO` differs from `makepkg --printsrcinfo`.
2. Clones `aur-jgabor:PKG.git` the first time. `aur-jgabor` is an SSH host alias
   for `aur@aur.archlinux.org`; set `AUR_REMOTE` to use another prefix. A new
   package name clones as an empty repository.
3. Starts from the AUR's `master`, keeping any unpushed commits on top, and
   removes untracked files such as earlier build output.
4. Makes the checkout hold exactly the files git tracks in `packages/PKG`,
   except `README.md`, whose links only work inside this repository.
5. Commits `Initial import VERSION` or `Update to VERSION` when something
   changed, and does nothing otherwise.

The output lists each package's version, whether it committed, and how many
commits are unpushed. With `--json` it is one JSON object with a `packages`
list. The recipes hold no engine archives, Microsoft tools, or built packages,
and must never do so.
