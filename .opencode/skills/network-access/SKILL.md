---
name: Network Access
description: Use when fetching external URLs or when a request fails, is blocked, or times out; decide whether to go direct or through the university's international proxy.
compatibility: opencode
metadata:
  audience: maintainers
  scope: machine-global
---

# Network access

Try a **direct** connection first: the university SD-WAN already reaches many hosts without a proxy,
so a plain `curl`, `gh`, `pip`, or `git` (https) usually just works. Only when a host is blocked or
times out (some international sites, e.g. Wikipedia) fall back to the HTTP/HTTPS proxy.

## Direct first

- Reached directly through the SD-WAN: `github.com` / `api.github.com`, `opencode.ai`, `pypi.org`,
  `conda.anaconda.org`, `repo.anaconda.com`, and the Westlake HPC hosts.
- The built-in `webfetch` tool never uses the proxy, so it is the natural "direct first" probe; if it
  times out, retry the URL with `curl` through the proxy and parse the output (e.g. pipe to `python3`).
- "Direct first" is about *reachability*.  For **throughput** the direct route is often throttled;
  see below.

## Bulk transfers (proxy), even when direct works

Large downloads are **not** a block problem but a bandwidth one.  The direct route to the GitHub
content network measured about **27--34 kB/s**, while the proxy gave **1.24--1.35 MB/s** on the same
URL (a 13 MB Actions artifact timed out at 3--4 MB direct and finished in ~10 s proxied, three runs
each).  So:

- Use the proxy **by default** for anything of appreciable size: `gh run download` (artifacts),
  release assets, `git clone` of a big repository, `pip download`, datasets, container layers.
- `github.com` replies with a redirect to a separate CDN host, so the proxy must allow the target,
  not just `github.com`.  Observed targets: `*.blob.core.windows.net` (Actions artifacts,
  `productionresultssa*.blob.core.windows.net`), `objects.githubusercontent.com`,
  `codeload.github.com`, `*.githubusercontent.com`.
- `gh` is a Go binary and honours `HTTPS_PROXY` / `HTTP_PROXY`; no extra flag is needed.

```bash
PROXY=$(cat ~/.config/opencode/proxy)
https_proxy="$PROXY" http_proxy="$PROXY" gh run download <run-id> -n <name> -D /tmp
```

Keep the plain direct form for small API calls (metadata, `gh api`, a few-kB JSON), where the proxy
adds latency without benefit.

## Proxy (on block only)

The proxy address is **not** stored here; it lives in the service environment at
`~/.config/opencode/proxy` (mode 600, a single line). Read it at use time:

```bash
PROXY=$(cat ~/.config/opencode/proxy)
export https_proxy="$PROXY" http_proxy="$PROXY"
curl -s --max-time 30 "https://api.crossref.org/works/<doi>"
```

Export the same variables for `curl`, `wget`, `pip`, `git` (https), etc., and always pass `--max-time`
to avoid hangs.
