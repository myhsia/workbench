---
name: hpc-cluster
description: Log in to the HPC cluster, run read-only commands there, and transfer files, using oathpass. Use whenever a task needs remote compute, remote data, or files moved to or from the cluster.
license: MIT
compatibility: opencode
metadata:
  audience: maintainers
  scope: machine-global
---

# Cluster access

The cluster asks one question, `One-time password (OATH)`, and nothing else.
`oathpass` answers it from a seed in `~/.config/oathpass/config.json`, so no
phone and no interactive shell are involved.

## First run

On a machine without `~/.config/oathpass/config.json`, every command prints the
set-up guide instead of failing, and creates a mode-600 skeleton to edit. With a
terminal attached, `oathpass --init` collects the four values itself -- host,
ports, user, and the `otpauth://` URI, which is read with the terminal echo off
so the seed never appears on screen -- validates the URI, writes the file, and
prints the current code for comparison with the authenticator. Without a
terminal it prints the guide and exits 1 rather than blocking on a prompt.

## Jobs and money

Slurm bills **allocated cores per started hour** (`cores × rate × ceil(hours)`),
so a job is a money decision before it is a submission, and an idle allocation
still bills. The rates are **not** in any tool: they live in
`hpc-rates.json` in this repository, and `scripts/hpc-rates.py --check`
compares them with the cluster's own page.

```bash
hpc-job cost -c 64 --time 04:00:00                     # price it first
hpc-job submit -c 64 --time 04:00:00 ./run.sh          # fastest within the cap
hpc-job submit --cheap -c 64 --time 04:00:00 ./run.sh  # cheapest
hpc-job list | show ID | log ID | cancel ID
```

Rules:

- `--time` is mandatory everywhere; the cluster's default is *no limit*.
- The per-job cap is `spend_limit` in `hpc-rates.json` (currently ¥7.80).
  Above it, `hpc-job submit` refuses unless `--yes`; a session must ask the
  user first and quote the estimate.
- The default is the **fastest plan within the cap**; `--cheap` is the
  money-first path. `-c` is the job's width, `--max-cores` caps scaling.
- `intel-sc3-32c` cancels jobs under 32 cores (measured: `CANCELLED by 0`), so
  it is excluded for small jobs via `min_cores`.
- `oathpass job` does no pricing: it needs `-p` and `--time` and passes them to
  `sbatch`. Always go through `hpc-job`.
- Slurm lives under `/soft`; `oathpass` runs job commands through `bash -lc` for
  that reason. Cancel what you no longer need, and read MaxRSS in
  `hpc-job show ID` before raising `--mem` next time.

## Approval first

**Never touch the cluster without an explicit yes from the user.** Before anything else:

1. State the estimate: how many cores and how long, and why the local eight-core Mac is not the
   right place for it (long DMRG/moments/FSSH sweeps, large scans, much more memory).
2. Ask, and stop. A "no" ends the subject for that task; do not re-ask or route around it.
3. Once approved, batch the work into as few commands as possible -- one driver script beats
   twenty calls -- because `opencode.json` makes every shell command naming `oathpass` prompt the
   user. Finish with `oathpass close`.

The permission rule covers the agents whose rules do not re-allow shell last; the Plan agent has a
built-in trailing `shell * allow`, so in Plan sessions this rule is instruction only, not a gate.

## The single-use rule shapes everything

**The code is single-use.** A second login inside the same 30 s window is
rejected, and a retry costs a full window. Therefore:

- the first command opens **one multiplexed master connection** and spends one
  code;
- every later command, `sftp` and `scp` rides that socket with no code at all;
- `ControlPersist` keeps the master alive indefinitely, so it survives between
  shell invocations. `oathpass close` drops it.

Never open a bare interactive session (`oathpass` with no arguments) to do work
a command could do: it holds a terminal for no reason and the master already
gives you everything.

## Commands

```bash
oathpass status                 # node, master state, socket path
oathpass run ls -la             # read-only command, inside your home
oathpass run grep -rn TITLE .   # no shell syntax, no globbing -- see below
oathpass run find . -name '*.py'
oathpass sftp -b -              # batch sftp; interactive sftp is refused
oathpass scp local.txt :dest/   # ':path' means <user>@<host>:path
oathpass rsync -av ./data/ :dest/
oathpass scp :dest/file.txt .   # fetch
oathpass sockpath               # the socket, for rsync -e
oathpass close                  # drop the master when finished
```

`oathpass check` is a dry run: it prints the node, the code and the socket
without sending anything. `oathpass doctor` explains a code that does not
match the authenticator (clock drift versus a wrong seed).

## Rules for `oathpass run`

- The command must be one of: `ls cat grep head tail wc stat file du df md5sum
  shasum find pwd`.
- No absolute paths, no `~`, no `..`, no `; | & $ ` < >` and no quotes.
- Arguments are quoted for the remote shell, so **globbing does not happen**:
  write `find . -name '*.py'`, not `ls *.py`.
- `find` refuses `-exec`, `-execdir`, `-ok`, `-okdir`, `-delete`, `-fprint`,
  `-fprintf`, `-fls` and `-fprint0`.
- The work happens with the remote working directory set to your home.

Anything outside that list is refused before a connection is opened.

## Transfers

Both transfers enforce the same boundary as `run`: remote paths must stay
inside your home. `../`, absolute paths and `~` are refused **before** a
connection opens.

- `sftp` is **batch-only**: `-b FILE` or `-b -` (stdin); there is no interactive
  mode, because its commands could not be validated. `!` shell escapes are
  refused. To browse, use `oathpass run ls`.
- `scp` and `rsync` accept `:path` so the host never has to be typed, and check
  every operand's remote half. `rsync` refuses `-e`, `-M`, `--remote-option`,
  `--rsync-path` and `--copy-as`, because those either replace the transport or
  run a command on the far side, stepping around that rule.

### What the cluster's own guide requires

The HPC centre's data-transfer page is the authority; these are its rules.

- **Only login nodes** may be used for upload and download. The master is on a
  login node, so every transfer above complies.
- **`scp`/`rsync` command line is the recommended route**; graphical SFTP is an
  acceptable alternative, **FileZilla is explicitly not allowed**, and SCOW
  handles small files in a browser.
- **Never let a client save a credential for this account.** The page warns that
  a TOTP code is dynamic and single-use, so a saved one causes repeated failed
  logins and the account gets blocked as a suspected attack. `oathpass` never
  gives a client a code: one code authenticates the master, and scp/sftp/rsync
  reach the far side over that socket with no authentication at all. `oathpass
  otp` prints a code for a human to read -- it must never be pasted into a
  client's saved-password field.
- **Mind the trailing slash.** `rsync -a dir host:` copies `dir`; `rsync -a
  dir/ host:` copies its contents. With `--delete` the wrong form removes
  files, and the page notes deleted cluster data cannot be recovered.

## Isolation: what this does *not* give you

`oathpass run` is a **tripwire, not a jail**. The account is a full shell, so
`oathpass 'cd /home && ls'` still works, and so does anything typed by hand.
The guard exists so that an agent's mistake (`../`, `/etc/passwd`, a stray
`rm`) fails loudly instead of silently reaching outside the login directory.

Real isolation has to be server-side, and because the cluster authenticates
with OATH only there is no `authorized_keys command=` to hook. The request to
the cluster admin is:

> Please restrict this account's SSH session so that only its login directory
> is visible -- either `ChrootDirectory` in `sshd_config`, or a `ForceCommand`
> wrapper that validates the command. Key-based `command=` restrictions are not
> available to us because the account authenticates with a one-time code only.

The cluster has no `apptainer`, `singularity`, `docker` or `podman` installed,
so a container-based jail cannot be set up from the account itself.

## Troubleshooting

| symptom | cause |
|---|---|
| `code rejected (1/3)` right after a successful login | the code is single-use; stop making per-command logins and use the master |
| `code rejected` three times | wrong seed or clock drift -- run `oathpass doctor` |
| `no login node answered` | campus network or the EasyConnect VPN is not up |
| `master not connected` | expected after `oathpass close`, a reboot, or a network drop; the next command reopens it with one code |
