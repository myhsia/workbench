#!/usr/bin/env bash
# Daily due-check for the `opencode-hpc-update` skill.
#
#   update-due.sh          -> print DUE / NOT DUE and exit 0 (due) or 1 (not due)
#   update-due.sh --mark   -> record today (Asia/Shanghai) as the last check day
#
# Timing is Asia/Shanghai (GMT+0800). At most once per calendar day: normally due
# from 17:00 onward on a day not yet checked; if a whole day was skipped (no check
# that day), it becomes due immediately on the next day's first message, any hour.
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

hour="$(date +%H)"
last=""
[ -f "$marker" ] && last="$(tr -d '[:space:]' < "$marker")"

[ -z "$last" ] && { echo "DUE: no previous check"; exit 0; }
[ "$last" = "$today" ] && { echo "NOT DUE: already checked $today"; exit 1; }

to_epoch() { date -j -f "%F" "$1" "+%s" 2>/dev/null || date -d "$1" "+%s"; }
last_s="$(to_epoch "$last")" || last_s=""
today_s="$(to_epoch "$today")" || today_s=""
{ [ -z "$last_s" ] || [ -z "$today_s" ]; } && { echo "DUE: unreadable marker ($last)"; exit 0; }

diff=$(( (today_s - last_s) / 86400 ))
if [ "$diff" -gt 1 ]; then
  echo "DUE: day skipped (last $last -> $today)"
  exit 0
fi
if [ "$((10#$hour))" -ge 17 ]; then
  echo "DUE: after 17:00 (last $last, now $(date +%H:%M))"
  exit 0
fi
echo "NOT DUE: last $last, now $today $(date +%H:%M)"
exit 1
