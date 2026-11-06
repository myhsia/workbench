# workbench

Machine-global OpenCode configuration for this Mac, checked out at `~/.config/opencode`
(so these files are the live configuration, not copies).

- `AGENTS.md` — the global instruction file, loaded by every OpenCode session.
- `skills/` — the global skills: `repo-rules` (coding style, git/PR, LaTeX, upkeep),
  `session-hygiene`, `opencode-hpc-update`, `network-access`, `ci-artifacts`.
- `scripts/update-due.sh` — the daily upkeep check used by `opencode-hpc-update`.
- `scripts/guides-due.sh` — the guide freshness check used by the commit gate in `repo-rules`
  (exit 0 = `STALE`, 1 = `OK`, 2 = `MISSING`); `--committed` judges the history only, which is
  what the session-start check needs.
- `plugins/upkeep/` — refreshes the Westlake model list once a day and announces the OpenCode half
  of the daily upkeep; the markers it writes stay untracked.
- `.models-ignore` — the model ids the plugin must never add back, one per line, because they were
  removed from `opencode.json` on purpose.
- `opencode.json` — the global config (providers, compaction, tool output).
- `templates/` — the skeletons a new repository copies: `templates/AGENTS.md` to its root
  `AGENTS.md`, and `templates/repo-topic/SKILL.md` to `.opencode/skills/<name>/SKILL.md`.

Secrets and machine-local state — `proxy`, `service.json`, `cli.json`, `.update-check`,
`.models-check`, `opencode.json.bak` — are untracked.

Project-specific configuration stays in the project: each repository has its own `AGENTS.md` and
`.opencode/skills/`, and a workspace may add its own `opencode.json` (for example the
`~/GitHub/Dou_Group` workspace's path guards).
