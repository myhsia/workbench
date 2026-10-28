---
name: session-hygiene
description: OpenCode session management — remove rubbish, enforce the type(things) title format, and move off-topic content to the right session; records the procedure, never the content of individual sessions.
license: MIT
compatibility: opencode
metadata:
  audience: maintainers
  scope: session store
---

# Session hygiene (OpenCode session management)

How to manage OpenCode sessions — the procedure, not a catalog of what any session said. Re-inventory
the live sessions on every run; never hard-code session ids, titles, sizes, or topics here.

## Standard routine

When asked to "make up" / tidy the sessions, do these three, in order:

1. **Remove rubbish.** Rebuild each session (*Rebuilding*) with the bulky, low-information parts
   dropped: truncate `reasoning`, remove tool `file`/image entries and attachments **whole**, drop
   compaction checkpoints. Keep all user/assistant text, tool commands, and tool results.
2. **Check titles.** Every title must be `type(things): short sentence covering all items`, with
   `type` one of `feat`, `fix`, `tune`, `refactor`, `docs`, `chore`. Rename agent auto-titles that do
   not conform, without waiting to be asked; check titles whenever you open or list sessions.
3. **Check categories / off-topic content.** Classify each session by theme. If a block of turns
   clearly belongs elsewhere, move it (*Moving content*); if no session fits, create a new one with a
   `type(things): …` title. Split only when the themes are obviously different — a little overlap
   between sessions is fine (a bus branch line).

Report the before/after sizes and the resulting ids when done.

## Inventory

- List: `opencode session list` (top-level, current project, newest first).
- Size and composition, read-only:

  ```bash
  sqlite3 "file:$HOME/.local/share/opencode/opencode.db?mode=ro" \
    "select session_id, count(*), round(sum(length(data))/1048576.0,2) from session_message group by session_id order by 2 desc;"
  ```

  Never write the live DB; query it `mode=ro`.

## Hard rule

Never edit the session store by hand (`session_v2`, `session_message`). A one-off "prune" script that
rewrote `session_message.data` dropped the required `model` field and made every session open empty;
recovery meant re-adding `model` from `session_v2.model` and `VACUUM`. All changes go through the API
(export / import / delete / rename / move / revert).

## Rebuilding a session (export -> prune -> import)

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
- **Compaction is irreversible in place.** `compaction.auto: false` only stops new automatic runs
  (installed checkpoints remain; there is no un-compact). Drop the `compaction` message to un-compact
  the copy.
- **Export only works for an existing session**: a deleted one returns `SessionNotFoundError` (404).
- **Verify before deleting the original**: `GET /api/session/<id>/context` returns HTTP 200, and a scan
  shows no empty inline files. Keep the source until then, then delete it.
- **Pruning the current session** creates a new id and deleting the old one ends the live
  conversation: create the pruned copy, keep the original, switch to the new id, then delete the old.

**Conversation-only rebuild.** When the session's value is its *instructions and decisions* rather
than its tool transcript, keep only the `user` messages and the `assistant` messages that carry
`text` (drop their `tool`/`reasoning` parts, and drop the `synthetic`/`idle`/`agent-switched`
markers). The procedure belongs in the skill, not in the transcript, so this shrinks a session by an
order of magnitude (e.g. 2.8 MB -> 0.2 MB) while keeping what the user asked for and the assistant's
summaries. Export the full session first if the tool record might be needed.

## Moving content between sessions (merge / split)

There is no append API: to move turns, rebuild a **new** session from the export(s).

1. Export the source session(s). The export carries message ids, not `seq`, so map the turns to move
   by querying `session_message.seq` for the ids.
2. Build the destination message list: the target's messages plus (or minus) the selected ids, in
   order.
3. Prune, assign fresh ids, and import as the destination (`info` from the target, title per
   convention); rebuild the source without those ids if it should be trimmed.
4. Verify both, then delete the sources. Report the new ids.

`POST /api/session/{id}/fork { before: <msg_id> }` gives one branch (not a partition).

## Session titles

`type(things): short sentence covering all items (several words)`, `type` ∈
`feat|fix|tune|refactor|docs|chore`. Rename via the session-rename tool; keep the id stable.

## Compaction (opt-in only)

Default is **no compaction**; keep the session whole and branch instead. Compaction
(`POST /api/session/{id}/compact`) keeps `keep.tokens` verbatim and summarizes the rest — lossy
in-context. V2 ignores the V1 `prune` / `tail_turns` fields.

## Deleting or hiding turns

`/undo` (`session.undo`) only **hides** turns — it sets `session_v2.revert` and does not delete
anything. It is not a delete tool. Pick the mechanism that matches the intent:

- **Delete turns (permanent).** Export the session first as a backup, then stage at the **first
  message to remove** and commit:

  ```sh
  POST /api/session/{id}/revert/stage  {"messageID": "<first to remove>", "files": false}
  POST /api/session/{id}/revert/commit
  ```

  The commit deletes `seq >= boundary`, so stage at the first turn to drop, **never** at the turn you
  want to keep (staging one message earlier would delete that message too). `files: false` leaves the
  working tree alone. (Alternative: rebuild via export -> import without those turns — new id.)
- **Un-hide a stray `/undo`.** `DELETE /api/session/{id}/revert` (HTTP 204), then rescan
  `select id from session_v2 where revert is not null;`.
- **In the TUI**, avoid `/undo`: v1-migrated sessions lack `snapshot`s (it drops content), and v2
  sessions can leave the TUI unable to render earlier turns even though the store keeps them
  (reopen/reload to re-render). `session.undo` is `"none"` in `cli.json`, though the command palette
  can still reach it.

## Decide per session

- **Long -> branch:** continue in a new session with a short handoff line; overlap is fine.
- **Multi-topic -> split only if the themes are obviously different.**
- **No compaction by default.**
