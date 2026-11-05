#!/usr/bin/env bash
# Are the history-rewrite rollback bundles still present?
#
#   backups-pending.sh [dir]   -> print "<n> bundle(s), <m> MB, in <dir>"
#                                 exit 0 when any *.bundle exists, 1 when none
#
# The bundles are the rollback for the 2026-11-05 history rewrite.  They live
# outside the repositories, in the workspace's admin/backups directory, and are
# deleted only after the user confirms the rewritten history is good.  The
# upkeep plugin calls this on the same cadence as the two due-checks, so the
# reminder disappears by itself once the files are gone.
set -u

dir="${1:-$HOME/GitHub/Dou_Group/admin/backups}"

shopt -s nullglob
files=("$dir"/*.bundle)
if [ "${#files[@]}" -eq 0 ]; then
  echo "nothing pending in $dir"
  exit 1
fi

total_kb=$(du -ck "${files[@]}" | tail -1 | cut -f1)
printf '%d bundle(s), %d MB, in %s\n' "${#files[@]}" "$((total_kb / 1024))" "$dir"
exit 0
