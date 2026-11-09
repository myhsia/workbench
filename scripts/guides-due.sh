#!/usr/bin/env bash
# Guide due-check: has code moved on since AGENTS.md / the skill last changed?
#
#   guides-due.sh [--committed|--staged] [repo]
#                          -> print STALE / OK / MISSING
#                             exit 0 (stale: review the guides), 1 (ok), 2 (missing)
#
# The check looks at the working tree first (uncommitted code changes count, so
# it works as a pre-commit gate) and then at the history.  "Guides" means
# AGENTS.md plus the skill directory: `.opencode` in a project, `skills` in the
# global config repository, which holds the skills at its top level.
#
# `--committed` ignores the working tree and judges the history alone.  Session
# start uses it: a repository being edited is dirty by design, and only the
# commits say whether the guides fell behind.
#
# `--staged` judges only the index, which is what the commit-msg hook needs: a
# code/config/CI change staged without a guide is STALE, docs-only is OK.
#
# When the target is not a git repository (a workspace root such as the oqs
# checkout, which holds sibling repositories), every immediate child directory
# that is a git repository is checked instead: one line per repository, named
# after the child, with any detail lines below it.  The exit code is then 0 if
# any child is STALE or MISSING, and 1 if they are all OK.  A path that is not a
# repository and holds no repositories at all prints a NOTE and exits 1.
set -u

committed=no
staged=no
repo="."
for arg in "$@"; do
  case "$arg" in
    --committed) committed=yes ;;
    --staged)    staged=yes ;;
    *)           repo="$arg" ;;
  esac
done

# Check one git repository and print its verdict.
# Returns 0 (stale), 1 (ok), 2 (missing).
check_repo() {
  local repo="$1"
  local skilldir="" d missing=""

  for d in .opencode/skills skills; do
    if [ -f "$repo/$d/SKILL.md" ] || \
       [ -n "$(ls -d "$repo/$d"/*/SKILL.md 2>/dev/null)" ]; then
      skilldir="$d"
      break
    fi
  done

  [ -f "$repo/AGENTS.md" ] || missing="$missing AGENTS.md"
  [ -n "$skilldir" ] || missing="$missing <skill>/SKILL.md"
  if [ -n "$missing" ]; then
    echo "MISSING:$missing"
    return 2
  fi

  local guides=(AGENTS.md "$skilldir")

  # Prose trees are not code for this gate.  A manuscript (`context/`) cannot
  # change a command, a flag, a dependency, a schema or a CI trigger, so commit
  # order says nothing about whether the guides owe an update; that judgement
  # stays with the author (the `Guides-Reviewed:` trailer).  Counting it would
  # make every `docs(context):` commit report STALE for ever.
  local prose_excl=()
  local p
  for p in context; do
    [ -d "$repo/$p" ] && prose_excl+=(":(exclude)$p")
  done

  # `set -u` plus bash 3.2 (the macOS default) cannot expand an empty array, so
  # the optional exclusions use the "expand only if set" idiom.
  local code_excl=(':(exclude)AGENTS.md' ":(exclude)$skilldir" ${prose_excl[@]+"${prose_excl[@]}"})

  # Index-only mode for the commit-msg hook.
  if [ "$staged" = yes ]; then
    local staged_files code_files
    staged_files="$(git -C "$repo" diff --cached --name-only -- . "${code_excl[@]}")"
    code_files="$(printf '%s\n' "$staged_files" \
      | grep -vE '\.(tex|md|bib|pdf|png|jpe?g|svg|eps|gif)$' | sed '/^$/d')"
    if [ -n "$code_files" ]; then
      echo "STALE: staged changes outside the guides"
      printf '%s\n' "$code_files" | sed 's/^/  /' | head -10
      return 0
    fi
    echo "OK: staged changes are guides or prose"
    return 1
  fi

  # Uncommitted work outside the guides: the answer is stale whatever the
  # history says.  `--committed` skips this, because an edited repository is
  # dirty by design.
  if [ "$committed" = no ]; then
    local pending
    pending="$(git -C "$repo" status --porcelain -- . "${code_excl[@]}")"
    if [ -n "$pending" ]; then
      echo "STALE: uncommitted changes outside the guides"
      printf '%s\n' "$pending" | sed 's/^/  /' | head -10
      return 0
    fi
  fi

  local guide_sha code_sha ahead
  guide_sha="$(git -C "$repo" log -1 --format=%H -- "${guides[@]}")"
  code_sha="$(git -C "$repo" log -1 --format=%H -- . "${code_excl[@]}")"

  [ -z "$code_sha" ] && { echo "OK: no code commits yet"; return 1; }
  [ -z "$guide_sha" ] && { echo "STALE: the guides have never changed"; return 0; }

  # Order, not timestamps: several commits can share one second.
  ahead="$(git -C "$repo" rev-list --count "$guide_sha..HEAD" -- . "${code_excl[@]}")"
  if [ "${ahead:-0}" -gt 0 ]; then
    echo "STALE: $ahead code commit(s) after the last guide change"
    echo "  code:  $(git -C "$repo" log -1 --format='%h %cs %s' -- . "${code_excl[@]}")"
    echo "  guide: $(git -C "$repo" log -1 --format='%h %cs %s' -- "${guides[@]}")"
    return 0
  fi

  echo "OK: the guides are as new as the code"
  return 1
}

# Single repository: the original behaviour, unchanged.
if git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
  check_repo "$repo"
  exit $?
fi

if [ ! -d "$repo" ]; then
  echo "MISSING: $repo is not a git repository" >&2
  exit 2
fi

# Workspace root: check every immediate child that is a git repository.
status=1
found=0
for child in "$repo"/*/; do
  child="${child%/}"
  git -C "$child" rev-parse --git-dir >/dev/null 2>&1 || continue
  found=1
  out="$(check_repo "$child")"
  rc=$?
  printf '%s\n' "$out" | sed "1s|^|$(basename "$child"): |"
  [ "$rc" -eq 1 ] || status=0
done

if [ "$found" -eq 0 ]; then
  echo "NOTE: $repo is not a repository and holds no repositories to check" >&2
  exit 1
fi

exit "$status"
