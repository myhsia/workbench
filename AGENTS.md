# Machine-wide OpenCode rules

These apply to every OpenCode session on this Mac, in every repository.  Project guides
(`AGENTS.md` in each repository, and any `AGENTS.md` in a parent directory) add the specifics and
stay authoritative for their own project.

- General conventions — Python style, git/PR workflow, LaTeX writing and source style, tooling and
  upkeep, local/CI parity — live in the global `repo-rules` skill.
- Session upkeep uses the `session-hygiene` skill; config/upstream upkeep uses
  `opencode-hpc-update`; bulk CI work uses `ci-artifacts`.

## At session start

Two checks of the configuration, plus at most one check of the repository, before the task
itself. The global ones are scripts: run them, do not recall them. They run on
the **first prompt of each calendar day** (Asia/Shanghai) and again **whenever the session's
directory changes** (a workspace or repository switch) — not merely once per session.  The
`upkeep` plugin enforces that cadence and injects one short line when a check reports something;
the `at session start` rule below is what makes the answer part of the task.

```bash
bash ~/.config/opencode/scripts/update-due.sh              # exit 0 = DUE
bash ~/.config/opencode/scripts/guides-due.sh --committed .  # exit 0 = STALE
```

- `update-due.sh` printing `DUE` means today's calendar day has no stamp: load
  `opencode-hpc-update`, refresh the config, and stamp the day with `update-due.sh --mark`.
  There is **no 17:00 rule** — the day rolls over at 00:00 Asia/Shanghai, and a skipped day is due
  on the next first message, any hour.  Otherwise say nothing about it.
- `guides-due.sh` in the current repository printing `STALE` or `MISSING` means the guides are part
  of this task, not a follow-up. Report the answer with the status at the end; see the commit gate
  in `repo-rules`.  The `--committed` form judges the history only: a repository being edited is
  dirty by design, and the pre-commit gate runs the default form.  When the target is not a git
  repository (the workspace root, which holds sibling checkouts), it prints one line per child
  repository and exits 0 if any of them is `STALE` or `MISSING`.  A path that holds no repositories
  at all (such as `~`) prints a `NOTE` and exits 1 — nothing to check, nothing to report.
- A repository may declare **one check of its own** in its `AGENTS.md`, as
  `` Session check: `scripts/…` ``.  The `upkeep` plugin runs that declared path on the same cadence,
  with the repository as the working directory.  Exit 0 is silence and exit 2 means "cannot run
  here"; anything else is reported, and its first lines become part of the task.  Only the declared
  path is run, never an undeclared file, so a checkout opts in through its reviewed guide.
- **Plan mode cannot run these** (see *Plan mode* below): the `shell` action is denied there, as
  are `edit` and `subagent`.  The `upkeep` plugin runs the checks itself, independently of the
  agent's permissions, so its injected line is the evidence to quote; never claim to have run a
  check that the mode forbade.  Report a `STALE`/`MISSING` guide as pending rather than fixing it,
  and run both scripts at the first prompt after switching to a build agent.  A check that could
  not run is deferred, never reported as passed.

## Session titles

Every session title is `type(thing): short subject`, with `type` among `feat`, `fix`, `tune`,
`refactor`, `docs`, `chore`. The hidden `title` agent writes it, and its system prompt is ours:
`prompts/title.txt`, wired as `agent.title.prompt`. A drifting title therefore means that file
needs a look, not that an agent forgot to rename; a session titled before the prompt existed is
renamed in passing. The detail is in the `session-hygiene` skill.

## Plan mode

Plan mode is enforced by the permission rules, not by the prompt that announces it.  The rule is
narrow: **commands are allowed; writes are not, except in the temporary tree.**  `agent.plan` and
`agent.explore` allow `edit` only under `$TMPDIR/opencode` and (for plan) `~/.opencode/plan`, deny
it everywhere else, and limit `subagent` to the read-only `explore`.  The config names those roots
as `{env:TMPDIR}opencode/**` and `{env:HOME}/.opencode/plan/**`, so no machine id is committed;
macOS spells the same temp tree both `/var/folders/…` and `/private/var/folders/…`, and both are
listed because the matcher compares strings.  So a Plan session probes by
copying into `$TMPDIR/opencode` and working there, never by writing in place.  Shell is path-blind
— its permission resource is the command text, not the working directory — so
`plugins/shell-guard` rejects a command that would write into a project: `>`, `tee`, `sed -i`,
`rm`/`mv`/`cp`, `git add|commit|push|reset|…`, `l3build`, a Python write.  Check
`opencode debug agents` when in doubt.  Since the shell remains available, re-run a check rather
than quoting a result from before the switch.  A denied `read` says `Permission denied: read`; a
guard rejection names the reason and the directory.

## No unobserved results (MUST)

Never report a measurement you did not run.  Every claimed check, benchmark, error figure or
"it works" carries the command and its actual output; when something was not run, say so plainly
instead of implying it was.

- Label every number: **measured** (a run performed in this task), **derived** (computed from
  recorded data by a stated formula), or **fitted** (a parameter adjusted to match a target).
- Record rejected variants and dead ends with the reason they failed, instead of deleting them; a
  silently removed attempt reads as if it never existed.
- State an approximation with its regime and residual; never let a clean-looking plot stand in for
  a tolerance.

## Repository etiquette

- **Preserve the user's uncommitted changes.**  If `git status` shows uncommitted changes you did
  not make, treat them as the user's intentional edits: never discard, revert, overwrite, or "fix"
  them back.  Build on top of them; if they cause a problem (a failing build, an overfull box),
  flag it instead of silently undoing.
- **Commit only when asked.**  Leave the user's staging alone; stage by pathspec when committing.
- **`Guides-Reviewed:` trailer.**  The commit gate in `repo-rules` prescribes one line whenever the
  staged diff changes code, config, CI or output while neither guide changes.  Put it in the commit
  message's trailer block, `Guides-Reviewed: unchanged, because …` (or the reviewed paths), so the
  review lives in history rather than only in the chat report.
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
  `~/.config/opencode/templates/repo-topic/SKILL.md`, then filling them **from the code** — never
  inventing content.  The required sections are listed in the `repo-rules` skill ("Project guide
  standard").
- **Keep them current.**  Any change to layout, commands, dependencies, conventions, output schema,
  validation, or CI updates the relevant guide **in the same task**, and the guide is committed with
  the change.  Delete stale sections rather than leaving them to rot.  When the code changes and the
  guide does not, the commit says why, in the line the commit gate of `repo-rules` prescribes.
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

The daily upkeep check is `~/.config/opencode/scripts/update-due.sh`; the guide freshness check is
`~/.config/opencode/scripts/guides-due.sh` (both used in "At session start").
