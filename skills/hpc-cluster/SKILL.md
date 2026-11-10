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
- `scp` accepts `:path` so the host never has to be typed, and checks every
  operand's remote half.

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
