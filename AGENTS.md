# oqs workspace

This directory holds two related repositories:

- `mkct/` — the MKCT manuscript code. Its full guide is `mkct/AGENTS.md`.
- `heomXdmrg-spin_boson/` — the public companion repository (shared config / HEOM / library
  files and the MPS/tDMRG reference). Its guide is `heomXdmrg-spin_boson/AGENTS.md`.

Relative symlinks couple the checkouts (`mkct/source/{config,heom.py,library/...}` ->
`../heomXdmrg-spin_boson/source/...`), so the two must stay siblings here.

## Working here

- Before touching a project, read and follow that project's own guide (`mkct/AGENTS.md` or
  `heomXdmrg-spin_boson/AGENTS.md`); those are authoritative.
- Run git inside the project directory (`cd mkct` or `cd heomXdmrg-spin_boson`); `oqs/` itself is
  not a repository.
- The shared rules from `mkct/AGENTS.md` still apply: preserve the user's uncommitted changes and
  staging, commit only when asked, keep the guides in sync, never put secrets or addresses in
  commits.
- Session upkeep uses the `session-hygiene` skill (keep sessions whole; branch into a new session
  for a new topic; `type(things): …` titles); config/upstream upkeep uses `opencode-hpc-update`
  and `network-access`.
- `.opencode/` and `opencode.json` at this root belong to the **workspace**, not to either repository:
  the inner skills/scripts (HPC-update, session hygiene, the daily `update-due.sh`) and the
  permissions/compaction config.  The physics guide `.opencode/skills/SKILL.md` is a link to
  `mkct/.opencode/skills/SKILL.md`, which stays versioned in the private repo.  Neither repository
  carries its own `.opencode` or `opencode.json`.
- `bibliography/` (references and former-work code) and `admin/` are **workspace-level data**, outside
  both repositories; keep them here, not inside `mkct/` or `heomXdmrg-spin_boson/`.
