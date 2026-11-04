# <repository>

<!-- One paragraph: what this is, what it produces, and which sibling repositories / shared pieces
     it depends on. Name the owner's other checkouts explicitly if it mirrors files from one. -->

## Shared rules

Repo etiquette, Python style, the git/PR workflow, LaTeX style, `expl3` source style, manuals and
DocStrip, tooling and upkeep are **machine-global**: see the `repo-rules` skill at
`~/.config/opencode/skills/repo-rules/SKILL.md`.  Do not copy them here;
state only the exceptions this repository makes.

## Environment

<!-- The toolchain, the directory all commands run from, the entry points.  A Python repository
     names its conda environment, a TeX repository its TeX Live year and engine, and a mixed one
     both; say which scripts are bash and whether an interpreter is available.
     Example:
- Conda env `xyz`; run everything from `source/` (paths such as `./config` are relative to it).
- Entry points: `python run.py`, `python plot.py`. -->

## Project layout

<!-- Every tracked file and package, one line each, saying what lives where and which part is
     generated or gitignored.  This is the section that saves a new session the most time.  Where a
     check script exists, let it compare this table with `git ls-files` rather than trusting it. -->

## Conventions and pitfalls

<!-- The non-obvious rules: naming, units, ordering, precision, schema of outputs, numerical traps,
     anything a careful reader of the code would still get wrong.  Prefer bullets with the reason. -->

## Workflows

<!-- Copy-pasteable commands in dependency order, including the long or expensive ones and their
     typical runtimes.  Mark which steps need the network and which are optional. -->

```bash
# ...
```

## Validation

<!-- How correctness is checked: regression tests, reference values, expected agreement, the command
     to run them, and what "passing" means numerically.  If nothing exists, say so and propose one. -->

## CI

<!-- Workflows and their triggers, the matrix, artifact names, how to retrieve results, and what runs
     locally versus on CI (and any local/CI parity caveat). -->

## Git style

See the global `repo-rules` skill (`type(scope): summary`; commit only when asked; never commit
secrets, addresses, or generated output).  <!-- Add repository-specific commit scopes if any. -->

<!-- Optional for scientific repositories:

## Validity (measured, not assumed)

State each parameter and the measurement that justified it (convergence study, benchmark against a
reference method, error metric and threshold).  Distinguish what was measured from what was assumed.
-->
