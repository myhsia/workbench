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
- **Report status.**  Before reporting, run `git status -sb` in every checkout of the current
  workspace and state, for each: the branch, whether HEAD == `origin/main`, and whether the tree is
  dirty.  Call out uncommitted changes (and whose they are) and any unpushed commit.
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

## Keeping these rules current

Whenever a session in **any** repository establishes a convention that is not specific to that
project — a coding style, a commit/PR rule, a LaTeX style, a tool workflow, a pitfall — record it
here or in the matching global skill as part of the same task, then commit and push this repository
(`myhsia/workbench`, checked out at `~/.config/opencode`).  Check every time; never leave a general
rule trapped in a project guide.

The daily upkeep check is `~/.config/opencode/scripts/update-due.sh` (see `opencode-hpc-update`).
