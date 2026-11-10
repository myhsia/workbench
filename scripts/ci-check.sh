#!/bin/sh
# Negative and edge-case checks for oathpass.  Needs no network and no secret:
# the seed below is the published RFC 6238 test key.
#
# Usage: sh scripts/ci-check.sh [path-to-binary]
set -eu

BIN=${1:-./oathpass}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

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

# expect <exit-code> <description> <config> <args...>
expect() {
    want=$1
    desc=$2
    conf=$3
    shift 3
    set +e
    out=$(OATHPASS_CONFIG="$conf" "$BIN" "$@" 2>&1)
    got=$?
    set -e
    if [ "$got" = "$want" ]; then
        pass=$((pass + 1))
        printf '  ok   %-38s exit=%s\n' "$desc" "$got"
    else
        fail=$((fail + 1))
        printf '  FAIL %-38s exit=%s want=%s\n%s\n' "$desc" "$got" "$want" "$out"
    fi
}

echo "oathpass CLI checks"
expect 0 "--selftest"                    /nonexistent --selftest
expect 0 "--help"                        /nonexistent --help
expect 0 "otp at a fixed second"         "$TMP/valid.json" otp --at 59
expect 0 "target"                        "$TMP/valid.json" target
expect 1 "placeholders are rejected"     "$TMP/placeholder.json" check
expect 1 "invalid base32 is rejected"    "$TMP/badseed.json" check
expect 1 "missing config file"           "$TMP/absent.json" check
expect 1 "--node out of range"           "$TMP/valid.json" --node 4 check
expect 1 "--node with --port"            "$TMP/valid.json" --node 1 --port 22 check
expect 3 "nothing listening -> exit 3"   "$TMP/valid.json" check

printf '%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
