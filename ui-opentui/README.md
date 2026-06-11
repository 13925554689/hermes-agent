# ui-opentui — native OpenTUI engine for Hermes

Solid + `@opentui/core` over Node FFI. Ink (`ui-tui/`) is the shipping default;
this is the experimental engine (draft PR #42922).

## Node 26 setup (required; will not touch your other projects)

This package needs **Node ≥ 26.3** (`--experimental-ffi` floor). Everything
else on this machine/repo can keep whatever Node it already uses — pin 26 to
this directory only:

```sh
# 1. install fnm (skip if you have it; nvm/mise work too — see below)
curl -fsSL https://fnm.vercel.app/install | bash
# add to ~/.zshrc (or bashrc): eval "$(fnm env --use-on-cd --shell zsh)"

# 2. install Node 26 SIDE BY SIDE (does NOT change your default)
fnm install 26

# 3. done — this directory has a .node-version (26.3), so `cd ui-opentui`
#    auto-switches to 26 and leaving switches back. Do NOT run `fnm default 26`.
node -v   # v26.x here; your old version everywhere else
```

No shell integration wanted (CI, scripts, one-off): `fnm exec --using 26 -- node ...`
or invoke the absolute binary (`~/.local/share/fnm/node-versions/v26.*/installation/bin/node`).
mise users: `mise use node@26` in this directory. nvm users: `nvm install 26`,
plus an `.nvmrc` shim (`echo 26 > .nvmrc`) if you rely on auto-switching.

### Gotchas

- **Native modules are ABI-locked.** A `node_modules` installed under Node
  20/22 will not load under 26 (and vice versa) — run `npm ci` (or
  `npm rebuild`) after switching versions. Same applies to `bench/`'s node-pty.
- **Global npm packages don't follow** between versions (per-version prefix);
  reinstall the few you need, or don't use globals.
- **Editor terminals** (Zed/VS Code) need the `fnm env` line in your shell rc;
  the `.node-version` auto-switch then covers any shell that cd's here.
- **Never run this package with bun** — the FFI seam and the Solid/JSX build
  are Node-path only here.
- `package.json` declares `engines.node >= 26.3`, so a wrong-Node `npm ci`
  warns immediately.

## Build & run

```sh
node scripts/build.mjs
HERMES_TUI_MOUSE=1 node --experimental-ffi --no-warnings dist/main.js
```

Gates: `npm run check` (typecheck + lint + tests). Memory/perf benchmarks live
in `../bench/` (see its README). Transcript windowing (memory architecture) is
documented in `../docs/plans/opentui-transcript-windowing.md`.
