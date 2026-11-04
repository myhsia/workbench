#!/usr/bin/env bash
# Guide due-check: has code moved on since AGENTS.md / the skill last changed?
#
#   guides-due.sh [--committed] [repo]
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
set -u

committed=no
repo="."
for arg in "$@"; do
  case "$arg" in
    --committed) committed=yes ;;
    *)           repo="$arg" ;;
  esac
done
if ! git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
  echo "MISSING: $repo is not a git repository" >&2
  exit 2
fi

skilldir=""
for d in .opencode/skills skills; do
  if [ -f "$repo/$d/SKILL.md" ] || \
     [ -n "$(ls -d "$repo/$d"/*/SKILL.md 2>/dev/null)" ]; then
    skilldir="$d"
    break
  fi
done

missing=""
[ -f "$repo/AGENTS.md" ] || missing="$missing AGENTS.md"
[ -n "$skilldir" ] || missing="$missing <skill>/SKILL.md"
if [ -n "$missing" ]; then
  echo "MISSING:$missing"
  exit 2
fi

guides=(AGENTS.md "$skilldir")
code_excl=(':(exclude)AGENTS.md' ":(exclude)$skilldir")

# Uncommitted work outside the guides: the answer is stale whatever the history
# says.  `--committed` skips this, because an edited repository is dirty by
# design.
if [ "$committed" = no ]; then
  pending="$(git -C "$repo" status --porcelain -- . "${code_excl[@]}")"
  if [ -n "$pending" ]; then
    echo "STALE: uncommitted changes outside the guides"
    printf '%s\n' "$pending" | sed 's/^/  /' | head -10
    exit 0
  fi
fi

guide_sha="$(git -C "$repo" log -1 --format=%H -- "${guides[@]}")"
code_sha="$(git -C "$repo" log -1 --format=%H -- . "${code_excl[@]}")"

[ -z "$code_sha" ] && { echo "OK: no code commits yet"; exit 1; }
[ -z "$guide_sha" ] && { echo "STALE: the guides have never changed"; exit 0; }

# Order, not timestamps: several commits can share one second.
ahead="$(git -C "$repo" rev-list --count "$guide_sha..HEAD" -- . "${code_excl[@]}")"
if [ "${ahead:-0}" -gt 0 ]; then
  echo "STALE: $ahead code commit(s) after the last guide change"
  echo "  code:  $(git -C "$repo" log -1 --format='%h %cs %s' -- . "${code_excl[@]}")"
  echo "  guide: $(git -C "$repo" log -1 --format='%h %cs %s' -- "${guides[@]}")"
  exit 0
fi

echo "OK: the guides are as new as the code"
exit 1
