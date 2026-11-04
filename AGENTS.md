# Machine-wide OpenCode rules

These apply to every OpenCode session on this Mac, in every repository.  Project guides
(`AGENTS.md` in each repository, and any `AGENTS.md` in a parent directory) add the specifics and
stay authoritative for their own project.

- General conventions — Python style, git/PR workflow, LaTeX writing and source style, tooling and
  upkeep, local/CI parity — live in the global `repo-rules` skill.
- Session upkeep uses the `session-hygiene` skill; config/upstream upkeep uses
  `opencode-hpc-update`; bulk CI work uses `ci-artifacts`.

## Repository etiquette

- **Preserve the user's uncommitted changes.**  If `git status` shows uncommitted changes you did
  not make, treat them as the user's intentional edits: never discard, revert, overwrite, or "fix"
  them back.  Build on top of them; if they cause a problem (a failing build, an overfull box),
  flag it instead of silently undoing.
- **Commit only when asked.**  Leave the user's staging alone; stage by pathspec when committing.
- **Report status.**  Before reporting, run `git status -sb` in the global config repository
  (`~/.config/opencode`) and in every checkout of the current workspace (each sibling repository
  named by the workspace guide), then state for each: the branch, whether HEAD == `origin/main`,
  and whether the tree is dirty.  Call out uncommitted changes (and whose they are) and any
  unpushed commit.
- **Never put secrets or addresses in commits.**  Machine endpoints, proxy addresses, API keys and
  cluster IPs stay in untracked files or environment variables.

## Network access

Governed by the global `network-access` skill; the proxy address is not stored here.  Read it at use
time from `~/.config/opencode/proxy` (mode 600).

- Small calls (metadata, `gh api`, a few kB of JSON) go **direct** first.
- Bulk transfers (CI artifacts via `gh run download`, release assets, big clones, `pip download`) go
  **through the proxy** even when the direct route works: the GitHub content network
  (`*.blob.core.windows.net`, which Actions artifacts redirect to) is throttled to tens of kB/s
  directly against ~1.3 MB/s proxied.
- `gh` is a Go binary and honours `https_proxy`/`http_proxy`, so export them before downloading.

```bash
PROXY=$(cat ~/.config/opencode/proxy)
https_proxy="$PROXY" http_proxy="$PROXY" gh run download <run-id> -n <name> -D /tmp
```

## Every repository keeps a guide and a skill

A repository is not workable until it has **`AGENTS.md`** at its root and **`.opencode/skills/SKILL.md`**
(or `skills/<name>/SKILL.md`).

- **First action in a repository**: check both.  If either is missing, **ask the user once**, offering
  *create now / later / never for this repo*.  Never create guides silently.
- Only offer this in a repository the user owns or is editing; not in a third-party checkout that is
  merely being read.
- Creating them means starting from `~/.config/opencode/templates/AGENTS.md` and
  `~/.config/opencode/templates/skill/SKILL.md`, then filling them **from the code** — never inventing
  content.  The standard sections are listed in the `repo-rules` skill ("Project guide standard").
- **Keep them current.**  Any change to layout, commands, dependencies, conventions, output schema,
  validation, or CI updates the relevant guide **in the same task**, and the guide is committed with
  the change.  Delete stale sections rather than leaving them to rot.
- Guides describe the code **as it is now**; they are not design notes.

## Ambient skills: apply, don't ask

| situation | skill |
|---|---|
| a URL, download, clone, or API call fails, times out, or is slow | `network-access` — switch to the proxy |
| data generation, long or matrixed CI jobs, artifact retrieval | `ci-artifacts` |
| a long session, context pressure, or a topic that needs its own session | `session-hygiene` |
| OpenCode itself, its config, or the Westlake HPC models and endpoints | `opencode-hpc-update` |
| coding style, git/PR rules, LaTeX writing or source style | `repo-rules` |

Load and apply the matching skill as soon as the trigger appears; do not ask the user whether a skill
may be used.

## Keeping these rules current

Whenever a session in **any** repository establishes a convention that is not specific to that
project — a coding style, a commit/PR rule, a LaTeX style, a tool workflow, a pitfall — record it
here or in the matching global skill as part of the same task, then commit and push this repository
(`myhsia/workbench`, checked out at `~/.config/opencode`).  Check every time; never leave a general
rule trapped in a project guide.

The daily upkeep check is `~/.config/opencode/scripts/update-due.sh` (see `opencode-hpc-update`).
