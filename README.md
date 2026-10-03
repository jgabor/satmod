# Satisfactory modding on Linux

**`unreal-engine-css-bin` is complete and built.** The current package is
`5.6.1.css83-3`; the user confirms upgrading from pkgrel 2 to pkgrel 3. Follow the
[engine build and install guide](packages/unreal-engine-css-bin/README.md).
There is no need to rebuild the existing package before installing it.

The user also confirmed that reinstalling with the registration entry commented
out printed the reminder, while registering and reinstalling suppressed it.
These installed-state results were not independently rerun here. Normal GUI startup
remains unverified. An earlier isolated Xvfb/NullRHI startup failed with no
usable default DDC cache nodes and failed Zen startup. Its cause is unknown in
that limited environment; it does not establish normal GUI behavior.

The Arch Linux packages target the
[Linux setup guide](https://docs.ficsit.app/satisfactory-modding/latest/Development/Linux/LinuxSetup.html)
up to, but not including, **Project Setup**:

- [unreal-engine-css-bin](packages/unreal-engine-css-bin/): the prebuilt CSS
  Unreal Engine under `/opt/unreal-engine-css`, installed according to the user.
- [satisfactory-modding-setup](packages/satisfactory-modding-setup/): a built Arch
  recipe, user-run MSVC/SDK setup command, and minimal environment launcher.
  Follow its guide for build/install steps, applicable Microsoft terms, defaults,
  repeat runs, and retained user data. After the pkgrel 2 Wine server wait fix,
  the user reports successful helper compilation, compile/link/header/dependency/
  resource tests, and repeat setup without downloads. These runtime results were
  not independently rerun here. Pkgrel 3 uses `satisfactory-modding-setup --json`
  for first and repeat setup; the compatibility flag is optional and has no effect.

Account creation, account linking, repository access, GitHub authentication, and
applicable license decisions remain user responsibilities. The user-run setup
invocation deliberately requests MSVC/SDK installation under applicable Microsoft
terms, as linked in the setup guide; this notice is not legal certification.
User setup must run without root privileges. Pacman install scripts must not
download toolchains, initialize Wine, or configure user accounts.

The engine recipe is self-contained. [scripts/](scripts/) is reserved for
maintainer/bootstrap tools. Large local inputs and outputs stay in ignored
`.cache/`. A build needs roughly 48 GB plus overhead; installation needs roughly
30 GB plus metadata/cache.

AUR publication and Project Setup are deferred. See [TODO.md](TODO.md) and
[pinned source inputs](upstream-inputs.json). The engine package is ready;
the setup recipe is built and fixture-tested, with successful runtime setup and
repeat runs reported by the user. Normal GUI startup, clean-chroot builds, and full
package lifecycle checks remain unverified;
no agent-run Microsoft download, license acceptance, or account setup was performed.
