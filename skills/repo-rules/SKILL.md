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

Machine-global rules: they load in every OpenCode session on this Mac, in every repository.
Project-specific rules (physics, config schema, figure layout, engine details) stay in each
repository's own `AGENTS.md` and `.opencode/skills/`.

This file lives in the global repository (`myhsia/workbench`, checked out at
`~/.config/opencode`); general conventions learned anywhere belong here.

## Repository etiquette

- **Preserve the user's uncommitted changes.** If `git status` shows uncommitted changes you did
  not make, treat them as the user's intentional edits: never discard, revert, overwrite, or "fix"
  them back. Build on top of them; if they cause a problem (e.g., a compile overfull), flag it
  instead of silently undoing.
- **Preserve the user's staging.** When `git status` shows some paths staged and others unstaged,
  leave the index exactly as found --- never run `git add`, `git reset`, `git restore --staged`, or
  `git stash` to "tidy" it. Partly-staged work is intentional: the user keeps the remaining changes
  unstaged so they stay visible in `git diff`.
- **Keep the guides in sync (routine).** At the end of every task, run
  `bash ~/.config/opencode/scripts/guides-due.sh .` in the repository and review whether its
  `AGENTS.md` and skill need updating --- new or changed files/scripts, commands, conventions,
  figures/plotting, or pitfalls --- and update them as part of the same task.  The script only says
  whether the guides are older than the code; what changed in them is still a judgement.
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

### `gh api` request bodies

`-f`/`--raw-field` sends the value **literally**, so `-f body=@file.md` posts the 16-byte string
`@file.md` (this happened once on a public issue). To read a value from a file use `-F`/`--field`
(`-F body=@file.md`), or pass a whole JSON body with `--input file.json`. After creating or editing
an issue/comment/release, print it back once (`--jq '.body'`, `--jq '.html_url'`) to confirm it
expanded before reporting success.

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

### Status check

Before reporting, run `git status -sb` in the global config repository (`~/.config/opencode`) and
in every sibling checkout named by the workspace guide.  State, for each, the branch, whether
`HEAD == origin/main`, and whether the tree is dirty.  A settled state is `## main...origin/main`
with `HEAD == origin/main`.  Call out uncommitted changes (and whether they are the user's or the
agent's) and any unpushed commit; never "tidy" the index to make it look clean.

### Commit gate (guides)

Before `git commit`, run the check rather than recalling it:

```bash
bash ~/.config/opencode/scripts/guides-due.sh .
```

It prints `OK`, `MISSING`, or `STALE` (exit 0 = stale, 1 = ok, 2 = missing),
counting uncommitted changes and commit order.  The session-start check runs the same script with
`--committed`, which judges the history alone; this gate runs the default form, because at commit
time the working tree is what is about to land.

- **`MISSING`** → **refuse**, and offer to create the guides from
  `~/.config/opencode/templates/AGENTS.md` and `~/.config/opencode/templates/repo-topic/SKILL.md`.
  Only an explicit, one-off instruction from the user lifts this.
- **`STALE`** → **warn**: "this change may alter documented behaviour — update the guide, or
  confirm nothing documented changed".  Do not commit until the user answers.
- **`OK`** → commit, unless the diff plainly changes something the guide documents but the guide is
  newer for a different reason; the numbers in this skill's tables are the thing to re-read.
- **State the review.**  The script reads commit order, not content, so it cannot see a convention
  that was never written down.  Whenever the staged diff touches code, config, CI, or output while
  neither guide changes, the commit message and the final report carry one line:
  `guides reviewed: unchanged, because …`.  `OK` answers "has the guide moved since the code", not
  "is the guide complete".
- **Docs-only commits** are never blocked.

## Project guide standard

Every repository carries two documents, filled from the code and kept true:

**`AGENTS.md`** (root) — build and orientation:

| section | content |
|---|---|
| title + intro | what it is, what it produces, sibling/shared dependencies |
| Shared rules | pointer to this skill; only exceptions stated locally |
| Environment | conda env, working directory for commands, entry points |
| Project layout | every tracked file/package, one line each, what is generated |
| Conventions and pitfalls | the non-obvious rules, with the reason |
| Workflows | copy-pasteable commands in dependency order, with runtimes |
| Validation | how correctness is checked, the command, the numeric criterion |
| CI | workflows, triggers, matrix, artifacts, local/CI parity |
| Git style | pointer here; repository-specific scopes only |
| Validity (scientific repos, optional) | each parameter and the measurement that justified it |

**`.opencode/skills/SKILL.md`** — the science/architecture the code cannot explain:

| section | content |
|---|---|
| frontmatter | `name`, and a `description` that says *when to use it* |
| Repository rules | pointer to this skill |
| Background | model/architecture, equations or schemas, approximations |
| Current work | what the code does today, its variants, outputs |
| Conventions | units, factors, rescaling, sign/branch conventions, name↔symbol mapping, file naming |
| Workflows and validation | how to run, how to know it worked |

**Review triggers** — update the guides in the same task when any of these happen: a file is added,
renamed, or deleted; a command or flag changes; a dependency or environment changes; a convention or
unit changes; an output schema or filename changes; a CI trigger or job changes; a pitfall is
discovered; validation results change.  Before reporting, re-read the guide diff — a commit that
changes behaviour without touching the guide is incomplete.

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

## expl3 source style

Applies to any `dtx` written in `expl3` under `%<@@=…>`; a project guide points here rather than
repeating it.

- **Private names come from `@@`.**  The `dtx` sets `%<@@=Module>` once, before the first
  implementation line, and writes `\l_@@_…`, `\g_@@_…`, `\c_@@_…`, `\@@_…`; DocStrip
  expands the leading `@@` to `__Module`, and `l3doc` prints the same expansion when an object is
  documented in the same form.  Never write `@@` inside a Lua block or a Lua string: DocStrip
  rewrites it there too, and the Lua side would no longer match the TeX register it looks up.
  A name that Lua must see crosses with `\cs_to_str:N`, not as a literal.
- **Prefer the interface to the primitive.**  `\hbox:n`, `\hbox_to_wd:nn`, `\box_move_up:nn` and
  `\box_move_down:nn`, `\dim_set:Nn \tex_hsize:D`, `\int_use:N \allocationnumber` (not
  `\the\allocationnumber`), and `\c_zero_dim`/`\c_zero_int` for `\z@`.  Where no interface exists,
  use the `\tex_…:D` alias (`\tex_leaders:D`, `\tex_vrule:D`, `\tex_par:D`, `\tex_noindent:D`),
  not the bare primitive.  A module that patches a LaTeX2e package (a `listings` hook, for
  instance) stays LaTeX2e, and its `\@…`, `\def` and `\newif` are left alone.
- **Hooks go through `\hook_gput_code:nnn`.**  `\hook_gput_code:nnn { hook } { Package } { code }`,
  labelled with the package name so the chunk is deterministic; `.` resolves to the module only at
  load time, where the current file still is the module.  `\AtBeginDocument` is exactly
  `\hook_gput_code:nnn { begindocument } { … }`; `begindocument` runs after the `aux` is read but
  still during initialisation, `begindocument/end` at the start of the body.
- **Alignment.**  One space between arguments.  A multi-line argument list opens with its brace on
  its own line, one entry per line, padded *inside* the group so the closing braces line up:
  `{ CJK         }`, not `{ CJK }        `.  A run of two or more similar lines aligns the column
  that repeats: the function for a `\tl_new:N`/`\tl_set:Nn` pair, the variable for a `\dim_set:Nn`
  run, and the key, the property and the `=` in `\keys_define:nn`.  In a key block the property
  column is shared by the whole block while the keys are aligned per option family; a family whose
  padding would push a line past 79 columns stays unaligned.
- **Slashes carry spaces.**  `shipout / before`, `cmd / selectfont / after`, `LuaCJK / math`: the
  space is catcode 9 under `\ExplSyntaxOn`, so the stored name is `shipout/before` while the source
  reads as words.  Outside expl3, in a LaTeX2e file or a test, the name is written without spaces.
- **One `\GetIdInfo`.**  Every file derived from one `dtx` takes its information from a single block
  in a `%<*a|b|c>` guard: `\NeedsTeXFormat`, `\RequirePackage { expl3 }`, the `$Id$` line, then one
  description line per file and its own `\ProvidesExplPackage` or `\ProvidesExplFile`.  A LaTeX2e
  module keeps `\ProvidesPackage` and repeats the date, version and description in its optional
  argument.  `l3build tag` rewrites the single `$Id$`, so a second copy silently goes stale.
- **No compatibility packages.**  A format floor of 2020-10 or later puts `\NewDocumentCommand` and
  its siblings in the kernel (`xparse`), and 2022-06 puts `\ProcessKeyOptions` there (`l3keys2e`);
  load neither.
- **Lua goes through the public bridge.** `\lua_now:n`/`\lua_now:e` runs a chunk,
  `\lua_escape:n`/`\lua_escape:e` escapes a value for it, and `\lua_load_module:n` runs
  `require`. Never reach for `\directlua`, never hand-build a quoted `"…"` around a value that
  comes from TeX, and never find and load a file with `kpse.findfile` plus `dofile`: the first
  skips the escaping, and the second ignores `LUAINPUTS`, so it works locally and fails in a
  documentation build. A large body belongs in a `.lua` module named by
  `\lua_load_module:n { Module }`; a long `\lua_now:e` argument is unreadable and is re-parsed at
  every call.
- **A drawing is a box with a stroke around the path.** `l3draw` sizes its box by the bounding box
  of the stroked path, one stroke width wider than the path, and it shifts the drawing so that the
  bottom of that box sits on the baseline, which lifts a path that goes below the baseline. To tile
  a pattern with `\leaders`, give the box exactly one period (`\hbox to <period>`) and absorb the
  excess with `\hss` on both sides, and set the scratch box's height and depth to zero after
  building it, so that a decoration never changes the leading of the line it sits on.

## l3doc source style

- `\begin{macrocode}` and `\end{macrocode}` are written with `%` and **exactly four spaces**.
  `l3doc` reads the body between those two lines with a scan quark, so any other indentation
  leaves the following `\begin{macro}` inside the verbatim region, where it is printed in the
  manual instead of being executed.
- Every other documentation line uses `%` and **one space**, with no nesting indentation:
  `\begin{macro}`, `\begin{variable}`, their `\end{...}`, the description text, and ordinary
  prose all start in the same column.
- Mark internal objects with `[int]` (`\begin{macro}[int]{...}`, `\begin{variable}[int]{...}`);
  `[internal]` is accepted but the short form is the house style.  A `variable` whose name is a
  Lua identifier (dots and underscores) *needs* `[int]`: without it `l3doc` emits a reference to
  a label it never defines.
- Keep one blank `%` line between two consecutive entries.
- Wrap every function and variable in its own `macro` or `variable`, and nest a helper inside the
  object that calls it: a `\foo` that calls `\@@_foo:` is documented with the inner `macro` inside
  the outer one, so the printed structure mirrors the call graph. Several names that share one
  explanation go to one environment as a comma list (`\begin{macro}{\a, \b}`); a Lua function is
  named by its Lua name (`\begin{macro}{Module.pass}`), while a table or a constant is a
  `variable`. A missing `\end{macro}` swallows the rest of the run and the build dies far from the
  cause, so count the openings and the closings when that happens.
- Name an engine with the `hologo` macros: `\LuaTeX`, `\LuaLaTeX`, `\XeTeX`, `\pdfTeX`. `l3doc`
  provides `\LuaTeX` and `\XeTeX` but not `\LuaLaTeX` or `\XeLaTeX`, so a manual that needs them
  adds `\providecommand*\LuaLaTeX{\hologo{LuaLaTeX}}` and its sibling in the driver.
- A section does not open with a lone subsection: when a section has a single subdivision, drop
  the subheading and let the section carry the content.
- Narration goes between `\end{macrocode}` and the next `\begin{macrocode}`, never into comments
  inside the code: a comment in the verbatim body is printed as part of the listing.
- A name that is fixed is written as a brace group, not as a metavariable: `\tn{begin}\{document\}`,
  not `\tn{begin}\marg{document}`, which prints `{⟨document⟩}`.  Neither `\marg*` nor `\oarg*`
  exists in the current `l3doc`, so the star is not a way out.
- `\file{...}` takes plain text only; a control sequence inside it is typeset literally.  Write
  `\file{luacjk-}\meta{name}\file{.cfg}`, and keep each piece in its own `\file`.
- In a `quote` environment every line except the last ends with `\\`; without it the lines run
  together into one paragraph.
- The manual describes the package, not the repository: no test files, CI, build commands, or
  script names in the documentation part, and the reasoning behind an interface belongs in the
  implementation section rather than beside the instruction for the user.
- A command without arguments needs no `syntax` block, but a command with a visible effect wants a
  demo; the demos are `codemo` pairs of code and result, one per effect or per option group.
- In a demo, parallel commands align their arguments in one column (`\CJKunderline   {…}` under
  `\CJKunderdblline{…}`), a command is not split from the text it affects, and font options come
  before the font name (`\setCJKmainfont[Kana = Kai]{Song}`), broken between the two arguments.
- Aligning the continuation of a `syntax` line uses `\` plus spaces, never `\phantom`.
- In LaTeX and Markdown prose, start a sentence on a new source line and break a long sentence at
  a comma, semicolon, or colon rather than mid-phrase.  A paragraph keeps its line count and its
  width; only the break points move, which makes the diff readable without changing the output.
  Code, `syntax` and `quote` blocks, tables, and braced variable-name lists keep their layout.
- Prose uses one space after a sentence-ending full stop, question mark, or exclamation mark, and
  no trailing space at the end of a line: `\TeX` collapses runs of spaces, and the line-breaking
  algorithm decides where a line ends, so neither serves as a typographic control.  Alignment
  padding inside code, `syntax` blocks, docstrip tables, and licence boxes is the exception.
- An option name in running text is `\keys{name}`, not `\texttt{name}`, even outside a
  `keyval` environment.  Inside one it appends `=` (docext's item format), so a reference to
  another key in a `keyval` description stays `\texttt`.
- An option list is a `keyval` environment, never a `function`: a key is not a control sequence,
  and `function` also files the entry in the index of commands. Write each item as
  `\item[\keys{name}]\val{…}`, and give the metavariable with the docext helper that shows the
  default: `\val{\TTF}` for a switch that starts on, `\val{\TFF}` for one that starts off, and
  `\val{\TF}` when the initial value is stated in the text instead. A glue, a style name, or a
  dimension is written plainly (`\val{glue}`). `function` stays for real control sequences.
- A manual whose `codemo` demos execute is typeset by the engine the package targets, with the
  demos running in the same pass; a demo that only shows code does not need that engine.
- Never redirect the terminal output of a TeX run to `\jobname.out`: hyperref reads that file as
  its bookmarks, so the build fails on its own log with errors that point nowhere near the cause.

### Manuals and DocStrip

A `dtx` is both the source and the manual. What only the generated files need stays out of the
documentation, and what only the manual needs stays out of the derived files.

Prove a documentation-only change inert instead of arguing it: unpack the previous commit in a
worktree, `cmp` `build/unpacked/*` against the current build, and compare the text of the two PDFs
(`mutool draw -F txt`).  Both being identical is the evidence that only prose moved.

- **The driver lives in the `dtx`.** A `%<*driver>` block holds the `\documentclass` and
  `\DocInput{\jobname.dtx}`; a separate driver file is one more thing to keep in step. `l3build`
  then typesets the `dtx` itself (`typesetfiles = {"Name.dtx"}`). Prefer
  `typesetexe = "latexmk -pdflua"` with `typesetruns = 1` to repeated `lualatex` runs: `latexmk`
  knows when a rerun or an index run is still needed. Because `l3build` otherwise appends
  `\input <file>` to the command, and `latexmk` reads that as a file name, this needs a `tex()`
  override that passes the file and the `l3doc` index style. A package that loads Lua through
  `\lua_load_module:n` also needs `LUAINPUTS` in that environment, pointing at the unpacked tree;
  without it `require` sees only the system tree and the doc build fails on a module it just
  generated.
- **Metadata stays outside the documentation.** `\GetIdInfo` and the `\Provides…` lines sit in the
  hidden part of the file, inside an `internal`-guarded `\iffalse`/`\fi` pair, not in a
  `macrocode` block: everything in `macrocode` is typeset, so the manual would print the metadata
  and the branch markers with it.
- **One guard pair per region.** Open `%<*tag>` once at the start of a region and close it once at
  the end. A pair around every `macro` leaves the marker lines in the manual, because the
  documentation between them is stripped as guarded material rather than as prose.
- **Share one metadata block.** Several files derived from one `dtx` take `\NeedsTeXFormat`, the
  `expl3` requirement, the one `$Id$` line and the `\Provides…` lines from a single `%<*a|b|c>`
  guard. Do not use the complement of a guard that other outputs also match: `%<*!driver>` is true
  for every non-driver output, so it leaks into the `.lua` files as well.
- **The `$Id$` line must be matchable.** `update_tag` rewrites the single `\GetIdInfo` line, so its
  pattern may not assume a guard prefix on that line; a pattern such as `%<[a-z]+>\GetIdInfo`
  silently matches nothing once the metadata shares a block.
- **A line is copied or dropped, not interpreted.**  DocStrip drops a line that starts with `%`
  and copies every other line verbatim, a blank one included.  A stray blank line in a guarded
  region therefore appears in every generated file; when a generated file gains a line nobody
  wrote, look for a bare newline in the `dtx`.
- **A non-TeX preamble sets `\MetaPrefix` twice.**  `\declarepreamble` prefixes each line with
  `\MetaPrefix`, so a Lua or Python preamble needs `\def\MetaPrefix{--}` (or `#`) while the macro
  is declared.  The reference lines at the top of the generated file are expanded when the file is
  *opened*, not at declaration, so `\MetaPrefix` has to hold the same value again around the
  `\generate` that writes it.  Restore the TeX default afterwards.
- **The README is generated too.** Keep it in a `%<*readme>` block, extract it with
  `\nopreamble\nopostamble` into `README.md`, and copy it back to the repository root from
  `docinit_hook`: the root copy is what the forge shows, and a second hand-maintained copy drifts.

## Tooling and upkeep

- **Where to record things.**  General conventions go in the global repository
  (`~/.config/opencode`: `AGENTS.md`, `skills/`, `scripts/`, `opencode.json`), which syncs to
  GitHub.  Project-specific rules go in that project's `AGENTS.md` and `.opencode/skills/`.
  Machine secrets and addresses (`proxy`, `service.json`, `cli.json`, the shell rc) stay untracked,
  and nothing tracked may contain them.
- **Keep the global rules current.**  Whenever a session in any repository establishes a general
  convention — coding style, commit/PR rule, LaTeX style, tool workflow, pitfall — record it in the
  global repository in the same task, then commit and push.  Check every time.
- **opencode (v2).**  `opencode.json` (global, plus a workspace one where a project needs its
  own guards) is kept in strict v2 form.
  `permissions` is an ordered array of `{action, resource, effect}` rules; the **last** matching
  rule wins, and project rules come after global ones.  The machine-wide guards live in the global
  config — blanket `read`/`edit`/`shell` allows first, then `deny` on `.git/**` and
  `**/.git/**` (read/edit/`rm`; use git and `gh` instead of touching the store) and on
  `**/__pycache__/**`.  A project's own `opencode.json` adds only its specific denies (e.g.
  `bibliography/`, `*_legacy/`) and must **not** repeat a blanket allow after them, which would
  cancel them.  v2 names the shell action `shell`, not `bash`.  `compaction` tunes context handling
  (`auto`, `keep.tokens`, `buffer`).
- The provider lives in the machine-global `~/.config/opencode/opencode.json` (native v2
  `providers` block, `package: "@opencode/ai/providers/openai-compatible"` since 2.2.x,
  `settings.baseURL`).  The CLI
  moved under `session` (`opencode session export|import|list|delete`).  Tool names follow v2:
  `shell` (not `bash`), `subagent` (not `task`), and `read`/`edit`/`write` take `path`.
- **Network access.**  Governed by the global `network-access` skill.  Two regimes: small calls
  (metadata, `gh api`, a few kB of JSON) go **direct** first; bulk transfers (`gh run download`
  artifacts, release assets, big clones, `pip download`) go **through the proxy** even when the
  direct route works, because the GitHub content network (`*.blob.core.windows.net`, where Actions
  artifacts redirect) is throttled to tens of kB/s directly.  The address lives in
  `~/.config/opencode/proxy` (mode 600); never write it into a tracked file.
- **Daily upkeep (`opencode-hpc-update`).**  Not a scheduled job: when a user message arrives,
  quietly consult `~/.config/opencode/scripts/update-due.sh`.  If it prints `DUE`, load the
  skill, refresh the config, and stamp the day with
  `~/.config/opencode/scripts/update-due.sh --mark`; otherwise carry on without mentioning it.
  Timing is Asia/Shanghai, at most once per calendar day (due from 17:00 on a day not yet checked,
  or immediately if a whole day was skipped); the last date is in
  `~/.config/opencode/.update-check`.
- **The model half is automatic; the OpenCode half is not.**  The `upkeep` plugin
  (`~/.config/opencode/plugins/upkeep/index.ts`) runs at prompt admission once a day: it reads
  `https://hpc-api.westlake.edu.cn/v1/models` with `WESTLAKE_API_KEY`, inserts chat models that the
  configuration lacks (skipping embeddings and rerankers, never removing an entry, copying the
  capability block of an existing model), writes `opencode.json` with the text-preserving insertion
  that keeps the hand layout, keeps `opencode.json.bak`, and stamps `.models-check`.  It does not
  stamp `.update-check`: installing an OpenCode version is not something a plugin may do, so that
  half still goes through the skill, announced as `<context key="upkeep">`.
- **Session upkeep (`session-hygiene`).**  Keep each session whole and branch into a new session
  rather than compacting; give every session a `type(things): …` title (rename any agent
  auto-title that does not conform).  Load the skill for the export → prune → import procedure
  and its pitfalls.  Never edit the session store by hand.
- **Never publish a file under another package's name.**  CTAN rejects a duplicate filename, and a
  copy that sits next to the original silently loses to it.  To take over another package's hook
  file, ship the logic under your own name and redirect through that package's own configuration
  entry point, then check the log of a real end-to-end compile for the file it actually resolved.
- **kpathsea resolves by name, not by intent.**  Within one tree it returns the smallest full
  path, and `\input` searches the current directory before any tree.  So `tex/latex/<mine>/x.def`
  never shadows `tex/latex/<theirs>/x.def` in the same tree, and "install it beside the other
  package" is the one arrangement that cannot work.  A shadowing layer belongs in the document
  directory or in a tree that precedes the main one, and the test must assert the resolved path
  rather than a marker string.
- **A generated config file is read at an arbitrary point.**  A file written at run time for
  another package to `\input` may be read with category codes and an `expl3` state that are not
  yours, so write plain LaTeX2e, avoid `%` as a comment character, and guard the engine check with
  `\@ifundefined`.  An `expl3`-syntax version fails with `Undefined control sequence` at the point
  of use, not while writing the file.

## Local and CI parity

CI builds the same environment from the repository's `environment.yaml` (same pinned interpreter,
channels, `requirements.txt`) and runs the same commands as locally.  When a dependency, the
interpreter pin/channels, a validation suite, or the conda interface changes, update both the
local setup and the CI workflow in the same change.  `environment.yaml` is the single source of
truth: the workflow must not hard-code its own interpreter version or channel list.

A TeX Live package list names the **bundle**, not the file: `l3draw.sty` comes from
`l3experimental`, `expl3.sty` from `l3kernel`.  The name a `\RequirePackage` takes is not the name
to install.  A dependency pulled in transitively may also have to be listed: `hyperref` no longer
brings `nameref` and `refcount` with it on every platform, and a test that loads it then dies with
an empty log.  When a job fails on a missing package, add the bundle that provides it.
