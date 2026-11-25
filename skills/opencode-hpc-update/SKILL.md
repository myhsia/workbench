---
name: opencode-hpc-update
description: Check OpenCode V2 (docs, releases, breaking changes) and Westlake University HPC (online model list, endpoints) for upstream updates, then sync the local OpenCode configuration safely.
license: MIT
compatibility: opencode
metadata:
  audience: maintainers
  scope: machine-global config
---

# OpenCode / Westlake HPC update check

Use when asked to check for OpenCode or Westlake HPC updates, refresh the Westlake model list, or
reconcile the local OpenCode configuration with upstream.

## Where the local config lives

- `~/.config/opencode/opencode.json` — global provider + models (native V2 shape).
- `~/.config/opencode/cli.json` — terminal-client settings.
- `~/.config/opencode/service.json` — background-service password and `env`, which holds
  `WESTLAKE_API_KEY` (mode 600).  The cluster's own credential is *not* here: `oathpass` reads
  `~/.config/oathpass/config.json` (host, login ports, user, OTP seed; mode 600), and since the
  cluster asks for the OATH code alone, that seed *is* the account credential.
- `<project>/opencode.json` — per-project permissions and `compaction`.

The provider key is **only** referenced as `"apiKey": "{env:WESTLAKE_API_KEY}"`; never write the
secret inline. It lives only in `service.json`'s `env` and travels with the OpenCode backup.  The
cluster seed is kept outside `service.json`, in `~/.config/oathpass/config.json`: it holds the
cluster's only factor by design, so it never leaves this machine and is never copied into
`opencode.json` or a tracked guide.

This configuration is the repository `myhsia/workbench`, so a second machine can start from the
same guides, plugins and scripts.  `scripts/config-sync.sh` runs once a calendar day from the
`upkeep` plugin and reports `config: synced N commit(s) from origin/main` when it fast-forwards a
strictly-behind branch with a clean tree; a dirty or diverged tree is reported and never merged,
and an unreachable origin is exit 2, silence, retried tomorrow.  A fast-forward replaces
`plugins/`, `scripts/` and `AGENTS.md` before the next start, which is the point — but it also
means remote code runs automatically, so the guard is that it merges only when nothing local can
be lost.

## Check upstream

OpenCode (international — try direct first, fall back to the proxy from the `network-access` skill,
`~/.config/opencode/proxy`):

- `opencode --version` (CLI) and `opencode api get /api/info` (the running service) — they can differ
  after an upgrade; the service must be restarted by the user (`opencode service restart`) to pick up
  a new build, and that restart ends any running session, so never do it yourself.
- **The campus bottle mirror cannot serve Homebrew 7 at all.**  `~/.zprofile` keeps
  `HOMEBREW_API_DOMAIN` on `mirrors.cernet.edu.cn/homebrew-bottles/api` (that endpoint answers the
  right shape), but **`HOMEBREW_BOTTLE_DOMAIN` must stay unset**.  The mirror serves bottle tarballs
  only: its OCI manifest path `.../homebrew/core/<name>/manifests/sha256:…` redirects to
  `chinanet.mirrors.ustc.edu.cn` and answers **404** (measured 2026-11-25), and brew 7.0.16 aborts at
  that 404 instead of falling back to GHCR, reporting the misleading
  `rb_file_s_rename … .incomplete → .json`.  (The tarball path is worse: `403` without a browser UA,
  and an 875-byte HTML page with one.)  Bottles and manifests therefore come from GHCR through the
  proxy: `~/.zshrc` defines a `brew()` wrapper that **strips `HOMEBREW_BOTTLE_DOMAIN` per call** —
  long-lived parents such as the OpenCode service still export it — and sets `https_proxy`/`http_proxy`
  with the mirror hosts in `no_proxy`.  Keep using that wrapper; a bare `brew` inherits the stale
  variable and fails again.  Verified after the change: `zstd 1.5.7_1 -> 1.6.0`, `ffmpeg 9.0.2_1 ->
  9.1`, `brew outdated` empty.
- Docs <https://opencode.ai/v2/docs/> and migration guide <https://opencode.ai/v2/docs/migrate-v1>
  (note the three V2 breaking changes: plugins, server API, `cli.json`).
- Release notes: `https://api.github.com/repos/anomalyco/opencode/releases?per_page=5` (the old
  `sst/opencode` name redirects; the canonical repository is `anomalyco/opencode`). Read the
  **Breaking changes** section before syncing anything. The anonymous API is rate-limited from the
  campus address (`API rate limit exceeded for …` with no headers), so use `gh api` — authenticated —
  or fall back to the proxy.

Measured on 2026-11-24: v2.4.0 and v2.4.1 (both 2026-11-23) are the newest.  The CLI was upgraded to
**2.4.0** that morning with `brew upgrade opencode`; the **service still runs 2.3.2** until the user
runs `opencode service restart`, because that restart ends the session.
Measured again on 2026-11-25: the service had been restarted by then and ran **2.4.0**, and the CLI was
upgraded to **2.4.1** (`brew update` first — the formula still said 2.4.0, so `brew upgrade` alone
answered "already installed"; then the documented mirror bypass, because `HOMEBREW_API_DOMAIN` still
served the 403 bottle).  Measured on 2026-11-26: CLI and service both report **2.4.1**
(`opencode --version`, `GET /api/info`), so the user has restarted the service and the config-only
provider picker trap (#60587 / #65793, fixed in 2.4.1) is gone from the running TUI.  None of the
2.4.1 notes carries a `Breaking changes` section.  The v2.4.0 upgrade notes
that touch this setup and why they do not: the image tool is now `generate_image` (no permission rule
names it, so nothing to remap); a plugin that follows a version updates itself (every plugin here is
a local directory, and `opencode.json` names none); MCP servers negotiate the newest protocol first
(none is configured; `client-mcp` in `cli.json` is the TUI's own client setting); Code Mode session
tool paths are now `tools.opencode.session.rename` and `.move`, while the direct tool names are
unchanged, so a guide that says `session_move` is still right; automations are new and on by default
(`"automations": false` turns them off) and are left at the default; and the `opencode` theme now
means the new one, `new-designs` having become the default.  The v2.4.1 release fixes the
config-only-provider picker (see Pitfalls).

Measured on 2026-11-18 at v2.3.2 (published 2026-11-18, latest; v2.3.1 the same day, v2.3.2
only a GPT-6.2 prompt-caching fix): neither release carries a `Breaking changes` section, and the
configuration survived unchanged — one provider with `activation: "enabled"`, three models, the
`title` prompt loaded (`opencode debug agents`, 2 749 chars), and Plan's `edit * deny` still the
first rule.  The changes that could have touched this setup, and why they do not:

- **Background compaction is on by default** from 2.3.1, and `experimental.background_compaction` is
  gone.  This config sets `compaction.auto: false`, so no summary is written either way; keep it.
- Shell commands whose timeout expires now move to the background instead of being killed, and the
  `shell_timeout_background` flag no longer exists — neither it nor a foreground `timeout: 0` is set
  here.
- `CLAUDE.md` is read again wherever no `AGENTS.md` exists; every repository here carries one, so the
  fallback never fires.
- The app's *export* dialog can now save to the system temp directory as well as the project folder,
  which supersedes the 2.2.7 note that it always wrote into the current directory; the CLI
  `opencode session export <id>` still streams to stdout and creates no file (measured).

Still true from 2.3.0: subagents always run in the background and report when idle, and the TUI
transcript verbosity defaults to `low`.  Generated titles still carry no model commentary.

`oathpass` release — **done by the plugin, not by hand**:

- `scripts/release-check.sh --apply` runs once per calendar day from the `upkeep` plugin, and is the
  only thing that installs an `oathpass` here.  It compares the installed bytes with the release's
  `SHA256SUMS` (not just the version string), so a locally built binary is replaced even when it
  carries the same number, then prints one line: `oathpass 0.4.3 -> 0.4.4 (v0.4.4, selftest passed)`
  or `oathpass: re-installed …`.  State lives in `~/.config/opencode/.release-state` (untracked).
- If that line appears in a session's context, report it as given; do not re-run the check and do
  not "verify" it with `--version` alone.
- Never rebuild it with `make`, never `make install`, and never bypass the script by fetching an
  asset by hand: the checksum gate and the rollback live there.
- A failure line is information, not an error to fix in passing: the previous binary is still in
  place, and the next day retries.

Westlake HPC billing (campus — no proxy), as part of the daily check:
- `python3 ~/.config/opencode/scripts/hpc-rates.py --check` covers **both campuses**
  (each has its own `source` page; Yungu's is the internal `10.28.0.22:30538`, so it
  needs the campus network). `--profile NAME` narrows it. It fetches
  <https://hpc.westlake.edu.cn/document/science/en/money.html#partition-billing-standards>
  and compares it with `~/.config/opencode/hpc-rates.json`. It exits 0 when
  everything matches, 1 on a difference, 2 when the page cannot be read or no
  longer parses.
- **Report a difference, do not accept it silently.** A rate change is the
  user's decision; after they agree, `--update` rewrites the rate and cores of
  the known partitions, keeps every `min_cores` (local knowledge that the page
  does not publish), and stamps `updated`.
- A partition the group holds but the page never lists carries
  `"local_only": true` (currently `douwj`), so `--check` does not report it as
  gone; `--update` leaves it untouched.  Add the flag with the entry, not later.
- Slurm bills allocated cores per started hour, so a rate change moves what
  `hpc-job` recommends. Storage pricing (currently a 50% → 83.3% → 100%
  schedule) is on the same page; mention it if the schedule moves.
- `python3 ~/.config/opencode/scripts/hpc-docs.py --check` covers the rest of
  the documentation for both campuses (Yunqi's site and Yungu's internal one): it hashes every English page in the sitemap and reports
  added, changed and removed pages (exit 0 clean, 1 moved, 2 unreadable). A
  moved page is a prompt to read it and update `skills/hpc-cluster/SKILL.md`,
  then `--update` to accept the new state. Partitions, QoS and storage live
  there, so a silent page change is how a skill goes stale.  The sitemap also
  carries non-cluster pages (FutureOS, the AI-model page): a move there is often
  informational, so read the title before editing the skill — 2026-11-15 had two
  such pages and neither changed a partition or a rate.

Westlake HPC (campus — no proxy):

- Model table <https://hpc.westlake.edu.cn/#/ai-campus> is a Vue SPA; its data is in
  `https://hpc.westlake.edu.cn/js/app.<hash>.js`. Fetch it and read the `models:` array: an entry
  with `offline:!0` renders as `已下线` (offline) and must not be added.
- Docs `https://hpc.westlake.edu.cn/document/science/soft/more/ai.html`, plus
  `opencode_campus.json` and `opencode_se.json` (these can lag the live table — trust the SPA).
- Endpoint: campus `https://hpc-api.westlake.edu.cn/v1`. Currently online:
  `deepseek-flash`, `glm-flash`, `Qwen`, plus the serving-only `Qwen3-Embedding-8B` and
  `Qwen3-Reranker-8B` (embedding/reranking models — do not add them to `providers` as chat models).
  The live list also still carries `deepseek`, `deepseek_pro`, `glm`, `glm-5.2`, `minimax` and
  `gemma` marked `offline:!0` — they must not reappear in the config.  The check date lives in
  `.update-check`, not here, so this line does not go stale.

## Sync the configuration

1. Keep only **online** models, and match the user's compact JSON style (object fields on their own
   lines; `input`, `output`, and `limit` inline).
2. Preserve `package: "@opencode/ai/providers/openai-compatible"` (the 2.2.x name; older
   `aisdk:@ai-sdk/openai-compatible` is what 2.0/2.1 wrote), `settings.baseURL`, and
   `settings.apiKey: "{env:WESTLAKE_API_KEY}"`.

## Apply and verify safely

- Config edits hot-reload, but `{env:...}` is resolved from the **background service's process
  environment**, so any environment change needs `opencode service restart`. **Never restart the
  service yourself** — the running session lives on it; ask the user to restart.
- Verify with `opencode models` and `opencode api get /api/provider` (the list): it carries
  `activation: "enabled"`, the `package`, `settings`, and the **resolved key in plaintext**, which
  `/api/config` and `/api/model` also return. Every one of them writes the secret into whatever
  records the output, so parse the JSON and print ids, `activation`, `package` and a key *length* —
  never a slice of the raw body. `head -c 300` on `/api/model` leaked the key on 2026-11-11; the
  route is fine, the display was the mistake.
- The single-provider route `GET /api/provider/<id>` was absent in 2.2.6 (`ProviderNotFoundError`)
  and answers again in 2.2.7 (measured 2026-11-11). Try it; do not conclude from the version that
  it is gone. After an upgrade, `opencode debug agents` may also show a **partial** list while
  plugins load (2.2.7: `agent.list`, `integration.list`, `usage.limits`, `vcs.init`, `rpc.call`
  and `artifact.*` no longer wait for plugins) — re-run before reporting an agent missing.

## Pitfalls

- The published `opencode_campus.json` can list models that are now offline (`deepseek_pro`, etc.).
- `GET /api/config` returns the provider key in plaintext to any caller holding the local service
  password.
- Do not put the key in `~/.zshrc`; keep it inside the OpenCode config so it travels with the backup.
- **Empty `/model` picker with a config-only provider.** Upstream issue #60587 (canonical:
  #49309). With `experimental.new-designs: true` in `~/.config/opencode/cli.json`, the new picker
  counts only **saved integration connections** (`/connect`) as connected; a provider declared only
  in `opencode.json` is treated as disconnected, so the dialog falls back to the free-models list and
  shows **no items** — even though the provider works and the session keeps its model.  **Fixed in
  v2.4.1** (2026-11-23, #65793): a config-only provider lists its models without a `/connect` login,
  so the trap and the steps below apply to a service older than that.  Diagnosis and
  fix (status 2026-11-26: CLI and service both report 2.4.1, the release that carries the fix, so the
  trap no longer applies here; the picker itself was not re-opened to confirm):
  1. `opencode api get /api/model --header x-opencode-directory:<project>` — if the models are listed
     (with `/api/model/default`, `/api/agent`, `/api/command`, `/api/plugin` all valid too), the
     server is fine and the provider config is not at fault;
  2. `grep new-designs ~/.config/opencode/cli.json` — set it to `false` (or save a connection via
     `/connect`) to restore the classic "Select model" dialog; reload the TUI (F5);
  3. do **not** chase the `models.dev` catalog/proxy for this, and do not treat an empty picker as a
     provider problem: an earlier version of this note wrongly blamed the catalog fetch and the
     `ACPCatalogNotReadyError`/"No models are available" strings from the bundle, which belong to the
     ACP integration used by editor clients, not to the TUI dialog.
