#!/usr/bin/env bash
# Daily due-check for the `opencode-hpc-update` skill.
#
#   update-due.sh          -> print DUE / NOT DUE and exit 0 (due) or 1 (not due)
#   update-due.sh --mark   -> record today (Asia/Shanghai) as the last check day
#
# Timing is Asia/Shanghai (GMT+0800).  The check is due whenever today's calendar
# day carries no stamp: there is no time-of-day threshold, so the day rolls over
# at 00:00 and a skipped day is due immediately on the next first message.
set -u
export TZ=Asia/Shanghai

oc_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # .../.opencode
marker="$oc_dir/.update-check"
today="$(date +%F)"

if [ "${1:-}" = "--mark" ]; then
  printf '%s\n' "$today" > "$marker"
  echo "marked $today"
  exit 0
fi

last=""
[ -f "$marker" ] && last="$(tr -d '[:space:]' < "$marker")"

[ -z "$last" ] && { echo "DUE: no previous check"; exit 0; }
[ "$last" = "$today" ] && { echo "NOT DUE: already checked $today"; exit 1; }

echo "DUE: last $last, now $today"
exit 0
