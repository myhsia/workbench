---
name: repo-rules
description: Shared repository conventions: Python style, git/PR workflow, LaTeX writing and source style, tooling and upkeep
license: MIT
compatibility: opencode
metadata:
  audience: maintainers
  workflow: github
---

# Shared repository conventions

Workspace-level rules for every repository under `oqs/` (`mkct`, `heomXdmrg-spin_boson`, ...).
Project-specific rules (physics, config schema, figure layout, engine details) stay in each
repository's `AGENTS.md` and skill.

## Repository etiquette

- **Preserve the user's uncommitted changes.** If `git status` shows uncommitted changes you did
  not make, treat them as the user's intentional edits: never discard, revert, overwrite, or "fix"
  them back. Build on top of them; if they cause a problem (e.g., a compile overfull), flag it
  instead of silently undoing.
- **Preserve the user's staging.** When `git status` shows some paths staged and others unstaged,
  leave the index exactly as found --- never run `git add`, `git reset`, `git restore --staged`, or
  `git stash` to "tidy" it. Partly-staged work is intentional: the user keeps the remaining changes
  unstaged so they stay visible in `git diff`.
- **Keep the guides in sync (routine).** At the end of every task, review whether the repository's
  `AGENTS.md` and skill need updating --- new or changed files/scripts, commands, conventions,
  figures/plotting, or pitfalls --- and update them as part of the same task.
- **Commit by pathspec.** When another session may have staged files, commit with
  `git commit -- <paths>` so unrelated staged work is not swept into the commit.

## Python coding style

All Python code (not just the moment modules): spaces around `=` in keyword arguments and
decorator parameters (`BathMode(sig = -1, n = ...)`, `key = lambda x: (x.n, x.fam)`,
`@dataclass(frozen = True, slots = True)`), with consecutive keyword-argument lines of a call
aligning their `=` to one column; one parameter per line in multi-line signatures with
`) -> type` on the closing line, and a `# %%` marker at the top of a module.  File trees/tables
align their inline comments to a common column, and a related group of imports aligns the
`import` keyword.

## Git, commits, and pull requests

Commits follow `type(scope): short summary` with `type` among `feat`, `fix`, `tune`, `refactor`,
`docs`, `chore`; keep the subject imperative and concise.  Only commit when explicitly requested;
never commit secrets or `output/` artifacts (gitignored).  Never restage the user's work (see
"Preserve the user's staging" above); a mixed staged/unstaged index is intentional.

`gh` (GitHub CLI) is installed and authenticated (account `myhsia`; scopes `gist, read:org`,
`repo`, `workflow`).  Prefer it for GitHub-side and remote interactions: `gh repo view` (instead of
`git remote -v`), `gh pr`/`gh issue`/`gh release`/`gh run`, and `gh api` (instead of `curl` for
GitHub endpoints).  Local history operations (`git add`/`commit`/`push`) still use `git`; its remote
auth is backed by `gh` (run `gh auth setup-git` if push auth ever fails).

### Push and pull-request status

After every push, check the result and report it: `gh run list --limit 3`, or `gh run watch <id>`
for the run just triggered, and `gh pr checks <n>` when a PR is open.

Triage pull requests:

- **Dependabot version updates** (the `conda` and `github-actions` ecosystems): once the checks
  pass, approve and merge directly (`gh pr review <n> --approve`, then `gh pr merge <n> --squash
  --delete-branch`); no need to ask first.
- **Anything else** (contributor PRs, and external ones once a repository is public): read the
  change and its checks, summarize, and ask the user before approving or merging; never merge on
  your own.

## LaTeX writing style

- Impersonal prose (no first-person "we"); prefer "detailed workflow" over "by hand".
- Avoid em dashes (`---`) and long itemized lists; prefer prose with paragraph breaks.
- Define each acronym once at first body use (the abstract defines only those it reuses).
- Macros: `\kbproj0`/`\kbproj1` for same-label outer products and `\ketbra|a><b|` for cross
  products; `\iu` (imaginary), `\upe^{}` (exponential), `\d` (differential; never `\,`/`\!`
  or `\, \mathrm d`), `\ab(...)` delimiters (not `\left/\right`), and `\mathord\cdot`
  (not bare `\cdot`); use the `physics3` macros.
- No code-like strings in the rendered text (`\texttt{A-base\_line}`, filenames such as
  `moments.py`); describe physically and `\eqref`/`\zref` the relevant definition or section.
- Move over-long or multi-line inline formulas to a display; label and `\eqref` only if the
  equation is actually referenced.
- After an equation environment the text continues *without* paragraph indent; insert a blank
  line when the following sentence begins a new paragraph.
- Put a float's label **after** its `\caption`, not inside the caption.  Floats and cross-referenced
  sections use `\zlabel` (their references are `\zref`); `\label` is reserved for `\ref`/`\eqref`
  targets (equations and the remaining sections).  There is no auto-label hook.
- Label an equation only when it is actually `\eqref`-referenced; otherwise use an untagged display
  (`equation` environment to `\[…\]`, `align`/`multline` environment to `align*`/`multline*`), and
  downgrade any `\label` whose reference is later removed.
- Use `\equiv` when defining a new symbol; use `=` for derived relations and physical assignments.
- Keep cross-references label-strong: every symbol used should link, directly or via a chain, to
  its defining equation, and each `\eqref` should point to the equation that *explains* the
  quantity; after moving an equation, fix any ranges that then read backwards.
- Floats always use `[htbp]`, never `[tbp]`; full-width floats are a `figure` environment inside
  `\onecolumngrid`/`\twocolumngrid` (RevTeX), never `figure*`.  A figure may be stubbed with the
  TeX Live demo `example-image.pdf`.

## LaTeX source style

- Spacing (cosmetic but kept uniform): spaces around relations and binary operators
  (`a = b`, `a + b`, `a - b`), space before operator-like macros and before `\d`
  (`\lambda\omega_C \int ... \d x`), and align continuation lines under the leading expression;
  leave scripts compact (`\sum_{k=1}`).  Write single-token `\frac` arguments without braces
  (`\frac12`, `\frac2\pi`, `\frac\iu2`), and unbrace single-token sub/superscripts and `\text`
  arguments (`x^*`, `\omega_C^n`, `\text P`; keep braces for `^{-1}`, `^{\dagger}`).  Do not use
  `\,` in math.
- Fractions: write reciprocals as negative powers (`\omega^{-1}`, `\omega_C^{-2}`) rather than the
  `1/` slash; avoid a literally nested `\frac`-in-`\frac` (flatten the inner one); otherwise keep
  flat `\frac` (`\frac12`, `\frac2\pi`).
- Delimiters: wrap a math delimiter in `\ab` only when its content is tall enough --- it contains
  a large operator (`\prod`, `\sum`, `\int`, `\frac`), a `\hat` on an ascender (uppercase Latin;
  lowercase `b,d,f,h,i,j,k,l,t`; small Greek except non-ascenders such as `\rho`, `\sigma`),
  `^\dagger`, or a `\hat` raised into an exponent (e.g. `\upe^{-a'\hat q_j}`).  Content whose
  tallest hat is on a baseline non-ascender (`\hat q`, `\hat\sigma`), a lone baseline superscript
  (`^2`), or a `\upe^{...}` with no such hat stays plain (`U(\hat q)`,
  `[\hat\sigma_x,\hat\sigma_y]`, `\coth(\beta\omega/2)`, `o(\hat q_j^5)`).  Use plain `\ab`
  (auto) when a large operator is present, `\ab\big` when the height is from a `\hat`/`^\dagger`,
  and `\ab*` to keep a related set uniform at natural size (e.g. the commutator table, where
  `\sigma` would not grow but `\phi` would).  `\ab` already wraps `\left...\right` in
  `\mathopen{}\mathclose` (so never use bare `\left...\right`); a delimiter that must span a `\\`
  uses manual sizes (`\big`/`\Big`/`\Biggl`).
- Derivatives: do not use inline `\d A/\d B` (the `/` over-grows); use `\odv{A}{B}` (the
  `derivative` package's `\derivset{\odv}[style-frac-/ = \slashfrac[none]]` keeps its slash at
  natural size) or the display form.
- Alignment: `align`/`aligned` align the trivial `=`; use `alignat` when the left-of-`=` parts
  have quite different lengths (then left-align them).
- Alignment style: in `align`/`aligned`/`alignat` etc. write `& =` with a space (never `&=`);
  column-align the entries of matrices (`pmatrix`), `dcases`/`cases`, and tables in the source
  (pad each column to its maximum width, single ` & ` separators).
- Labelled (first-row/first-col) matrices: use `kbordermatrix` (`\kbordermatrix(){...}`);
  `nicematrix` cannot be used because it is incompatible with RevTeX (`revtex4-2`).  Leave the
  `\kbordermatrix` source layout as is (its label row/column need not be column-aligned); do not
  "tidy" it.
- Multi-line displays: a single formula broken at a binary operator (`+`, `-`, `\times`) uses
  `multline`/`multline*`; a display with two or more relations (several `=`) stays
  `align`/`aligned`.
- Case distinctions: use `dcases*` with case labels when the operator is identical across cases;
  when each case already has its own symbol, keep `align`/`aligned` with the labels on the
  left-hand side.
- Matrices: pure-numerical matrices are set in `psmallmatrix*` to fit the two-column width;
  symbolic or structured matrices keep `pmatrix*`.
- Long value enumerations: wrap a `\quad`-separated list that would overflow the column into an
  `alignedat` grid; otherwise keep it on one line.
- Standard identities: cite standard results (e.g. `DLMF` for the Gamma/polygamma integrals and
  kernels), not just the physics references.
- Single-letter superscript labels that could be misread as powers are parenthesized and upright
  (`\eta_n^{\text{(q)}}`, `\bm\Omega_n^{\text{(P)}}`); multi-letter labels (`^\text{bath}`,
  `^\text{anh}`) stay unparenthesized.
- Wick contraction diagrams: draw the contraction lines with the `simplewick` package
  (`\contraction` above, `\bcontraction` below), giving explicit rises and pre-args so that all
  pairings sit on one line.  State the thermal variance and occupation explicitly at their point
  of use.

## Tooling and upkeep

- **opencode (v2).**  `opencode.json` at the workspace root is kept in strict v2 form.
  `permissions` is an ordered array of `{action, resource, effect}` rules (the `edit` guard on
  restricted paths plus the matching `shell` guard on `rm`); v2 names the shell action `shell`,
  not `bash`.  `compaction` tunes context handling (`auto`, `keep.tokens`, `buffer`).
- The provider lives in the machine-global `~/.config/opencode/opencode.json` (native v2
  `providers` block, `package: "aisdk:@ai-sdk/openai-compatible"`, `settings.baseURL`).  The CLI
  moved under `session` (`opencode session export|import|list|delete`).  Tool names follow v2:
  `shell` (not `bash`), `subagent` (not `task`), and `read`/`edit`/`write` take `path`.
- **Network access.**  Governed by the global `network-access` skill: try a direct connection
  first and use the proxy address in `~/.config/opencode/service.json` → `env.HTTPS_PROXY`; only
  when a host is blocked or times out.
- **Daily upkeep (`opencode-hpc-update`).**  Not a scheduled job: when a user message arrives,
  quietly consult `.opencode/scripts/update-due.sh` (from the workspace root).  If it prints
  `DUE`, load the skill, refresh the config, and stamp the day with
  `.opencode/scripts/update-due.sh --mark`; otherwise carry on without mentioning it.  Timing is
  Asia/Shanghai, at most once per calendar day (due from 17:00 on a day not yet checked, or
  immediately if a whole day was skipped); the last date is in `.opencode/.update-check`.
- **Session upkeep (`session-hygiene`).**  Keep each session whole and branch into a new session
  rather than compacting; give every session a `type(things): …` title (rename any agent
  auto-title that does not conform).  Load the skill for the export → prune → import procedure
  and its pitfalls.  Never edit the session store by hand.

## Local and CI parity

CI builds the same environment from the repository's `environment.yaml` (same pinned interpreter,
channels, `requirements.txt`) and runs the same commands as locally.  When a dependency, the
interpreter pin/channels, a validation suite, or the conda interface changes, update both the
local setup and the CI workflow in the same change.  `environment.yaml` is the single source of
truth: the workflow must not hard-code its own interpreter version or channel list.
