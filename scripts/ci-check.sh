#!/bin/sh
# Negative and edge-case checks for oathpass.  Needs no network and no secret:
# the seed below is the published RFC 6238 test key.
#
# The tool reads $HOME/.config/oathpass/config.json and nothing else, so this
# script points HOME at a scratch tree -- it can never touch a real config.
#
# Usage: sh scripts/ci-check.sh [path-to-binary]
set -eu

BIN=${1:-./oathpass}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

HOME="$TMP/home"
export HOME
CONFIG="$HOME/.config/oathpass/config.json"
mkdir -p "$HOME/.config/oathpass"

SEED="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNA="

cat >"$TMP/valid.json" <<EOF
{"oathpass": {"host": "127.0.0.1", "ports": ["1", "2", "3"], "user": "ci",
  "otp": {"uri": "otpauth://totp/ci?secret=$SEED&algorithm=SHA512&digits=8&period=30"}}}
EOF

cat >"$TMP/placeholder.json" <<'EOF'
{"oathpass": {"host": "<IP address>", "ports": ["<port 1>"], "user": "<username>",
  "otp": {"uri": "<otpauth://totp/...?secret=...>"}}}
EOF

cat >"$TMP/badseed.json" <<'EOF'
{"oathpass": {"host": "127.0.0.1", "ports": ["1"], "user": "ci",
  "otp": {"secret": "not!base32!"}}}
EOF

pass=0
fail=0

ok() { pass=$((pass + 1)); printf '  ok   %-38s %s\n' "$1" "${2:-}"; }
bad() { fail=$((fail + 1)); printf '  FAIL %-38s %s\n' "$1" "${2:-}"; }

# install <fixture|missing> -- place (or remove) the config for the next call
use_config() {
    rm -f "$CONFIG"
    [ "$1" = missing ] || cp "$1" "$CONFIG"
}

# expect <exit-code> <description> <fixture> <args...>
expect() {
    want=$1
    desc=$2
    fixture=$3
    shift 3
    use_config "$fixture"
    set +e
    out=$("$BIN" "$@" 2>&1)
    got=$?
    set -e
    if [ "$got" = "$want" ]; then
        ok "$desc" "exit=$got"
    else
        bad "$desc" "exit=$got want=$want"
        printf '%s\n' "$out" | sed 's/^/       /'
    fi
}

echo "oathpass CLI checks"
expect 0 "--selftest"                  missing --selftest
expect 0 "--help"                      missing --help
expect 0 "otp at a fixed second"       "$TMP/valid.json" otp --at 59
expect 0 "target"                      "$TMP/valid.json" target
expect 1 "placeholders are rejected"   "$TMP/placeholder.json" check
expect 1 "invalid base32 is rejected"  "$TMP/badseed.json" check
expect 1 "missing config file"         missing check
expect 1 "--node out of range"         "$TMP/valid.json" --node 4 check
expect 1 "--node with --port"          "$TMP/valid.json" --node 1 --port 22 check
expect 3 "nothing listening -> exit 3" "$TMP/valid.json" check
expect 3 "run with no network"         "$TMP/valid.json" run ls
expect 3 "status with no network"      "$TMP/valid.json" status
expect 0 "close with nothing open"     "$TMP/valid.json" close

# The guard must refuse before any connection is attempted, so these are safe
# to test offline and must not reach the network.
expect 1 "run refuses .."              "$TMP/valid.json" run cat ../../etc/passwd
expect 1 "run refuses an absolute path" "$TMP/valid.json" run cat /etc/passwd
expect 1 "run refuses ~"               "$TMP/valid.json" run ls "~"
expect 1 "run refuses shell syntax"    "$TMP/valid.json" run cat "x; id"
expect 1 "run refuses an unlisted cmd" "$TMP/valid.json" run rm -rf .
expect 1 "run refuses find -exec"      "$TMP/valid.json" run find . -name x -exec ls {} +

# The help text must name the tool and advertise the selftest.
use_config missing
help=$("$BIN" --help 2>&1)
if printf '%s\n' "$help" | grep -q '^usage: oathpass'; then
    ok "--help names oathpass"
else
    bad "--help names oathpass" "still advertises another command name"
fi
if printf '%s\n' "$help" | grep -q -- '--selftest'; then
    ok "--help advertises --selftest"
else
    bad "--help advertises --selftest"
fi

# Guard against the pre-rename command name creeping back into the sources.
# The hyphen guards let `opencode-hpc-update` through; this script is excluded
# because it necessarily contains the pattern it searches for.
if out=$(grep -nE '(^|[^A-Za-z-])hpc([^A-Za-z-]|$)' \
    "$ROOT/scripts/oathpass.c" "$ROOT/Makefile" "$ROOT/README.md" 2>/dev/null); then
    bad "no stale command name in the sources" ""
    printf '%s\n' "$out" | sed 's/^/       /'
else
    ok "no stale command name in the sources"
fi

printf '%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
