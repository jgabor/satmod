# satisfactory-modding-setup

This directory is reserved for a self-contained Arch package recipe for setup
tools and a user-run command that installs MSVC and registers the engine.

Upstream inputs are verified and the complete source-tested MSVC snapshot is
pinned. This setup package and its command remain unimplemented.
User setup must remain unprivileged; toolchain downloads, Wine initialization,
and user configuration must not run in pacman install scripts. Account access,
authentication, and required license acceptance remain manual responsibilities.
The scope stops before Project Setup; AUR publication is also deferred.

See the [pinned source inputs](../../upstream-inputs.json)
and the [work scope](../../TODO.md).
