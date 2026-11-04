# workbench

Machine-global OpenCode configuration for this Mac, checked out at `~/.config/opencode`
(so these files are the live configuration, not copies).

- `AGENTS.md` — the global instruction file, loaded by every OpenCode session.
- `skills/` — the global skills: `repo-rules` (coding style, git/PR, LaTeX, upkeep),
  `session-hygiene`, `opencode-hpc-update`, `network-access`, `ci-artifacts`.
- `scripts/update-due.sh` — the daily upkeep check used by `opencode-hpc-update`.
- `opencode.json` — the global config (providers, compaction, tool output).
- `templates/` — the skeletons a new repository copies to its own `AGENTS.md` and
  `.opencode/skills/SKILL.md` (never discovered as skills).

Secrets and machine-local state — `proxy`, `service.json`, `cli.json`, `.update-check` — are
untracked.

Project-specific configuration stays in the project: each repository has its own `AGENTS.md` and
`.opencode/skills/`, and a workspace may add its own `opencode.json` (for example the `oqs`
workspace's path guards).
