# unreal-engine-css-bin

The engine recipe packages CSS release `5.6.1-css-83` as `5.6.1.css83-3` for
x86_64 under `/opt/unreal-engine-css`. The user reports that pkgrel 3 is installed
and its registration reminder works. These installed-state results were not
independently rerun here.

## Install the built pkgrel 3 package

From the repository root, install when you are ready to change your system:

```bash
sudo pacman -U .cache/engine-recipe/packages/unreal-engine-css-bin-5.6.1.css83-3-x86_64.pkg.tar.zst
```

If not already registered, register the engine **as your ordinary user, without sudo**:

```bash
/opt/unreal-engine-css/Engine/Binaries/Linux/UnrealVersionSelector -register -unattended
```

Install and upgrade print this instruction unless `SUDO_USER` identifies a non-root
account whose `~/.config/Epic/UnrealEngine/Install.ini` has an `[Installations]`
entry for `/opt/unreal-engine-css`. If the account is unknown or the check fails,
the reminder is conditional. The script never registers the engine or writes user
configuration. Fixture tests cover the notice. The user tested the real notice:
commenting out the registration entry and reinstalling printed the reminder;
registering and reinstalling again printed no reminder.

The user installed pkgrel 2 successfully; the package query, root ownership,
`/opt` directory mode 755, and dotnet permission guard were checked. The guard
skips `chmod` when dotnet is already executable, avoiding a non-owner permission
failure in the root-owned `/opt` installation. Normal GUI
startup remains unverified. Check normal editor startup and user-owned cache state.
The earlier isolated
Xvfb/NullRHI startup failed with no usable default DDC nodes and failed Zen startup;
the cause is unknown in that limited test environment. It was not a normal GUI test.
MSVC installation and the `satisfactory-modding-setup` command are next, not yet
implemented. Engine registration is manual until that command exists.

## Build prerequisites

Use Arch `base-devel`, `github-cli` (provides `gh`), `zstd`, and `patch`.
For uncached downloads, create and link your Epic Games and GitHub accounts,
obtain access to `satisfactorymodding/UnrealEngine`, and authenticate `gh` first.
The helper checks existing authentication; it never logs in or accepts terms.
Authorized use remains subject to the [Unreal Engine EULA](https://www.unrealengine.com/eula)
and applicable upstream terms. Repository access is not redistribution permission.
The unchanged upstream `LICENSE.md` notice and bundled third-party notices are packaged.

Allow roughly **48 GB plus overhead** for parts, build tree, and one package,
and roughly **30 GB plus metadata/cache** for installation.

## Rebuild only when needed

For a fresh uncached build, run `makepkg` as an ordinary user from
`packages/unreal-engine-css-bin`. Its download agent acquires the four pinned parts.
Makepkg's acquisition is serial; optional prefetch runs at most two one-asset
helpers at once. From the recipe directory, with no separate `SRCDEST`:

```bash
./prefetch-engine-sources
makepkg --verifysource && makepkg
```

Prefetch reads the adjacent trusted `PKGBUILD` and skips existing files and symlinks,
including broken aliases. It does not verify cached bytes or repair bad entries.
Normal makepkg checksum verification remains required. Downloads use the existing
helper's atomic publication. Prefetch is optional, uses existing `gh` authentication
only for missing parts, and does not change packaging or decompression.
With a configured `SRCDEST`, pass that same source-cache directory to prefetch
and use the matching makepkg configuration for verification and build.

For this checkout's existing cache, start at the repository root:

```bash
repo=$PWD
mkdir -p "$repo/.cache/engine-recipe/"{sources,build,packages,logs,tmp}
config="$repo/.cache/engine-recipe/makepkg.conf"
if [[ ! -e "$config" ]]; then
  cat > "$config" <<EOF
source /etc/makepkg.conf
SRCDEST="$repo/.cache/engine-recipe/sources"
BUILDDIR="$repo/.cache/engine-recipe/build"
PKGDEST="$repo/.cache/engine-recipe/packages"
LOGDEST="$repo/.cache/engine-recipe/logs"
COMPRESSZST=(zstd -c -T2 -3 -)
EOF
fi
for part in 00 01 02 03; do
  alias="$repo/.cache/engine-recipe/sources/UnrealEngine-CSS-5.6.1-css-83-Editor-Linux.tar.zst.$part"
  [[ -e "$alias" ]] || ln -s "$repo/.cache/upstream/engine/UnrealEngine-CSS-Editor-Linux.tar.zst.$part" "$alias"
done
export TMPDIR="$repo/.cache/engine-recipe/tmp"
cd "$repo/packages/unreal-engine-css-bin"
./prefetch-engine-sources "$repo/.cache/engine-recipe/sources" # Optional; all four are cached here.
makepkg --config "$config" --verifysource
makepkg --config "$config"
```

The aliases map original `.00` through `.03` filenames to release-specific names
without copying 8.26 GB. Keep their original targets available; do not use partial
downloads. When reusing another makepkg configuration, inspect its paths and
recreate its configured build/output/log directories after cleanup. Keep staging and package
directories on the same filesystem. Cached sources need no GitHub credentials.

## Built package

The retained package is **10,074,221,257 bytes**, SHA-256
`d38463d687d9cda4a26347f5dc934c1231cbbfce4e5e760e098823756ab740db`.
It was built with normal dependency and integrity checks. The four cached parts,
source aliases and build configuration remain available for rebuilding.
Normal GUI startup remains unverified. Prefetch network throughput has not been measured.
