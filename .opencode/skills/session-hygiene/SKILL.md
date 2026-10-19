---
name: session-hygiene
description: Keep OpenCode sessions under the context limit by keeping each session whole and opening a new branch session to continue (a little overlap is fine); compact or split only on explicit request; never edit the session store by hand.
license: MIT
compatibility: opencode
metadata:
  audience: maintainers
  scope: session store
---

# Session hygiene (avoid context limits)

Use when sessions grow long, when the context window bites, or when asked to tidy, rename, continue,
or split sessions in the current project.

## Hard rule

Never edit the session store by hand. `~/.local/share/opencode/opencode.db`, tables `session_v2`
and `session_message`, must be managed through OpenCode itself. A one-off "prune" script that
rewrote `session_message.data` dropped the required `model` field and made every session open empty;
recovering it required re-adding `model` from `session_v2.model` and `VACUUM`.

## Inventory

- List: `opencode session list` (top-level sessions, current project, newest first).
- Size/tokens per session, read-only:

  ```bash
  sqlite3 "file:$HOME/.local/share/opencode/opencode.db?mode=ro" \
    "select count(*) msgs, session_id from session_message group by session_id order by msgs desc;"
  ```

  Or copy the DB to a temp dir and query the copy (never write the live DB while the service runs).

## Decide per session

- **Long -> branch.** When a topic gets long, open a **new** session (a branch, like a bus 支线) for the
  continuation and write a short handoff line. A little duplication of context between the main
  session and its branch is fine — prefer that over shrinking the original.
- **Multi-topic -> split only if obvious.** Split into parts only when the themes are clearly
  different; otherwise keep the session whole and branch for the next topic.
- **Do not compact by default.** See below.

## Session titles

Convention: `type(things): short sentence covering all items (several words)` with `type` one of
`feat`, `fix`, `tune`, `refactor`, `docs`, `chore`. Real examples from this repository:

- `chore(pltools): legends, labels, grids, and paper figures`
- `refactor(io): moments filenames, save_time writer, fsutils, and config`
- `feat(sf): surface hopping (FSSH/MASH) and sh.py rename`
- `docs(repo): README, AGENTS, commits, and open items`

**Every session title must follow this convention.** OpenCode auto-titles some new sessions with a
plain description (e.g. `DMRG implementation for dynamics and correlations`, `Plot Pade orders ...`)
that does not conform. When a session you start gets such a title, rename it to `type(things): …`
without waiting to be asked, and check titles whenever you open or list the project's sessions.

Rename with the OpenCode session-rename tool (or the TUI); keep the session id stable.

## Compaction (opt-in only)

- Default is **no compaction**: keep the session whole and branch instead. Compaction is the only
  native context-reducer (`POST /api/session/{id}/compact`); it keeps the recent `keep.tokens`
  (60000) verbatim and summarizes the rest, so it is lossy in-context. Raw messages are never
  deleted, but there is no native un-compact.
- V2 is checkpoint-based and ignores the V1 `prune` / `tail_turns` fields.

## `/undo` is unsafe in v1-migrated sessions

`/undo` (keybind `session.undo`, default `<leader>u`) is snapshot-based. Sessions created under v1 and
migrated to v2 have assistant messages without a `snapshot` field, so `/undo` there does not stage a
clean, reversible rollback: it removes content and leaves a `revert` mark. Native v2 sessions (every
message carries `snapshot`) behave correctly. Identify a migrated session by its assistant messages
lacking `snapshot` (roughly, created before the v2 era). In those, do not use `/undo`; to revise,
revert files with `git` and continue in a new branch session.

Remedy if it has already happened:

- Clear the mark: `DELETE /api/session/{id}/revert` (HTTP 204) -> the hidden messages come back.
- Re-scan: `select id from session_v2 where revert is not null;`.
- If messages were truly removed, rebuild it (export -> import).

## Branching and splitting

- **Branch (preferred):** continue in a new session titled by the convention above, carrying a short
  handoff note. Overlap with the parent is acceptable.
- **Split (rare):** only when themes are obviously different. `POST /api/session/{id}/fork` takes
  `{ before: <msg_id> }` and returns **one** new session (a branch, not a partition);
  `opencode session export` / `import` can move a subset manually. Fork does not carve one session
  into several.

## Rebuilding a session (export -> prune -> import)

To get an un-compacted, pruned copy without touching the store, round-trip the session through the
export/import API:

```sh
opencode api get /api/experimental/session/<id>/export > export.json
# edit export.json: drop the compaction message, trim bulky parts (remove attachment entries whole), then
opencode api post /api/experimental/session/import --data @payload.json
```

Pitfalls, each learned the hard way:

- **New session id.** Reusing the source `info.id` fails with `ConflictError` (HTTP 409).
- **New message ids.** Reusing `msg_…` ids fails (HTTP 500, no body): local ids are globally unique.
  Regenerate every top-level message `id`; part ids (e.g. `chatcmpl-tool-…`) are fine unchanged.
- **Delete attachment entries, never blank their data.** Emptying `files[].data` while keeping the
  entry (`source: {type: "inline"}`) makes the session unopenable: on send it decodes an empty inline
  file and errors `Failed to load image: cannot identify image file`. Remove the whole file entry.
- **Inline files load as images**, so inline PDFs are unreliable; keep only small inline images, or
  drop attachments entirely.
- **`location` goes at the top level** of the import body (`{info, messages, location: {directory}}`);
  a location only inside `info` is ignored and the copy lands in the service's default directory.
  The CLI form is `opencode session import <file> --directory <dir>`.
- **Compaction is irreversible in place.** `compaction.auto: false` only stops new automatic runs
  (installed checkpoints remain; there is no un-compact). Drop the `compaction` message in the
  payload to un-compact the copy.
- **Export only works for an existing session**: a deleted one returns `SessionNotFoundError`
  (HTTP 404).
- **Verify before deleting the original**: `GET /api/session/<id>/context` returns HTTP 200, and a
  scan shows no empty inline files. Keep the source until then, then delete it.
- The import round-trip silently drops invalid or empty inline attachments, which is how the broken
  copy got cleaned up after the fact.
