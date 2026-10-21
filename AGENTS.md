# oqs workspace

This directory holds three related repositories:

- `mkct-oqs/` — the MKCT manuscript code. Its full guide is `mkct-oqs/AGENTS.md`.
- `heomXdmrg-spin_boson/` — the public companion repository (shared config / HEOM / library
  files and the MPS/tDMRG reference). Its guide is `heomXdmrg-spin_boson/AGENTS.md`.
- `sh-oqs/` — the public surface-hopping (FSSH) reference. Its guide is `sh-oqs/AGENTS.md`.

Relative symlinks couple the checkouts (`mkct-oqs/source/{config,heom.py,library/...}` ->
`../heomXdmrg-spin_boson/source/...`), so the two must stay siblings here.

## Working here

- Before touching a project, read and follow that project's own guide (`mkct-oqs/AGENTS.md` or
  `heomXdmrg-spin_boson/AGENTS.md`); those are authoritative.
- Run git inside the project directory (`cd mkct-oqs` or `cd heomXdmrg-spin_boson`); `oqs/` itself is
  not a repository.
- The shared rules in the workspace `repo-rules` skill still apply: preserve the user's uncommitted
  changes and staging, commit only when asked, keep the guides in sync, never put secrets or
  addresses in commits.
- Shared conventions for both projects (repo etiquette, Python coding style, git/PR workflow, LaTeX
  writing and source style, tooling/upkeep, local/CI parity) are in the workspace `repo-rules` skill
  (`.opencode/skills/repo-rules/SKILL.md`); the project guides keep only their specific rules.
- Session upkeep uses the `session-hygiene` skill (keep sessions whole; branch into a new session
  for a new topic; `type(things): …` titles); config/upstream upkeep uses `opencode-hpc-update`
  and `network-access`.
- `.opencode/` and `opencode.json` at this root belong to the **workspace**, not to either repository:
  the inner skills/scripts (HPC-update, session hygiene, the daily `update-due.sh`) and the
  permissions/compaction config.  The physics guide is `mkct-oqs/.opencode/skills/SKILL.md` (pointed
  to by `mkct-oqs/AGENTS.md`); this workspace keeps no link to it.  Neither repository carries its own
  `.opencode` or `opencode.json`.
- `bibliography/` (references and former-work code) and `admin/` are **workspace-level data**, outside
  both repositories; keep them here, not inside `mkct-oqs/` or `heomXdmrg-spin_boson/`.

## Status check

After any change (and before reporting), check and report all four checkouts:

    git -C oqs                    status -sb
    git -C mkct-oqs               status -sb
    git -C heomXdmrg-spin_boson   status -sb
    git -C sh-oqs                 status -sb

A settled state shows `## main...origin/main` with HEAD == origin/main for each; call out a dirty
tree (and whose change it is) and any unpushed commit.  The full rule is in the `repo-rules` skill.
