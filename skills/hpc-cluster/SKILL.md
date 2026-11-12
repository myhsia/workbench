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

## Partitions and QoS

| partition | cores | mem | QOS | notes |
|---|---|---|---|---|
| **`douwj`** | 64 | 250G | normal/huge | **the group's own, free**, 10 nodes, `AllowGroups=douwenjie,hpc` |
| `intel-sc3` (Slurm default) | 64 | 480G | normal/huge | SSD `/data` |
| `intel-sc3-32c` | 64 | 480G | normal/huge | **cores must be a multiple of 32** |
| `amd-ep2`, `amd-ep2-short`, `amdepyc` | 64 | 480G | normal/huge | `/data`; `amd-ep2-short` and `amdepyc` are in the rates file but **absent from `scontrol show partition`** |
| `amd-ep5`, `amd-ep5-first` | 256 | 1.5T | normal/huge | `/data`, **`login05` only** |
| `intel-fat` | 96 | 3T | `hmem` only | min memory 450G, 30-day limit |
| GPU partitions | 28–64 | — | gpu/gpu-huge | min 1 GPU; `rt-2080ti-short` 8 h |

**`douwj` is the partition to use.** It is the group's private server (10 nodes × 64 cores, 640
CPUs) and it is **not billed**, so `hpc-rates.json` carries it at `rate: 0.0` (a 64-core hour on
`intel-sc3`/`amd-ep2` is ¥1.28). The *choice* of default is machine-local, not part of the rates
table: `~/.config/opencode/hpc-default` (untracked, mode 600) holds a partition name, currently
`douwj`, and `hpc-job` pins every job to it unless told otherwise. Precedence:
`-p PARTITION` > `$HPC_PARTITION` > that file; `--any` and `--cheap` ignore the default and rank the
whole table.  Setting it: `hpc-job default douwj` (validated against the rates table), reading it:
`hpc-job default`.

`douwj` is free for a job up to its **640 cores** (10 nodes x 64), so such a job costs nothing; only
a request beyond that, or one needing another node type, goes to a paid partition, and the tool
refuses rather than escalating silently: `douwj holds 640 cores (64 x 10 nodes), 700 requested --
pass -p PARTITION to use another`.

| QOS | priority | limit |
|---|---|---|
| `normal` (default) | **high** | **≤200 CPU cores**, 30 concurrent |
| `huge` | **low** | ≤6400 cores |
| `hmem` | high | memory ≥450G, `intel-fat` only |
| `gpu` / `gpu-huge` | high / low | ≤8 / ≤32 GPUs |

Consequences that matter:

- **200 cores is a wall.** Wider than that needs `--qos huge`, which is *low*
  priority: the job may queue far longer than a 64-core `normal` job. `hpc-job`
  refuses >200 cores without `--qos huge` and keeps the default search inside
  `normal`.
- Within one QOS, more resources requested means lower priority.
- `intel-sc3-32c` pads the request to a multiple of 32; the padding is billed
  but does not make the job faster (the tool models that correctly).
- `intel-fat` needs `-p intel-fat --qos hmem --mem 450G`; monthly memory
  efficiency below 50 % gets an account downgraded to `hmem_strict`.

## Jobs and money

Slurm bills **allocated cores per started hour** (`cores × rate × ceil(hours)`),
so a job is a money decision before it is a submission, and an idle allocation
still bills. The rates and QoS rules are **not** in any tool: they live in
`hpc-rates.json` in this repository, checked daily by `scripts/hpc-rates.py`.

```bash
hpc-job cost -c 64 --time 04:00:00                     # price it first
hpc-job default                                        # which partition, and from where
hpc-job default douwj                                  # set the machine-local default
hpc-job submit -c 64 --time 04:00:00 ./run.sh          # the default partition (douwj: free)
hpc-job submit --cheap -c 64 --time 04:00:00 ./run.sh  # cheapest, ignoring the default
hpc-job cost -c 4 --time 01:00:00 --any                # rank the whole table
hpc-job submit -c 64 --time 06:00:00 -p amd-ep2 ./run.sh   # pin the partition
hpc-job submit -c 256 --time 08:00:00 --qos huge ./run.sh
hpc-job list | show ID | log ID | cancel ID
```

The partition is pinned by, in order, `-p PARTITION`/`--partition`, `$HPC_PARTITION`, and the file
`~/.config/opencode/hpc-default` (machine-local, untracked); `hpc-job` prints which one applied, as
`partition  douwj  (from /Users/…/hpc-default)`.  `--any` and `--cheap` drop the pin and rank the
whole table, which is what a node comparison needs; on an exact cost tie that ranking takes the
first entry of the rates file, not necessarily the hardware the user asked for, so use `-p` whenever
the choice of hardware is part of the measurement.

- `--time` is mandatory everywhere; the cluster's default is *no limit*.
- The per-job cap is `spend_limit` in `hpc-rates.json` (¥7.80). Above it,
  submit refuses unless `--yes`; a session asks the user first and quotes the
  estimate.
- Default is the **fastest plan within the cap**; `--cheap` is money-first.
- `oathpass` has **no job surface**: it is the authenticated connection.
  `hpc-job` builds the Slurm command itself and runs it through the master
  (`oathpass 'bash -lc "…"'`), so always go through `hpc-job`.
- Slurm lives under `/soft`; `oathpass` runs job commands through `bash -lc`.
  Cancel what you no longer need, and read MaxRSS in `hpc-job show ID` before
  raising `--mem`.

## Notifications

`hpc-job submit` sends mail to `<login name>@<mail_domain>` (the domain is in
`hpc-rates.json`, the name comes from `oathpass target`) with
`--mail-type=END,FAIL,TIME_LIMIT_80`, unless `--no-mail` is passed.
`hpc-job submit --dry-run` prints the exact `sbatch` line without spending
anything. The mail is for the **user**: an agent cannot
read the inbox, so it still polls `hpc-job show ID` / `hpc-job log ID`. The
80 % trigger exists so the user can cancel before another billed hour starts.

## Storage

- **Home** `/home/<group>Lab/<user>`, **50 GB** — code and configuration only.
  Large data there, or jobs doing heavy I/O from it, risks job cancellation and
  a one-day suspension. `df -h ~` shows the quota.
- **Working directory** `/storage/<group>Lab/<user>` (or `/storage2/…`), 10 TB
  per group; `lfs quota -uh <user> /storage`.
- **`/data` SSD** on the compute nodes of `amd-ep2|intel-sc3|intel-sc3-32c|amd-ep5|amd-ep5-first`.
  Jobs with heavy I/O (>50 concurrent) **must** stage inputs there at job start
  and write outputs there, then copy back and delete. Files are auto-removed
  after 1 day (`amd-ep2`), 3 days (`intel-sc3`), 7 days (login05 partitions).
- Heavy I/O left in the working directory can cap the account at 10 concurrent
  jobs.

## Software

No `sudo`, no `yum`/`apt`. Use the module system:

```bash
module avail | grep -i <name>    # or: module av
module load <name>[/<version>]
module list
module purge
```

`module load anaconda3` then conda for private environments; compile from
source only as a last resort.

## The documentation itself

`scripts/hpc-docs.py --check` hashes all 22 English pages listed in the site's
sitemap and reports what changed; the daily upkeep runs it beside
`hpc-rates.py --check`. When a page moves, read it and update this skill —
the tables above are only as good as the page they came from.

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
