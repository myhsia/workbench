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
opencode session export <id> > export.json
# edit export.json: drop the compaction message, trim bulky parts (remove attachment entries whole), then
opencode session import payload.json --directory <dir>
```

(`opencode api post … --data @file` does **not** read the file: it sends the literal `@file` and
fails with HTTP 400 `Expected a valid JSON body`. Use `opencode session import`, which resolves the
location and posts the body, or pass the JSON as a plain string.)

Pitfalls, each learned the hard way:

- **The id is yours to choose.** Import uses `info.id`; it fails with `ConflictError` (HTTP 409) only
  while a session with that id still exists. To keep the id, export, delete the original, then import
  (keep the export and a DB copy until verified); otherwise import under a new id and delete the
  original afterwards.
- **New message ids.** Reusing `msg_…` ids fails (HTTP 500, no body): local ids are globally unique.
  Regenerate every top-level message `id`; part ids (e.g. `chatcmpl-tool-…`) are fine unchanged.
- **`executed` means provider-executed, not "the tool ran".** Local tools (`shell`, `read`, `write`,
  `edit`, …) must be written with `executed: false` (or the key omitted). With `executed: true` the
  transcript replays the tool result *inside* the assistant message; the OpenAI-Chat and
  Anthropic-Messages encoders accept only text/reasoning/tool-call there, so the next send fails with
  `… assistant messages only support text, reasoning, and tool-call content for now` — the session
  still opens and renders, which hides the damage until a prompt is sent. Fix by exporting, setting
  every local tool part to `executed: false`, and rebuilding (the same id can be kept, see above).
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
- **Verify before deleting the original**: `GET /api/session/<id>/context` returns HTTP 200, the
  scan in *Verify a session is encoder-safe* below returns nothing, and a send actually succeeds
  (the encoder only runs on send; opening the session proves nothing). Keep the source until then,
  then delete it.
- **Omit `info.revert`, do not set it to `null`.** The import schema expects a
  `Session.Revert` object or the key absent; `revert: null` fails with HTTP 400
  `InvalidRequestError: Expected Session.Revert at ["info"]["revert"]`.
- **A running TUI shows an imported session as blank — restart it.** On `session.created` the client
  marks `session.message:<id>` as done (`pdu()` in 2.2.0: `complete()` sets the key to `true`, and
  `run()` on a done key returns without fetching). An `opencode` that was already running when the
  import happened therefore has that marker for the id (new id or reused id alike) and never loads
  the transcript: the session opens empty, while `opencode session export <id>` lists every message
  and `GET /api/session/<id>/context` returns 200. The marker is only cleared by
  `session.deleted` or a process restart, so quit and relaunch the TUI (or any client) before
  judging an import. A fresh client fetches the transcript in chronological order (the message list
  is ordered by `seq`/time, not by id, so regenerated ids do not affect display order).
- **Pruning the current session** creates a new id and deleting the old one ends the live
  conversation: create the pruned copy, keep the original, switch to the new id, then delete the old.

## Verify a session is encoder-safe

The encoder only runs when a prompt is sent, so a damaged transcript still opens and renders. Run
this scan after **any** rebuild, import or hand edit; all four queries must return nothing (a row
means that session will fail on its next send):

```bash
DB="file:$HOME/.local/share/opencode/opencode.db?mode=ro"
# a) provider-executed tool parts: executed=true replays the result inside the assistant message
sqlite3 "$DB" "select m.session_id, count(*) from session_message m, json_each(m.data,'\$.content') p
  where m.type='assistant' and json_extract(p.value,'\$.executed')=1 group by 1;"
# b) empty inline attachments: the send fails with 'cannot identify image file'
sqlite3 "$DB" "select m.session_id, count(*) from session_message m, json_each(m.data,'\$.files') f
  where m.type='user' and json_extract(f.value,'\$.source.type')='inline'
    and length(coalesce(json_extract(f.value,'\$.data'),''))=0 group by 1;"
# c) assistant content outside text/reasoning/tool-call
sqlite3 "$DB" "select m.session_id, json_extract(p.value,'\$.type'), count(*) from session_message m,
  json_each(m.data,'\$.content') p where m.type='assistant'
  and json_extract(p.value,'\$.type') not in ('text','reasoning','tool') group by 1,2;"
# d) compaction messages: only replayable to the provider/API that produced them
sqlite3 "$DB" "select session_id, count(*) from session_message where type='compaction' group by 1;"
```

`executed=true` is the only one that appears without a hand edit (an old rebuild template wrote it);
ordinary runtime writes `false` for every local tool, so a clean scan stays clean. Repair in place
without export/import: flip `content[*].executed` to false in `session_message.data` inside one
`BEGIN IMMEDIATE`, then re-run (a) and send.

## Deep clean (D3, conversation-only)

The default deep clean when sessions approach the context limit.

**Export a backup of every session first** (`~/.local/share/opencode/session-backups/<id>.json`,
mode 600) and keep it until the rebuild is verified. The rebuilt rows replace the originals
in place and are **not** recoverable afterwards: deleting the rebuilt session and re-scanning
the database finds only older generations, not the immediately previous payloads.

Keep:

- every **`user`** message verbatim (`text`; drop `files`);
- every **`assistant` `text`** verbatim;
- every tool call as a **native tool part** (so the TUI renders a tool row, not prose):

  ```json
  { "type": "tool", "id": "<new>", "name": "shell", "executed": false,
    "state": { "status": "completed",
               "input": { "command": "<full command>" },
               "content": [{ "type": "text", "text": "" }],
               "metadata": { "status": "completed" } },
    "time": { "created": <ms>, "ran": <ms>, "completed": <ms> } }
  ```

  - `input` keeps only the **identifier** fields: `shell`/`bash` `command`; `read`/`write`/`edit`
    `path`; `grep` `pattern`+`path`+`include`; `glob` `pattern`+`path`; `webfetch` `url`+`format`;
    `websearch` `query`; `skill` `name`; `execute` `code`; `todowrite` `todos`; `question` `questions`.
  - **drop** `state.content` payload (the output), `state.metadata` diffs/diagnostics, and the file
    **bodies**: `write.input.content`, `edit.input.oldString`/`newString` (the code is in `git`).
  - import schema requires all of: `state.content` **with at least one item** (use
    `[{"type":"text","text":""}]`), `state.metadata`, and `time.created/ran/completed`. For
    `status: "error"` also set `state.error = {"type":"tool.execution","message":"<text>"}`.
  - never trim `input` values.
- `time`, `agent`, `model`, `finish`, `cost`, `tokens` on assistant messages (`model` is required).

Drop: `reasoning`, the tool **outputs** (`state.content`, `state.metadata`) and file bodies,
attachments/images, compaction messages, and every non-`user`/non-`assistant` marker (`idle`, `synthetic`, `agent-switched`,
`model-switched`, `location-switched`, `system`, `shell`). Assistant turns left with no text are
dropped, which removes tool-only steps.

Measured: a 33.7 MB project store (24 sessions, real requests up to ~600 k tokens) becomes
~13 MB of text, no session above a few hundred k tokens. `git` holds the code, so the dropped
tool bodies are recoverable there.

Also cap future growth in the project config (V2 field, verified in 2.2.0):

```jsonc
"tool_output": { "max_lines": 500, "max_bytes": 32768 }
```

## Removing `/undo` traces

After an `/undo` (or after a raced one), a session can keep `session_v2.revert` plus per-message
`snapshot` keys, and the TUI then hides turns. To clean it without hand-editing the store:

1. Export the session; keep a backup.
2. `B` = `seq` of `revert.messageID`. In the export, **drop the undone block** (the messages the mark
   hides, typically 1–2 right after `B`), but **keep any turn sent after the undo** — resolve it by
   the first `user` message whose `seq > B` (its turn is new, not undone).
3. Omit `info.revert` and delete every `snapshot` key from assistant messages, so `/undo` cannot fire
   on that session again (file rollback then goes through `git`).
4. Rebuild (fresh ids), verify, delete the original. Confirm `select count(*) from session_v2 where
   revert is not null;` is 0 afterwards.


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

`/undo` (`session.undo`) sets `session_v2.revert`; it never deletes rows, and when it races (next
section) it does not even reliably hide them. Pick the mechanism that matches the intent:

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

## `/undo` is an unfixed race — avoid it

`/undo` has a known **race** (upstream #54150, open, labelled `reproduced`; reproducer script in the
thread):

- If `/undo` lands **before the reply starts streaming**, the turn is **not reverted** at all: the
  prompt *and* the reply stay in the store **and in the model context**. The UI looks rolled back,
  but the model still sees the turn — the "memory exists, nothing visible" symptom.
- Resending the restored prompt then stores it **again**, so the model sees that turn **twice** (and
  repeated attempts pile up more copies).
- `/undo` after the reply is streaming or finished removes the turn correctly.

Status: the direct fixes are **open, not merged** (#55394 `park execution while a revert is staged`,
#55403 `preserve surviving input through committed reverts`); #54163 was **closed unmerged**. No
commit on `main` references #54150, so current releases have no fix.

Consequences:

- Never use `/undo` to delete turns — use *stage + commit* above.
- Do not `/undo` immediately after sending; if you must, wait until the reply has finished.
- Expect **duplicate copies of the same prompt** in sessions where this race happened (a repeated
  "…didn't render correctly, can you …" prompt many times is the signature). Removing a duplicate in
  the *middle* of a session needs a rebuild (export -> drop -> import; new id); stage+commit only
  deletes a suffix.
- `session.undo` is `"none"` in `cli.json`, but the command palette can still reach `/undo`.
- A stray mark left behind is still cleared with `DELETE /api/session/{id}/revert`.

## Decide per session

- **Long -> branch:** continue in a new session with a short handoff line; overlap is fine.
- **Multi-topic -> split only if the themes are obviously different.**
- **No compaction by default.**
