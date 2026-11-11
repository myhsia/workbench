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
- **Set `strategy.max-parallel` explicitly.** Its default is 10, so a 44-job matrix silently runs ten
  at a time and the rest queue behind them; a job that then exceeds its timeout is lost work. The
  ceiling is per **account**, not per run (about 20 concurrent jobs on the free plan), so splitting
  one batch into several runs or several workflows does **not** add machines — it only makes the
  queue harder to see. Size one batch to the ceiling and put the work that must not be split inside
  a single job.
- **One job per heavy unit; sub-units go inside it, on all the cores.** A job with four cores should
  run its four cases as parallel *processes* (`-nproc`) rather than exporting a `case` matrix
  dimension that leaves each core idle. Only split a dimension into the matrix when one job genuinely
  cannot hold the whole unit.
- **`timeout-minutes:` on the job is the real cap** (≤ 350 min here), not the run's. A workflow run
  may last 35 days; a job is killed at its own timeout and its artifact never uploads, so quote the
  step estimate against that number, not against the run.
- **Name the dispatch.** GitHub titles every run of a workflow with the workflow's `name:`, so a
  dozen identical `Data` rows are indistinguishable. Set
  `run-name: Data · ${{ inputs.configs }} · ${{ inputs.methods }}` (inputs and `github.*` are
  available). It cannot be applied retroactively — it is stamped at dispatch.
- Each job uploads its own result with `actions/upload-artifact`:
  - `name:` must be unique per matrix job (include the matrix value).
  - `path:` may list several paths; the artifact is rooted at their **least common ancestor**, so
    listing sibling output dirs gives a tidy tree.
  - `if-no-files-found: error` when a missing file is a failure (use `ignore` only when some jobs
    legitimately produce nothing); `retention-days:` caps storage.
  - An `l3build` job uploads `build/**/*.diff`, `build/**/*.fc` and `build/**/*.log`: the
    comparison it could not satisfy is written to `<test>.<engine>.fc`, so without it the artifact
    arrives with "no difference files" and no evidence of which line moved.
  - A `windows-latest` job writes its logs with CRLF, so a log and the committed baseline can
    differ in the line ending alone. Read the `.fc` first and treat a CRLF-only difference as the
    platform's, not the test's.
- Build any shared environment once in a `needs:`-gated job and hand it to the matrix through a
  cache rather than rebuilding it per job.
- **A CJK font the build needs is not a TeX Live package.**  List the release URLs, one per line
  with `#` comments, in a tracked file such as `.github/font-urls.txt`; key the cache on
  `hashFiles()` of that file, so a changed URL invalidates it; download the collections, unzip the
  `*.ttc` faces, copy them into the per-OS system font directory (`/usr/share/fonts/truetype`,
  `/Library/Fonts`, `/c/Windows/Fonts`) and run `fc-cache -f`.  A font package that TeX Live does
  carry (`lxgw-fonts`, `fandol`) joins the package list instead, and a `windows-latest` job needs
  `wintools.windows` for `unzip`.
- **A `combine`/`collect` job is what makes a batch one download.** `actions/download-artifact` with
  `pattern: '<prefix>-*'` and `merge-multiple: true` assembles every artifact of the run, and a
  `tar -czf` upload gives a single tarball. Guard an empty gather (`[ -n "$(ls -A dist)" ]`), or the
  `tar` exits 2 and the failure reads as a packaging bug. To join *several runs* (one dispatch per
  config, say), dispatch a small `collect` workflow with a `runs` input and download each run's
  tarball by id into one tree — the artifacts stay addressable per run, and the batch is still one
  download at the end.

## 2. Dispatch and watch

```bash
gh workflow run <file>.yaml [--ref <branch>] [-f key=value]
gh run list --workflow <file>.yaml --limit 5
gh run watch <run-id> --exit-status      # blocks; exits 0 only on success
gh run view <run-id> --json status,conclusion,jobs
```

`workflow_dispatch` only works once the workflow exists on the **default branch** (dispatch another
branch with `--ref`). Prefer `gh run watch … --exit-status` over manual polling, but a
**multi-hour** run drops the watch connection; poll it instead and keep the conclusion explicit:

```bash
until [ "$(gh run view <run-id> --json status --jq .status)" = completed ]; do sleep 60; done
gh run view <run-id> --json status,conclusion --jq .conclusion
```

## 3. Download and place

Artifacts live on the GitHub content network (`productionresultssa*.blob.core.windows.net`), which is
badly throttled on a direct route (tens of kB/s).  **Always download through the proxy**, even when a
plain `gh api` call works without it:

```bash
PROXY=$(cat ~/.config/opencode/proxy)   # mode 600, the single source of the address
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
- A step-level `shell:` cannot read the `matrix` context: GitHub rejects the whole file with
  `Invalid workflow file … Unrecognized named-value: 'matrix'`, and because the workflow never
  parses the run does not start at all.  Put the per-OS shell in the job's `defaults.run.shell`
  (`C:\\msys64\\usr\\bin\\bash.exe -e {0}` for MSYS2 bash), which accepts the context and applies
  to every `run:` step of that job.
- Heavy jobs bill runner minutes: keep triggers manual, cache the environment, and set
  `timeout-minutes` on the job. A private repo has a monthly free-minutes budget, and a matrix of many
  long jobs can exhaust it.
- A run whose jobs never start, annotated "The job was not started because recent account payments
  have failed or your spending limit needs to be increased", is a **billing stop, not a code
  failure**.  Private repositories draw on paid minutes while public ones run free, so a private repo
  can fail alone with the same commit; re-running does not help until the account's spending limit is
  raised, and the local equivalents (the CI command run by hand) are the only evidence in the
  meantime.
