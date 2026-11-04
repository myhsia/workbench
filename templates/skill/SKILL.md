---
name: <repo>-<topic>
description: Use when working on <what the code does> — <the questions this skill answers>.
license: MIT
compatibility: opencode
metadata:
  audience: maintainers
  scope: project
---

# <Topic>

<!-- Two or three sentences: what this repository computes, for whom, and what a session gets from
     this skill that it would otherwise have to reverse-engineer from the code. -->

## Repository rules

Repo etiquette, Python style, the git/PR workflow, LaTeX style, tooling and upkeep are **machine-global**:
see the `repo-rules` skill.  This skill carries only the project's science and engineering.

## Background

<!-- The model/architecture, with the equations or data structures a newcomer needs to reason about
     the code: Hamiltonian or schema, parameters and their meaning, approximations made and why.
     Enough that a session can judge whether a proposed change is physically correct. -->

## Current work

<!-- What the code does today: the solver/algorithm, its variants, what each entry point produces,
     and the state of the art it implements.  Update this whenever behaviour changes. -->

## Conventions

<!-- Numeric conventions the code relies on: units, factors (and any rescaling the solver undoes),
     sign/branch conventions, name-to-symbol mapping between the paper and the config files,
     output file naming.  These are the details that silently produce wrong results. -->

## Workflows and validation

<!-- How to run it, and how to know it worked: the command, the expected output, the regression test
     or benchmark, and the tolerance. -->

```bash
# ...
```
