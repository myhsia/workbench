# oqs workspace

This directory holds three related repositories:

- `mkct4oqs/` — the MKCT manuscript code. Its full guide is `mkct4oqs/AGENTS.md`.
- `dmrg4oqs/` — the public companion repository (shared config / HEOM / library
  files and the MPS/tDMRG reference). Its guide is `dmrg4oqs/AGENTS.md`.
- `sh4oqs/` — the public surface-hopping (FSSH) reference. Its guide is `sh4oqs/AGENTS.md`.

The three checkouts must stay siblings here: `mkct4oqs` is canonical for the shared pieces
(`heom.py`, `config/`, `qutils/fsutils/pltools/extended_heom`), and the public `dmrg4oqs` and
`sh4oqs` keep synced copies (`tools/sync_from_mkct.sh`).

## Working here

- Before touching a project, read and follow that project's own guide (`mkct4oqs/AGENTS.md` or
  `dmrg4oqs/AGENTS.md`); those are authoritative.
- Run git inside the project directory (`cd mkct4oqs` or `cd dmrg4oqs`); `oqs/` itself is
  not a repository.
- The shared rules in the workspace `repo-rules` skill still apply: preserve the user's uncommitted
  changes and staging, commit only when asked, keep the guides in sync, never put secrets or
  addresses in commits.
- Shared conventions for all projects (repo etiquette, Python coding style, git/PR workflow, LaTeX
  writing and source style, tooling/upkeep, local/CI parity) are in the workspace `repo-rules` skill
  (`.opencode/skills/repo-rules/SKILL.md`); the project guides keep only their specific rules.
- Session upkeep uses the `session-hygiene` skill (keep sessions whole; branch into a new session
  for a new topic; `type(things): …` titles); config/upstream upkeep uses `opencode-hpc-update`
  and `network-access`.
- `.opencode/` and `opencode.json` at this root belong to the **workspace**, not to either repository:
  the inner skills/scripts (HPC-update, session hygiene, the daily `update-due.sh`) and the
  permissions/compaction config.  Each repository keeps its own physics skill
  (`mkct4oqs/.opencode/skills/SKILL.md`, `dmrg4oqs/.opencode/skills/SKILL.md`,
  `sh4oqs/.opencode/skills/SKILL.md`); the workspace keeps no link to them.
- `bibliography/` (references and former-work code) and `admin/` are **workspace-level data**, outside
  the repositories; keep them here, not inside `mkct4oqs/` or `dmrg4oqs/`.

## Network access

Governed by the machine-global `network-access` skill; the proxy address is not stored here.  Read it
at use time from `~/.config/opencode/service.json` → `env.HTTPS_PROXY`.

- Small calls (metadata, `gh api`, a few kB of JSON) go **direct** first.
- Bulk transfers (CI artifacts via `gh run download`, release assets, big clones, `pip download`) go
  **through the proxy** even when the direct route works: the GitHub content network
  (`*.blob.core.windows.net`, which Actions artifacts redirect to) is throttled to tens of kB/s
  directly against ~1.3 MB/s proxied.
- `gh` is a Go binary and honours `https_proxy`/`http_proxy`, so export them before downloading.

```bash
PROXY=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.config/opencode/service.json')))['env']['HTTPS_PROXY'])")
https_proxy="$PROXY" http_proxy="$PROXY" gh run download <run-id> -n <name> -D /tmp
```

## Status check

After any change (and before reporting), check and report all four checkouts:

    git -C oqs                    status -sb
    git -C mkct4oqs               status -sb
    git -C dmrg4oqs               status -sb
    git -C sh4oqs                 status -sb

A settled state shows `## main...origin/main` with HEAD == origin/main for each; call out a dirty
tree (and whose change it is) and any unpushed commit.  The full rule is in the `repo-rules` skill.
