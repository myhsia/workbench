#!/usr/bin/env bash
# Keep this configuration repository level with origin/main.
#
# The config lives in `myhsia/workbench` so that a second machine can start from
# the same guides, plugins and scripts.  This runs once a calendar day from the
# `upkeep` plugin: fetch, then fast-forward only when the tree is clean and the
# branch is strictly behind.  It never rewrites a local commit and never resets,
# so divergence stays a human merge.
#
# Exit codes follow the other checks:
#   0  nothing to report (up to date, or this machine is ahead)
#   1  a line to report (synced, dirty, diverged, refused)
#   2  cannot run here (no repository, or origin unreachable)
#
# Usage: config-sync.sh [directory]      (default: ~/.config/opencode)

set -u

dir=${1:-$HOME/.config/opencode}
cd "$dir" 2>/dev/null || exit 2
git rev-parse --git-dir >/dev/null 2>&1 || exit 2

export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=/bin/true

if ! timeout 15 git fetch --prune --quiet origin >/dev/null 2>&1; then
  echo "config: cannot reach origin"
  exit 2
fi

counts=$(git rev-list --left-right --count origin/main...HEAD 2>/dev/null) || exit 2
behind=${counts%%[[:space:]]*}
ahead=${counts##*[[:space:]]}

[ "$behind" -eq 0 ] && [ "$ahead" -eq 0 ] && exit 0
[ "$ahead" -gt 0 ] && [ "$behind" -eq 0 ] && exit 0          # this machine is the source

if [ "$ahead" -gt 0 ]; then
  echo "config: diverged, ahead $ahead behind $behind - merge by hand"
  exit 1
fi

# Strictly behind.  Untracked files do not block a fast-forward, tracked edits do.
dirty=$(git status --porcelain --untracked-files=no)
if [ -n "$dirty" ]; then
  echo "config: behind $behind, tree dirty - not fast-forwarded"
  exit 1
fi

if git merge --ff-only --quiet origin/main >/dev/null 2>&1; then
  echo "config: synced $behind commit(s) from origin/main"
  exit 1
fi

echo "config: behind $behind, fast-forward refused"
exit 1
