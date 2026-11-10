# workbench

Machine-global OpenCode configuration for this Mac, checked out at `~/.config/opencode`
(so these files are the live configuration, not copies).

- `AGENTS.md` — the global instruction file, loaded by every OpenCode session.
- `skills/` — the global skills: `repo-rules` (coding style, git/PR, LaTeX, upkeep),
  `session-hygiene`, `opencode-hpc-update`, `network-access`, `ci-artifacts`, `hpc-cluster`.
- `scripts/update-due.sh` — the daily upkeep check used by `opencode-hpc-update`.
- `scripts/guides-due.sh` — the guide freshness check used by the commit gate in `repo-rules`
  (exit 0 = `STALE`, 1 = `OK`, 2 = `MISSING`); `--committed` judges the history only, which is
  what the session-start check needs, and `--staged` judges the index, which is what the hook runs.
- `scripts/oathpass.c` + `Makefile` — `oathpass`, a small C tool that answers an SSH OATH/TOTP
  prompt from a local seed, so a cluster login needs no phone and no typing of host or port. It
  resolves host, user and login port from `~/.config/oathpass/config.json` (mode 600), and speaks the
  `One-time password (OATH)` prompt itself (RFC 6238; SHA-1/256/512). `make install` builds and
  copies it into `$(PREFIX)/bin` (default `~/.local/bin`) — the build output *is* the command, so
  there is no interpreter, no symlink and no bytecode cache. `make test` replays the RFC 6238
  vectors, `oathpass check` is a dry run, and `.github/workflows/ci.yml` runs both on Ubuntu, macOS
  and Windows (MSYS2). MIT licensed. Because the OATH code is single-use, the first command opens
  one multiplexed master connection and later commands, `sftp` and `scp` reuse it; `oathpass run`
  is a guarded read-only door for agents (see the `hpc-cluster` skill).
- `hooks/commit-msg` — installed machine-wide by `git config --global core.hooksPath
  ~/.config/opencode/hooks`; refuses a code/config/CI commit with neither a guide change nor a
  `Guides-Reviewed:` trailer, and skips docs-only, merge/revert, and repos without a guide.
- `plugins/upkeep/` — refreshes the Westlake model list once a day and announces the OpenCode half
  of the daily upkeep; the markers it writes stay untracked.
- `plugins/shell-guard/` — rejects a shell command from a Plan or Explore session that would write
  into a project (`>`, `tee`, `sed -i`, `rm`/`mv`/`cp`, `git add|commit|push|…`, `l3build`, a
  Python write); the temp tree stays writable. `guard.js` is pure logic with `test.mjs` beside it
  (`node test.mjs`); the plugin only reads the session's agent and directory.
- `.models-ignore` — the model ids the plugin must never add back, one per line, because they were
  removed from `opencode.json` on purpose.
- `opencode.json` — the global config (providers, compaction, tool output), plus
  `agent.title.prompt` pointing at `prompts/title.txt`.
- `prompts/title.txt` — the system prompt of the hidden `title` agent: the only instruction the
  auto-titler sees, so it carries the `type(things): subject` format. Edit it there, not in the
  skills, and confirm with `opencode debug agents`.
- `templates/` — the skeletons a new repository copies: `templates/AGENTS.md` to its root
  `AGENTS.md`, and `templates/repo-topic/SKILL.md` to `.opencode/skills/<name>/SKILL.md`.

Secrets and machine-local state — `proxy`, `service.json` (service password and `env`), `cli.json`,
`.update-check`, `.models-check`, `opencode.json.bak` — are untracked. `oathpass` keeps its own
config, and its seed, in `~/.config/oathpass/config.json` (mode 600, outside this repository).

Project-specific configuration stays in the project: each repository has its own `AGENTS.md` and
`.opencode/skills/`, and a workspace may add its own `opencode.json` (for example the
`~/GitHub/Dou_Group` workspace's path guards).
