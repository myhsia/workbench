# OpenCode on this Mac — the handbook

This is the narrative record: what we settled, what it cost to settle, and the mistakes that
became rules.  It is **not** the enforced configuration — `AGENTS.md`, `skills/` and
`opencode.json` are.  Where the two disagree, the config wins and this file is wrong and gets
fixed.

Numbers below carry their provenance: *measured* means a run during the 2026-11 work (or, for the
2026-11-11 items, during the 2.2.7 check), *derived* means computed from a recorded export or
database, *fitted* means tuned to a target.  Nothing here is a remembered impression.

---

## 1. Titles

Every session title is `type(things): short subject`, `type` in `feat|fix|tune|refactor|docs|chore`.

The auto-title is written by the hidden `title` agent, and its system prompt is the only
instruction it ever sees — it does not read `AGENTS.md` or a skill.  That prompt is ours:
`prompts/title.txt`, wired as `agent.title.prompt`.  A drifting title therefore means the prompt
file needs a look, not that an agent forgot to rename.  Sessions titled before the prompt existed
keep their titles; rename them in passing.

Measured behaviour (v2.2.5/v2.2.6): the title is generated from the first message, a later turn
does not regenerate it, and a manual rename wins over a generation still in flight (the generator
aborts when the title changed).  Verify the loaded prompt with `opencode debug agents` — it appears
as the agent's `system` field — not by assumption.  In v2.2.7 generated titles no longer carry the
model's commentary (release note #62267, not separately measured here).

## 2. Plan mode

Plan mode is enforced by permissions, not by the prompt that announces it.  The order is: each
agent's own defaults, then the global `permissions` block, then the project's — last match wins.  A
blanket `edit` allow in the global block therefore cancelled Plan's deny, which is exactly how Plan
edited files under v2.  The global block now carries **deny rules only**.

`agent.plan` and `agent.explore` allow `edit` only under `{env:TMPDIR}opencode/**` and (for plan)
`{env:HOME}/.opencode/plan/**`; everything else is denied.  The config names the roots through
`{env:…}` so no machine id is committed; macOS spells the same temp tree `/var/folders/…` and
`/private/var/folders/…`, and both are listed because the matcher compares strings, not inodes.
The effective list is checkable: `opencode debug agents` shows `edit * deny` followed by the two
roots (re-verified on 2.2.7, 2026-11-11).

Shell is path-blind — its permission resource is the command text, not the working directory — so
`plugins/shell-guard` inspects each shell call from a plan/explore session and rejects writes:
unquoted `>`/`>>`, `tee`, `sed -i`, `perl -i`, `rm`/`mv`/`cp`/`rsync`, `git add|commit|…`,
`l3build`, `tlmgr`, a Python write.  Quoted text is ignored, so `echo "a > b"` and `grep '>' file`
pass.  The rules fire in **command position** only, so `grep -rn install .` stays allowed while
`node -e "…os.remove(…)"` is still refused, and an unrecognised wrapper (`foo rm x`) is not seen.
`guard.js` is pure logic with `test.mjs` beside it — `node plugins/shell-guard/test.mjs` reports
`all pass (52 cases)` (2026-11-11).

Two behaviours worth remembering: a **denied tool leaves the effective list**, so calling it fails
with `No tool named "shell" is currently available` rather than a permission error (a denied `read`
says `Permission denied: read`).  And a guard false positive once blocked a command merely because
its *quoted argument* contained `> path`; the quote-aware scanner fixed it.

## 3. The guide gate

After every build run that changes code, configuration, CI or output, check **both** scopes:

1. the working repository — `AGENTS.md`, `.opencode/skills/`, `opencode.json`;
2. the machine-global configuration — `~/.config/opencode/AGENTS.md`, `skills/`, `opencode.json`.

Update whichever is stale in the same commit; otherwise record
`Guides-Reviewed: unchanged, because …`.  A `commit-msg` hook installed machine-wide
(`core.hooksPath=~/.config/opencode/hooks`) refuses a code/config/CI commit that brings neither a
guide change nor the trailer; it chains to a repository's own hook, skips merge/revert commits,
docs-only diffs, and repositories without a guide.  `--no-verify` is the deliberate bypass.

`scripts/guides-due.sh` answers "has the guide moved since the code": `--committed` judges history,
`--staged` judges the index (what the hook runs).  The history branch ignores commits carrying the
trailer, because the trailer is the gate's own escape hatch.  A prose tree (`context/`) and a prose
file (`README.md`) are excluded — a README-only commit otherwise reported STALE for ever.

The gate compares commit order, not content: it cannot see a convention that was never written
down.  That is why the review line matters more than the STALE/OK verdict.

## 4. The session store

Never hand-edit `session_v2` / `session_message`.  One recorded exception (2026-11-09): 102
`plan`-authored messages that had edited a repository were relabelled to `build` — the `agent` field
only — inside one `BEGIN IMMEDIATE`, after a whole-database `.backup`; verified `json_valid`, `model`
present, every other key byte-identical, row counts unchanged, encoder scan clean, `/context` 200,
and a real send.

Prune levels, measured before choosing:

| level | drop | keep |
|---|---|---|
| least clean | reasoning | every output, every input, text |
| medium | reasoning + tool outputs | tool **inputs** verbatim, text, attachments |
| D3 | the above + attachments + markers; inputs to identifiers | user/assistant text |

Measured during the 2026-11 prune on this Mac (not re-run since): 46 sessions, 50 MB; medium took
reasoning 5.9 MB + outputs 13.4 MB out, store 50 → 34.3 MB; 39/39 sessions text-identical to their
exports, one assistant row dropped because it had no text.  `ses_XphjKSfWnrxKA0yvDPJ2hSnRNW`
(1.61 MB, text-only) was split seven ways: formatter, packaging/CI, macOS chrome, macOS file list,
macOS panels, Windows GUI, drag/extension — each with an `Aim:`, `synthetic` transitions, a closing
`Finished Build`, and `agent: build`; the union of the seven is multiset-identical to the 3 680
source text parts.

Export → prune → import pitfalls, each learned the hard way:

- the import **requires `info.id`** and **`info.location`** (and a top-level `location`); a payload
  without them is a bare `Bad Request` — the CLI hides the reason, `opencode api POST
  /api/experimental/session/import --data "$(cat f.json)"` prints it;
- regenerate every top-level message id (local ids are globally unique); part ids may stay;
- local tools must be written with `executed: false`; `executed: true` replays the result inside the
  assistant message and the next send fails;
- assistant messages require `model`; a rebuild that drops it makes every session open empty;
- drop `snapshot` keys (otherwise `/undo` can fire on a rebuilt session), and omit `info.revert`
  (never `null`);
- delete attachment entries whole, never blank their data;
- a **running TUI shows an imported session blank** until relaunched (client marker), while export
  and `/context` are fine;
- deleting a session also deletes its child sessions — check `parent_id` first;
- the current session cannot prune its own row: export, build a new id, import, switch, then delete
  the old.

Compaction is irreversible in place and absent on this machine (no `compaction` rows; dropping one
is the only "un-compact").  `/undo` has an unfixed race: it can leave the turn visible to the model
while hiding it in the UI, and resending duplicates it.  Delete a suffix with `revert/stage` at the
first message to remove + `revert/commit` (`files: false`); a middle turn needs a rebuild.

Measured on 2.2.7 (2026-11-11): `opencode session export <id>` still streams JSON to stdout and
creates no file, so the redirect in `session-hygiene` is unaffected by the release note that the
app's *export* action now writes into the current directory.

## 5. Orchestration

The pattern that works: **gather → aggregate → decide → execute**, one session at a time.

1. **Audit** each session read-only, in Plan (`opencode run -s <id> --agent plan --auto "…"`),
   asking it to name its own commits, judge `gap: none|local|global|both`, propose the exact guide
   edit, and list questions.  One full context replay per run, so sequence, never fan out, and wrap
   each in `timeout` (v2.2.6 waits for background jobs with no deadline).
2. **Aggregate** the replies into one decision sheet; deduplicate global proposals against the
   skills, because a later audit will otherwise re-add a rule that already exists.
3. **Decide once** with the user; "all recommended" is a valid answer.
4. **Execute by the owning session**, in build, with the answers and the instruction in one message.
   One owner per repository and one for the machine-global config; `LuaCJK`'s 13 sessions were
   serialised, and the global `repo-rules` edits were committed one session at a time.
5. **Leave no session parked**: after the run, `POST /api/session/{id}/agent {"agent":"build"}` for
   every session whose audit found nothing.  Five Dou_Group sessions were left in Plan because their
   audits had no work — that was an omission, not a policy.

The audits' most common finding was "already documented": the global skills had the rule, the
session had not followed it.  The missing rules were concentrated in TeX-on-CI and docext.

### The second pass, 2026-11-11: the questions that survived

The first pass switched to build only the sessions whose audit found **work**.  A session whose
audit ended in questions stayed in Plan with those questions as its last message — the residue was
invisible because "parked" had been read as "found nothing to do".  Two failures compounded it: the
questions were handed to the user instead of being answered, and being generic (guides, CI, commit
gates) they drifted off the session's title.  Measured: of the 30 sessions carrying the standard
audit turn, two ended with eight open questions, one sat in Plan for seventeen hours and stopped
inside a tool call, and seven others needed a second "check for residue" prompt before their
questions were answered — several of those answers then arrived as four more turns.

What was done: those sessions were closed in build with `Residue: none` (LuaCJK commits `999dac7`,
`dc311cb` for the eight answers), the audit exchanges were removed in place — **478 whole messages
across 30 sessions**, one transaction each, after a `.backup` to
`~/.local/share/opencode/session-backups/opencode-2026-11-11-preprune.db` and a
`PRAGMA integrity_check`, with every remaining row `json_valid` and ids and titles unchanged — and
three kept replies lost their trailing offers.  The lesson is now a rule in `AGENTS.md`
§Orchestrating other sessions: **an audit's questions are answered by the orchestrator, a session
ends in build with `Residue: none`, and the finding stays inside the title**.

## 6. Upkeep

- `scripts/update-due.sh` — the day (Asia/Shanghai) has no stamp → due; `--mark` stamps it.  No
  17:00 rule.
- `scripts/guides-due.sh` — per repo, `--committed` for session start, `--staged` for the hook.
- `plugins/upkeep` — refreshes the Westlake model list once a day, injects the two-scope guide line,
  runs the repository's declared `Session check:` (bash, ~10 s budget), and reports both scopes'
  guide verdicts.
- `plugins/shell-guard` — the Plan/Explore shell write guard described above.
- Westlake: `deepseek-flash`, `glm-flash`, `Qwen` online; `Qwen_claude` ignored on purpose
  (`.models-ignore`); the embedding/reranker ids are not chat models.
- Backups live under `~/.local/share/opencode/session-backups/` (three files, 7.3 MB on 2026-11-11)
  and are deleted only on explicit agreement, with their references cleaned in the same task.

Measured on 2026-11-10 at v2.2.6: CLI and service both that build, the latest release, and the model
list unchanged.  Re-checked on 2026-11-11 at **v2.2.7** (latest, published 2026-11-10): CLI and
service agree; the Westlake SPA's `models:` array still shows 3 online chat models, 2 serving-only,
6 `offline:!0`; the provider answers `activation: "enabled"`, and `opencode models` lists exactly
three.  Two 2.2.7 breaking items were read and dismissed for this setup: `@opencode/ai`'s
`ImageResponse.image` removal (our plugins import `@opencode/plugin` alone) and the shorter plugin
wait (visible only as a partial `agent.list` at start-up).  The `/api/provider/<id>` route that 2.2.6
dropped answers again.

## 7. Lessons

- **The guard is the config, not the prose.**  Plan mode was bypassed for weeks because one global
  `edit` allow was merged after the agent's deny; the reminder in the prompt never mattered.  Check
  `opencode debug agents` for the *effective* order.
- **Do not over-tighten.**  Denying `shell` outright made Plan unable to run `git status`; models
  then answered from stale data and the user saw a broken mode.  The rule is narrow: commands yes,
  writes only into the temp tree.
- **Verification must be measured.**  Every claim in this work carried the command and its output:
  the 39/39 text-identical prune, the 3 680-part split, the hook's block and pass cases, the guard's
  52 unit cases, the four plan sessions that hit `No tool named "shell"` before the fix.
- **A wrong claim is corrected in place.**  An audit once said `guides-due.sh --staged` was
  unimplemented; it was implemented and exercised, and the skill said 2.2.6 had removed
  `/api/provider/<id>` when 2.2.7 serves it again.  Both corrections are recorded rather than
  dropped.
- **Never print raw API bodies.**  On 2026-11-11 a `head -c 300` of `/api/model` wrote the resolved
  provider key into a transcript.  `/api/provider`, `/api/model` and `/api/config` all carry it in
  plaintext; parse, print ids and a key *length*.
- **The hook only enforces the local half.**  Whether a convention belongs in the machine-global
  scope is a judgement; the rule, the per-turn reminder and the trailer are what carry it.
- **A question is not a closure.**  A session that ends on a question reads as finished to a script
  and as unfinished to the user.  The end state has to be a line the orchestrator writes —
  `Residue: none` — not a question it forwards.  The 2026-11-11 pass is the proof: 30 sessions
  "completed", two of them with eight open questions, and one stopped mid-tool-call for seventeen
  hours.
- **Duplication is allowed.**  Branching (a bus line) beats compacting; a little overlap between
  sessions keeps each readable.  "Finished Build" closes a thematic copy.
- **A guide gap outlived its own gate.**  The extended-DEOM filtering change carried neither a guide
  change nor a `Guides-Reviewed:` trailer, so `guides-due.sh --committed` read STALE until the
  pitfall and the reference-solver gates were finally written, two commits later, by an audit of the
  session's own claims.  A check nobody runs reports nothing, which is why the per-turn reminder
  carries the convention and the hook only backstops it.

## 8. The first CTAN release

LuaCJK v0.0.1 was the first release prepared under these rules (2026-11-11).  Three things were
learned, and all three are now in the `CTAN releases` section of `repo-rules`.

- **The package id is lower case, and it is the archive's top directory.**  `build.lua` had
  `module = "LuaCJK"` on the reading that `module` is the CTAN name, so `l3build ctan` produced
  `LuaCJK/` and `LuaCJK.tds.zip`; CTAN's submit interface accepts `pkg` as lower-case letters only
  and answers *Unexpected top level directory* when the two differ.  Nothing local catches it:
  every test passes and both archives look well formed.  The fix is a derived variable —
  `local pkg = string.lower(module)`, handed to `ctanpkg` — not a second spelling of the package:
  putting the id in `module` also makes the tag, the repository URL and the changelog heading
  lower case, and moving `moduledir` out of `l3build`'s way is impossible, because
  `l3build-variables.lua` assigns it after `build.lua` is read.  So the tds zip keeps
  `doc/latex/LuaCJK/` and `source/latex/LuaCJK/`, accepted rather than fixed.
- **A TDS zip does not need permission.**  The belief that CTAN rejects `.tds.zip` files unless
  TeX Live asks for them is wrong: its guidelines prescribe exactly l3build's layout, `pkg/` beside
  `pkg.tds.zip`, and file the zip under `install/`; `xeCJK` itself ships one.  It is worth creating
  only for a package that spans more than one `tex/` tree, which LuaCJK does.
- **`l3build upload --dry-run` is not offline.**  It skips publication but still posts the archive
  to `ctan.org/submit/validate`, so a rehearsal with no network needs a `curl` stand-in on `PATH`
  that saves the `--config` file and exits 0 — which prints every field and the exact form without
  sending it.  A case-insensitive file system then produced the session's only self-inflicted
  casualty: `LuaCJK-ctan.zip` and `luacjk-ctan.zip` are one file on APFS, so cleaning up the old
  spelling deleted the new archives, and `l3build ctan` had to be run a second time.

## Decisions, verbatim

Each line is the user's own wording, and what it settled:

| verbatim | settled |
|---|---|
| `medium` | prune at the medium level — reasoning and tool outputs out, tool inputs, text and attachments kept |
| `All of the session: if any msg is plan but the agent edited it, then change the label to build` | the 102-message relabel, `agent` field only, inside one transaction after a full backup |
| `one combined build run` | orchestration executes in a single build pass, not a session per finding |
| `Confirm the ownership` | one owning session per repository and one for the machine-global config, named before the run |
| `Delete the prune backups` / `Delete the backup` | backups are removable, but only on explicit agreement, with their references cleaned in the same task |
| `leave shell` | the Plan guard keeps `shell` available and narrows it; it is not denied outright |
| `hard block` | a rule that must be refused by configuration, not merely discouraged by a prompt |
| `Keep the verbatim user decisions` | this table exists; later summaries quote the user, not a paraphrase |
| `@opencode-hpc-update v2.2.7 updated` | the version check is re-run after an upgrade, and the skill records what changed |
| `module = "luacjk", hardcode LuaCJK` | the CTAN id and every TDS directory are lower case; `LuaCJK` survives only where it names the package |
| `Keep v0.0.1` | a first public release may carry the number the sources already use; no `\changes` rewrite |
| `Pack and inspect only` | the archives and the form are verified locally, and nothing is sent to `ctan.org` |
