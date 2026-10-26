---
name: CI Artifacts
description: Use when running long or heavy jobs (data generation, batch or matrix sweeps) on GitHub Actions and retrieving their outputs, or when watching a run and downloading/placing its artifacts.
compatibility: opencode
metadata:
  audience: maintainers
  scope: machine-global
---

# CI artifacts round-trip

Use GitHub Actions as a compute backend for work that is too heavy or too slow locally (data
generation, batch or matrix sweeps), then bring the results home as artifacts.

## 1. Design the workflow

- Trigger it with `workflow_dispatch` (manual) so it never runs on push; inputs can be typed
  (`type: choice`).
- Fan out with `strategy.matrix` over the cases and set `fail-fast: false` so one case does not
  cancel the rest. A matrix value can come from a job output, e.g.
  `matrix: { config: ${{ fromJSON(needs.plan.outputs.configs) }} }`.
- Each job uploads its own result with `actions/upload-artifact`:
  - `name:` must be unique per matrix job (include the matrix value).
  - `path:` may list several paths; the artifact is rooted at their **least common ancestor**, so
    listing sibling output dirs gives a tidy tree.
  - `if-no-files-found: ignore` when some jobs legitimately produce nothing; `retention-days:` caps
    storage.
- Build any shared environment once in a `needs:`-gated job and hand it to the matrix through a
  cache rather than rebuilding it per job.

## 2. Dispatch and watch

```bash
gh workflow run <file>.yaml [--ref <branch>] [-f key=value]
gh run list --workflow <file>.yaml --limit 5
gh run watch <run-id> --exit-status      # blocks; exits 0 only on success
gh run view <run-id> --json status,conclusion,jobs
```

`workflow_dispatch` only works once the workflow exists on the **default branch** (dispatch another
branch with `--ref`). Prefer `gh run watch … --exit-status` over manual polling.

## 3. Download and place

Artifacts live on the GitHub content network (`productionresultssa*.blob.core.windows.net`), which is
badly throttled on a direct route (tens of kB/s).  **Always download through the proxy**, even when a
plain `gh api` call works without it:

```bash
PROXY=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.config/opencode/service.json')))['env']['HTTPS_PROXY'])")
export https_proxy="$PROXY" http_proxy="$PROXY"

gh run download <run-id> -D <tmp>            # all artifacts
gh run download <run-id> -n <name> -D <tmp>  # one artifact
gh run download <run-id> -p '<pat>*' -D <tmp>
```

If `gh run download` is still slow or the proxy is unavailable, fetch the signed blob URL through the
API and `curl` it yourself (the SAS URL needs no auth):

```bash
AID=$(gh api repos/<owner>/<repo>/actions/runs/<id>/artifacts --jq '.artifacts[] | select(.name=="<name>") | .id')
URL=$(curl -s -o /dev/null -D - -H "Authorization: Bearer $(gh auth token)" \
        "https://api.github.com/repos/<owner>/<repo>/actions/artifacts/$AID/zip" \
      | awk 'tolower($1)=="location:"{print $2}' | tr -d '\r')
curl -L --proxy "$PROXY" -o <name>.zip "$URL"
```

Download into a **temporary directory first**, inspect it, then copy into the repo's real output
folders; never download straight over live data. Artifacts keep the ancestor-relative tree, so an
artifact typically contains e.g. `data/<case>/…` and `moments/<case>/…` that map back onto the
project's `output/`.

## Pitfalls

- Artifacts expire (`retention-days`, 90 by default) and count against the repo's storage quota;
  download promptly and delete stale artifacts.
- Re-running a workflow reuses the same run id and its artifacts replace the previous ones; redownload
  with `--clobber`.
- Matrix jobs need **unique** artifact names; a shared name fails the upload.
- Heavy jobs bill runner minutes: keep triggers manual, cache the environment, and set
  `timeout-minutes` on the job. A private repo has a monthly free-minutes budget, and a matrix of many
  long jobs can exhaust it.
