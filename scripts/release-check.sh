#!/usr/bin/env bash
# Keep the released tools on this Mac current, once a calendar day.
#
#   release-check.sh            -> the same as --apply (what the upkeep plugin runs)
#   release-check.sh --apply    -> install the latest release if the installed
#                                  binary is not exactly that release
#   release-check.sh --check    -> report only; 0 current, 1 action needed,
#                                  2 the release could not be read
#   release-check.sh --status   -> print the recorded state and the installed hash
#
# "Current" means more than a matching version string: the installed bytes must
# be the ones this script recorded after downloading the release.  A locally
# built binary with the same version is therefore replaced, which is the point --
# this Mac runs the GitHub build, never `make install`.
#
# State lives in ~/.config/opencode/.release-state (untracked):
#   {"checked": "YYYY-MM-DD", "tag": "v0.4.3", "sha256": "...", "error": null}
set -u
export TZ=Asia/Shanghai

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
state="$root/.release-state"
proxy_file="$root/proxy"
BIN="${RELEASE_BIN:-$HOME/.local/bin/oathpass}"
REPO="${RELEASE_REPO:-myhsia/oathpass}"
INSTALLER="${RELEASE_INSTALLER:-https://raw.githubusercontent.com/${REPO}/main/install.sh}"
today="$(date +%F)"

mode="${1:---apply}"
case "$mode" in
  --check | --apply | --status) ;;
  *)
    echo "usage: release-check.sh [--check|--apply|--status]" >&2
    exit 2
    ;;
esac

asset_sum() { # sha256 of a file, whichever tool exists
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

# --- what is installed ------------------------------------------------------
installed_version=""
installed_sum=""
if [ -x "$BIN" ]; then
  installed_version="$("$BIN" --version 2>/dev/null | awk '{print $2}')"
  installed_sum="$(asset_sum "$BIN")"
fi

# --- what is released -------------------------------------------------------
# The API first: it is a few kB, needs no auth on a public repository, and its
# timeout bounds the daily check.  `gh` is the fallback for a rate-limited IP,
# and is only reached when curl could not answer.
latest="$(curl -fsSL --max-time 15 "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null |
  sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1)"
if [ -z "$latest" ] && command -v gh >/dev/null 2>&1; then
  latest="$(gh release view --repo "$REPO" --json tagName -q .tagName 2>/dev/null)"
fi

recorded_tag=""
recorded_sum=""
recorded_error=""
if [ -f "$state" ]; then
  recorded_tag="$(sed -n 's/.*"tag": *"\([^"]*\)".*/\1/p' "$state" | head -1)"
  recorded_sum="$(sed -n 's/.*"sha256": *"\([^"]*\)".*/\1/p' "$state" | head -1)"
  recorded_error="$(sed -n 's/.*"error": *"\([^"]*\)".*/\1/p' "$state" | head -1)"
fi

if [ "$mode" = "--status" ]; then
  echo "installed ${installed_version:-none}  ${installed_sum:-}"
  echo "release   ${latest:-unreachable}"
  echo "recorded  ${recorded_tag:-none}  ${recorded_sum:-}"
  [ -n "$recorded_error" ] && echo "last error $recorded_error"
  exit 0
fi

if [ -z "$latest" ]; then
  echo "release-check: cannot read the latest ${REPO} release (offline, or no proxy)" >&2
  exit 2
fi

# --- is it the release? -----------------------------------------------------
current=0
reason=""
if [ -z "$installed_version" ]; then
  reason="no binary at $BIN"
elif [ "$recorded_tag" != "$latest" ]; then
  reason="recorded tag ${recorded_tag:-none} is not ${latest}"
elif [ -z "$installed_sum" ] || [ "$recorded_sum" != "$installed_sum" ]; then
  reason="the installed binary is not the released one (same version, different bytes)"
else
  current=1
fi

if [ "$current" -eq 1 ]; then
  printf '{"checked": "%s", "tag": "%s", "sha256": "%s", "error": null}\n' \
    "$today" "$latest" "$installed_sum" >"$state"
  [ "$mode" = "--check" ] && echo "current ${installed_version} (${latest})"
  exit 0
fi

if [ "$mode" = "--check" ]; then
  echo "needs install: ${reason}"
  exit 1
fi

# --- install ----------------------------------------------------------------
version="${latest#v}"
# The proxy is a fallback, not a default: on this network GitHub answers
# directly, and a stale proxy would turn a working download into a failure
# (measured 2026-11-19: direct 200, proxied 000).
fetch_to() { # fetch_to URL OUT
  if curl -fsSL --max-time 30 "$1" -o "$2" 2>/dev/null; then return 0; fi
  [ -f "$proxy_file" ] || return 1
  curl -fsSL --max-time 40 -x "$(cat "$proxy_file")" "$1" -o "$2" 2>/dev/null
}

fail() { # one line, recorded so the day is not retried on every session
  printf '{"checked": "%s", "tag": null, "sha256": null, "error": "%s"}\n' \
    "$today" "$1" >"$state"
  echo "oathpass: update to ${latest} failed (${1}); the previous binary is unchanged"
  exit 1
}

# Fetch the installer first: `curl ... | sh` reports sh's status, so a failed
# download would look like a successful install.
installer_tmp="$(mktemp)"
if ! fetch_to "$INSTALLER" "$installer_tmp"; then
  rm -f "$installer_tmp"
  fail "installer download"
fi
# The installer downloads the asset itself, so give it the same fallback.
if ! sh "$installer_tmp" --version "$version" --prefix "$(dirname "$BIN")" \
  >/tmp/release-check.$$ 2>&1; then
  if [ -f "$proxy_file" ] && https_proxy="$(cat "$proxy_file")" \
    http_proxy="$(cat "$proxy_file")" \
    sh "$installer_tmp" --version "$version" --prefix "$(dirname "$BIN")" \
    >/tmp/release-check.$$ 2>&1; then
    :
  else
    tail -3 /tmp/release-check.$$ >&2
    rm -f /tmp/release-check.$$ "$installer_tmp"
    fail "installer"
  fi
fi
rm -f /tmp/release-check.$$ "$installer_tmp"

new_version="$("$BIN" --version 2>/dev/null | awk '{print $2}')"
new_sum="$(asset_sum "$BIN")"
if [ "$new_version" != "$version" ]; then
  fail "installer left ${new_version:-nothing}, wanted $version"
fi
if ! "$BIN" --selftest >/dev/null 2>&1; then
  fail "selftest"
fi

# Do not trust the installer: the installed bytes must be one of the assets the
# release itself lists.  This catches a no-op installer, and an asset that was
# replaced in place of the binary.
sums_tmp="$(mktemp)"
if ! fetch_to "https://github.com/${REPO}/releases/download/${latest}/SHA256SUMS" "$sums_tmp"; then
  rm -f "$sums_tmp"
  fail "cannot read the release checksums"
fi
published="$(awk -v p="oathpass-${version}-" 'index($2, p) == 1 { print $1 }' "$sums_tmp")"
rm -f "$sums_tmp"
if [ -z "$published" ]; then
  fail "the release lists no asset for ${version}"
fi
if ! printf '%s\n' "$published" | grep -qx "$new_sum"; then
  fail "the installed binary is not the released asset"
fi

printf '{"checked": "%s", "tag": "%s", "sha256": "%s", "error": null}\n' \
  "$today" "$latest" "$new_sum" >"$state"

if [ "$installed_version" = "$new_version" ]; then
  echo "oathpass: re-installed ${latest} from the release (selftest passed)"
else
  echo "oathpass ${installed_version:-none} -> ${new_version} (${latest}, selftest passed)"
fi
