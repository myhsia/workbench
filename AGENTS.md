# Machine-wide OpenCode rules

These apply to every OpenCode session on this Mac, in every repository.  Project guides
(`AGENTS.md` in each repository, and any `AGENTS.md` in a parent directory) add the specifics and
stay authoritative for their own project.

- General conventions — Python style, git/PR workflow, LaTeX writing and source style, tooling and
  upkeep, local/CI parity — live in the global `repo-rules` skill.
- Session upkeep uses the `session-hygiene` skill; config/upstream upkeep uses
  `opencode-hpc-update`; bulk CI work uses `ci-artifacts`.
- The narrative record — what was tried, what failed, and why the rules read as they do — is
  `docs/handbook.md`.  It is history, not policy: where it disagrees with this file, the
  configuration wins and the handbook is corrected.

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
- **Plan mode can run the checks, but cannot fix what they report**: shell stays available, and
  `plugins/shell-guard` rejects only commands that would write (`>`, `tee`, `sed -i`, `rm`, `mv`,
  `cp`, `git add|commit|push`, `latexmk`, Python writes).  Run both scripts; never claim a check
  that the mode forbade.  Report a `STALE`/`MISSING` guide as pending rather than fixing it, and
  apply the fix at the first prompt after switching to a build agent.  A check that could not run
  is deferred, never reported as passed.

## Session titles

Every session title is `type(thing): short subject`, with `type` among `feat`, `fix`, `tune`,
`refactor`, `docs`, `chore`. The hidden `title` agent writes it, and its system prompt is ours:
`prompts/title.txt`, wired as `agent.title.prompt`. A drifting title therefore means that file
needs a look, not that an agent forgot to rename; a session titled before the prompt existed is
renamed in passing. The detail is in the `session-hygiene` skill.

## Plan mode

Plan mode is enforced by the permission rules, not by the prompt that announces it.  The rule is
narrow: **Plan cannot write in the working repository or in the config repository**
(`~/.config/opencode`); everywhere else is allowed.  `agent.plan` and `agent.explore` implement it
by allowing `edit` only under `$TMPDIR/opencode` and (for plan) `~/.opencode/plan` and denying it
elsewhere, and by limiting `subagent` to the read-only `explore`.  The config names those roots as
`{env:TMPDIR}opencode/**` and `{env:HOME}/.opencode/plan/**`, so no machine id is committed; macOS
spells the same temp tree both `/var/folders/…` and `/private/var/folders/…`, and both are listed
because the matcher compares strings.  So a Plan session probes by copying into `$TMPDIR/opencode`
and working there, never by writing in place.  Shell is path-blind — its permission resource is the
command text, not the working directory — so `plugins/shell-guard` rejects a command that would
write outside the allowed roots: `>`, `tee`, `sed -i`, `perl -i`, `rm`, `mv`, `cp`, `rsync`,
`install`, `mkdir`, `touch`, `chmod`, `ln`, `truncate`, `dd of=…`, `find … -delete`,
`tar -x`/`unzip`, `curl -o`/`wget -O`, git history or worktree commands (`add|commit|push|reset|
checkout|switch|apply|mv|rm|stash|clean|restore|am|worktree|submodule|gc|notes|lfs|…`), the build
writes (`l3build`, `tlmgr`, `latexmk`, `bibtex`, `makeindex`), and Python writes (`open(…,'w')`,
`.write(`, `os.remove|unlink|rename|replace|makedirs|mkdir|rmdir`, `shutil.rmtree|move|copy*`,
`Path.unlink|mkdir|rmdir|touch`, `np.save*`, `.tofile(`, `.to_csv(`).  It is a heuristic on purpose:
the word rules fire only in **command position** (start, after `;`/`&`/`|`/`(`, or after
`sudo`/`env`/`nohup`/`time`/`command`/`exec`/`xargs`), so `grep -rn install .` and
`grep -n 'perl -i' notes.txt` stay allowed, while a read-only command that *contains* such a call in
its own text — `node -e "…os.remove(…)"` — is still refused, and an unrecognised wrapper
(`foo rm x`) is not seen.  Check `opencode debug agents` when in doubt, and `node test.mjs` in the
plugin directory for the rule set itself.  Since the shell remains available, re-run a check rather
than quoting a result from before the switch.  A denied `read` says `Permission denied: read`; a
guard rejection names the reason and the directory.

## Orchestrating other sessions

An audit asks; the orchestrator answers.  A read-only audit may end with questions, but those are
resolved here — answered, or waived in one written line — never handed back to the user and never
left as a session's last message.

- **One turn, not two.**  Audit, decision and execution are a single build turn: send the decisions
  with the instruction, and require a reply that names what changed, the verification actually run,
  and the literal line `Residue: none`.  A session that ends on a question is parked, exactly like
  one whose audit found nothing — "leave no session parked" covers both.
- **Stay inside the title.**  A finding outside the session's title belongs to a guide session or to
  the machine-global config; ask about it there, or fix it in the same turn without asking.
- **Prune the question turn once it is answered.**  The audit exchange may then be removed in place:
  whole messages only, one transaction per session, after a `sqlite3 .backup`, leaving the task
  history and the single result turn.  No message JSON is edited, ids and titles stay stable;
  `session-hygiene` carries the procedure and its verification.  The 2026-11-11 run and its numbers
  are in `docs/handbook.md`.

## Guide check after every build run (mandatory)

A run that changes code, configuration, CI or output ends by checking **both** scopes, not only the
one being edited:

1. the working repository — `AGENTS.md`, `.opencode/skills/`, `opencode.json`;
2. the machine-global configuration — `~/.config/opencode/AGENTS.md`, `skills/`, `opencode.json`.

Update whichever is stale in the same commit; when neither needs a change, record it in the commit
as `Guides-Reviewed: unchanged, because …`.  A convention that is not specific to the project
belongs in the global scope — forgetting that half is the failure this rule exists for.  A
machine-wide `commit-msg` hook (`core.hooksPath=~/.config/opencode/hooks`) refuses a code/config/CI
commit that carries neither a guide change nor the trailer; docs-only commits and repositories
without a guide pass, and `--no-verify` is the deliberate bypass.  The same hook runs
`scripts/style-lint.py` over the tracked Python files of **every** repository, gating the house
keyword-`=` spacing at commit time (merge/revert commits skipped, fails open when the interpreter
or script is missing).

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
- **Never put secrets or addresses in commits.**  Machine endpoints, proxy addresses, API keys,
  cluster IPs and the cluster's OTP seed stay in untracked files or environment variables.  The
  seed lives in `~/.config/oathpass/config.json`, which is the only place `scripts/oathpass.c` reads
  it from; since the cluster asks for the OATH code alone, that file holds the whole cluster
  credential and stays mode 600.

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
| a cluster login, a read-only remote command, or a file transfer | `hpc-cluster` |
| coding style, git/PR rules, LaTeX writing or source style | `repo-rules` |

Load and apply the matching skill as soon as the trigger appears; do not ask the user whether a skill
may be used.

## Cluster use requires approval

The HPC cluster is for work that genuinely exceeds this Mac: long DMRG/moments/FSSH sweeps, large
parameter scans, or anything needing far more than the local eight cores.  A session **states the
estimate** (cores, expected wall time, why local is not enough), **asks**, and waits for a yes.  A
"no" ends that subject for the task -- do not re-ask, and do not work around it.

Approved work is batched: one script per approval, not a stream of small commands, because the
permission rule below prompts the user on every shell command that names `oathpass`.  Finish with
`oathpass close`.  The `hpc-cluster` skill carries the workflow, the guarded `run` door, and the
honest note that the guard is a tripwire rather than a jail.

## Keeping these rules current

Whenever a session in **any** repository establishes a convention that is not specific to that
project — a coding style, a commit/PR rule, a LaTeX style, a tool workflow, a pitfall — record it
here or in the matching global skill as part of the same task, then commit and push this repository
(`myhsia/workbench`, checked out at `~/.config/opencode`).  Check every time; never leave a general
rule trapped in a project guide.

The daily upkeep check is `~/.config/opencode/scripts/update-due.sh`; the guide freshness check is
`~/.config/opencode/scripts/guides-due.sh` (both used in "At session start").
