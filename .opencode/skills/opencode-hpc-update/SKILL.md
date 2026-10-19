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
  `WESTLAKE_API_KEY` (mode 600).
- `<project>/opencode.json` — per-project permissions and `compaction`.

The provider key is **only** referenced as `"apiKey": "{env:WESTLAKE_API_KEY}"`; never write the
secret inline. It lives only in `service.json`'s `env` and travels with the OpenCode backup.

## Check upstream

OpenCode (international — try direct first, fall back to the proxy from the `network-access` skill,
`env.HTTPS_PROXY` in `~/.config/opencode/service.json`):

- `opencode --version`
- Docs <https://opencode.ai/v2/docs/> and migration guide <https://opencode.ai/v2/docs/migrate-v1>
  (note the three V2 breaking changes: plugins, server API, `cli.json`).

Westlake HPC (campus — no proxy):

- Model table <https://hpc.westlake.edu.cn/#/ai-campus> is a Vue SPA; its data is in
  `https://hpc.westlake.edu.cn/js/app.<hash>.js`. Fetch it and read the `models:` array: an entry
  with `offline:!0` renders as `已下线` (offline) and must not be added.
- Docs `https://hpc.westlake.edu.cn/document/science/soft/more/ai.html`, plus
  `opencode_campus.json` and `opencode_se.json` (these can lag the live table — trust the SPA).
- Endpoint: campus `https://hpc-api.westlake.edu.cn/v1`. Currently online: `deepseek-flash`,
  `glm-flash`, `Qwen`.

## Sync the configuration

1. Keep only **online** models, and match the user's compact JSON style (object fields on their own
   lines; `input`, `output`, and `limit` inline).
2. Preserve `package: "aisdk:@ai-sdk/openai-compatible"`, `settings.baseURL`, and
   `settings.apiKey: "{env:WESTLAKE_API_KEY}"`.

## Apply and verify safely

- Config edits hot-reload, but `{env:...}` is resolved from the **background service's process
  environment**, so any environment change needs `opencode service restart`. **Never restart the
  service yourself** — the running session lives on it; ask the user to restart.
- Verify: `opencode api get /api/config`, `opencode api get /api/provider/WestlakeHPC` (shows the
  resolved key), and `opencode models`.

## Pitfalls

- The published `opencode_campus.json` can list models that are now offline (`deepseek_pro`, etc.).
- `GET /api/config` returns the provider key in plaintext to any caller holding the local service
  password.
- Do not put the key in `~/.zshrc`; keep it inside the OpenCode config so it travels with the backup.
