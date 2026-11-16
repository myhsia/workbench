#!/usr/bin/env python3
"""Price a Slurm job from a local rate table, then submit it through oathpass.

Slurm bills allocated cores per started hour, so cost = cores x rate x
ceil(hours): a two-minute job costs a full core-hour, and an over-sized request
is charged while it sits idle.  The rates and the QoS rules live in
``hpc-rates.json`` next to this script, refreshed by ``hpc-rates.py`` from the
cluster's own page -- they are not compiled into any tool.

    hpc-job cost -c 64 --time 04:00:00
    hpc-job submit -c 64 --time 04:00:00 ./run.sh          # fastest within the cap
    hpc-job submit --cheap -c 64 --time 04:00:00 ./run.sh  # cheapest
    hpc-job submit -c 256 --time 08:00:00 --qos huge ./run.sh
    hpc-job list | show ID | log ID | cancel ID
    hpc-job shell -p PARTITION -c 8 --time 01:00:00

The default QoS is `normal`, which caps a job at 200 cores but has high
priority; `huge` allows 6400 and queues lower.  A job wider than 200 cores is
refused unless `--qos huge` is given, so the fast plan never silently buys a
long wait.  The `sbatch` line is built here and run through
`oathpass 'bash -lc ...'`, so it rides the single-use master connection; the
completion mail is appended to that same command.
"""

import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
RATES = os.path.join(ROOT, "hpc-rates.json")
DEFAULT_PARTITION_FILE = os.path.join(ROOT, "hpc-default")
OATHPASS = "oathpass"
DEFAULT_QOS = "normal"
# `huge` gives up five points of priority for 8-32x the core ceiling and no
# per-user job cap, so it is the default wherever a partition allows it.
QOS_PREFERENCE = ("huge", "normal", "hmem", "fast", "gpu", "gpu-huge",
                  "gpu-l40s", "gpu-lpl", "gpu-wyd", "gpu-wzt")


def die(message):
    print(f"hpc-job: {message}", file = sys.stderr)
    raise SystemExit(1)


def load_rates(path = RATES):
    with open(path, encoding = "utf-8") as handle:
        data = json.load(handle)
    if "profiles" not in data:
        # a file written before campuses were separate: one unnamed profile
        data = {"currency": data.get("currency", "CNY"), "profiles": {"default": data}}
    return data


def oathpass_default_profile():
    """The campus default oathpass would use, read straight from its config."""
    path = os.path.expanduser("~/.config/oathpass/config.json")
    try:
        with open(path, encoding = "utf-8") as handle:
            doc = json.load(handle).get("oathpass", {})
    except (OSError, ValueError):
        return None
    name = doc.get("default")
    if name:
        return name
    profiles = doc.get("profiles")
    if isinstance(profiles, dict) and len(profiles) == 1:
        return next(iter(profiles))
    return None


def select_campus(rates, options):
    """--profile, then $OATHPASS_PROFILE, then oathpass's own default."""
    profiles = rates["profiles"]
    wanted = options.get("--profile") or os.environ.get("OATHPASS_PROFILE") \
        or oathpass_default_profile()
    if wanted is None and len(profiles) == 1:
        wanted = next(iter(profiles))
    if wanted is None:
        die("no campus chosen -- pass --profile NAME (have: " + ", ".join(profiles) + ")")
    if wanted not in profiles:
        die(f"no campus '{wanted}' in {RATES} -- have: " + ", ".join(profiles))
    return wanted, profiles[wanted]


def parse_time(text):
    try:
        numbers = [int(part) for part in text.split(":")]
    except ValueError:
        die("--time must be HH:MM:SS, MM:SS or minutes")
    if len(numbers) == 3:
        hours = numbers[0] + numbers[1] / 60 + numbers[2] / 3600
    elif len(numbers) == 2:
        hours = numbers[0] / 60 + numbers[1] / 3600
    elif len(numbers) == 1:
        hours = numbers[0] / 60
    else:
        die("--time must be HH:MM:SS, MM:SS or minutes")
    if hours <= 0:
        die("--time must be positive")
    return hours


class Plan:
    def __init__(self, name, spec, cores, wall, billed, cost, qos):
        self.name = name
        self.spec = spec
        self.cores = cores
        self.wall = wall
        self.billed = billed
        self.cost = cost
        self.qos = qos

    def wall_text(self):
        hours = int(self.wall)
        minutes = int(round((self.wall - hours) * 60))
        if minutes == 60:
            hours, minutes = hours + 1, 0
        return f"{hours}h{minutes:02d}m"


def round_up(value, step):
    return step * math.ceil(value / step) if step > 1 else value


def plan_job(campus, cores, hours, efficiency, max_cores, qos_name, only = None):
    """Plans for one QoS.  `cores` is the job width, `max_cores` how far it may
    scale, `only` restricts the plans to one named partition."""
    qos = campus["qos"].get(qos_name)
    if qos is None:
        die(f"unknown QoS '{qos_name}'")
    limit = qos.get("max_cores")
    if limit and cores > limit:
        hint = "" if qos_name != DEFAULT_QOS else "  (pass --qos huge to run wider than 200 cores)"
        die(f"{cores} cores exceed the {qos_name} QoS limit of {limit}{hint}")

    plans = []
    for name, spec in campus["partitions"].items():
        if spec.get("unit", "core-hour") != "core-hour":
            continue  # GPU partitions bill per card-hour; not modelled here
        if qos_name not in spec.get("qos", []):
            continue
        if only and name != only:
            continue
        capacity = int(spec.get("cores", 0)) * int(spec.get("nodes", 1))
        if capacity < cores or cores < int(spec.get("min_cores", 1)):
            continue
        if hours > float(spec.get("max_hours", 1e9)):
            continue
        # `useful` is the parallelism the job actually gets; `request` is what
        # Slurm is asked for, which may be padded up to a granularity.  The
        # padding is billed but does not make the job faster.
        useful = max(min(capacity, max_cores), cores)
        if useful > capacity:
            continue
        request = useful
        if "multiple_of" in spec:
            request = round_up(useful, int(spec["multiple_of"]))
            if request > capacity:
                continue
        wall = hours * cores / useful / efficiency
        billed = max(1, math.ceil(wall - 1e-9))
        rate = spec.get("rate")
        cost = None if rate is None else rate * request * billed
        plans.append(Plan(name, spec, request, wall, billed, cost, qos_name))
    if not plans:
        if only:
            spec = campus["partitions"].get(only)
            if spec is None:
                die(f"{only} is not a partition on this campus -- have: "
                    + ", ".join(campus["partitions"]))
            capacity = int(spec.get("cores", 0)) * int(spec.get("nodes", 1))
            die(f"{only} holds {capacity} cores ({spec.get('cores', 0)} x "
                f"{spec.get('nodes', 1)} nodes), {cores} requested "
                f"-- pass -p PARTITION to use another")
        die(f"no partition can hold {cores} cores under QoS {qos_name}")
    return plans


def choose(plans, limit, cheap):
    # a partition without a published rate has no cost to compare: it can be
    # chosen by name, never by price
    priced = [plan for plan in plans if plan.cost is not None]
    if not priced:
        return plans[0], plans[0], False
    cheapest = min(priced, key = lambda plan: plan.cost)
    if cheap:
        return cheapest, cheapest, False
    within = [plan for plan in priced if plan.cost <= limit + 1e-9]
    if not within:
        return cheapest, cheapest, True
    fastest = min(within, key = lambda plan: (plan.wall, plan.cost))
    return fastest, cheapest, False


def print_table(plans, chosen, cheapest):
    print(f"{'partition':<16}{'cores':>7}{'rate':>9}{'wall':>9}{'billed':>8}{'cost':>10}  qos")
    for plan in plans:
        marks = ""
        if plan is chosen:
            marks += "  <-"
        if plan is cheapest and plan is not chosen:
            marks += " (cheapest)"
        rate = plan.spec.get("rate")
        cost = "unknown" if plan.cost is None else f"{plan.cost:.2f}"
        rate_text = f"{rate:.3f}" if rate is not None else "-"
        print(f"{plan.name:<16}{plan.cores:>7}{rate_text:>9}{plan.wall_text():>9}"
              f"{plan.billed:>7}h{cost:>10}  {plan.qos}{marks}")


def describe(campus, chosen, cheapest, over, limit):
    print()
    currency = "CNY"
    priority = campus["qos"][chosen.qos].get("priority", "?")
    tag = "  (over the cap)" if over else ""
    if chosen.cost is None:
        print(f"plan       {chosen.name}  {chosen.cores} cores  cost unknown"
              f"  qos {chosen.qos} ({priority} priority)")
        print(f"unpriced   {chosen.name} has no published rate, so the {limit:.2f} {currency} "
              "cap cannot be enforced")
        return 0
    print(f"plan       {chosen.name}  {chosen.cores} cores  {chosen.cost:.2f} {currency}"
          f"  qos {chosen.qos} ({priority} priority){tag}")
    if chosen is not cheapest and cheapest.cost is not None:
        saving = chosen.cost - cheapest.cost
        slower = cheapest.wall - chosen.wall
        print(f"cheaper    {cheapest.name}  {cheapest.cost:.2f}  "
              f"({slower:.1f}h slower, saves {saving:.2f})")
    normal_priority = campus["qos"].get(DEFAULT_QOS, {}).get("priority")
    priority = campus["qos"].get(chosen.qos, {}).get("priority")
    if normal_priority is not None and priority is not None and priority <= normal_priority - 100:
        print(f"queue      {chosen.qos} (priority {priority}) queues below normal "
              f"({normal_priority}); a normal plan may start sooner")
    if chosen.spec.get("login_node"):
        print(f"login      {chosen.name} is only reachable from {chosen.spec['login_node']}")
    if over:
        print(f"cap        {limit:.2f} {currency} -- pass --yes to accept {chosen.cost:.2f}")
    return 0


def split_options(argv):
    options, rest = {}, []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item in ("-c", "--time", "-p", "--partition", "-q", "--mem", "--efficiency",
                    "--max-cores", "--budget", "--qos", "--mail-type", "--profile"):
            if index + 1 >= len(argv):
                die(f"{item} needs a value")
            options[item] = argv[index + 1]
            index += 2
            continue
        if item in ("--cheap", "--yes", "--no-mail", "--dry-run", "--any"):
            options[item] = True
            index += 1
            continue
        rest = argv[index:]
        break
    return options, rest


def resolve(campus, campus_name, options):
    if "-c" not in options:
        die("-c N is required")
    if "--time" not in options:
        die("--time is required: no job is submitted without a wall-clock limit")
    cores = int(options["-c"])
    hours = parse_time(options["--time"])
    efficiency = float(options.get("--efficiency", 1.0))
    limit = float(options.get("--budget", campus["spend_limit"]))
    # Scaling is opt-in: `-c` is what you ask for, `--max-cores` is how far the
    # job may spread.  Without it a 4-core test would occupy the group's node.
    max_cores = int(options.get("--max-cores", cores))
    qos = options.get("--qos")
    # Partition choice: an explicit -p wins, then this campus's machine-local
    # default ($HPC_PARTITION, then hpc-default).  --any and --cheap drop the
    # pin, because both state a different intent.
    only, source = (options.get("-p") or options.get("--partition")), "-p"
    if not only and not options.get("--any") and not options.get("--cheap"):
        only, source = default_partition(campus_name)
    if only and only not in campus["partitions"]:
        die(f"'{only}' is not a partition on {campus_name} -- have: "
            + ", ".join(campus["partitions"]))
    return cores, hours, efficiency, limit, max_cores, qos, only, source


def read_partition_defaults():
    """{profile: partition}; a bare word is accepted as the default for all."""
    try:
        with open(DEFAULT_PARTITION_FILE, encoding = "utf-8") as handle:
            text = handle.read().strip()
    except FileNotFoundError:
        return {}
    if not text:
        return {}
    if text.startswith("{"):
        try:
            loaded = json.loads(text)
        except ValueError:
            die(f"{DEFAULT_PARTITION_FILE} is not valid JSON")
        return loaded if isinstance(loaded, dict) else {}
    return {"*": text}


def default_partition(campus_name):
    """The machine-local default partition for this campus, and where from."""
    env = os.environ.get("HPC_PARTITION")
    if env and env.strip():
        return env.strip(), "HPC_PARTITION"
    defaults = read_partition_defaults()
    name = defaults.get(campus_name) or defaults.get("*")
    return (name, DEFAULT_PARTITION_FILE) if name else (None, None)


def print_partition(campus_name, only, source):
    """Which campus, and which partition it is pinned to, and why."""
    print(f"campus     {campus_name}")
    if only:
        print(f"partition  {only}  (from {source})")


def print_qos(campus, qos, source):
    spec = campus["qos"].get(qos, {})
    priority = spec.get("priority")
    cap = spec.get("max_cores")
    detail = []
    if priority is not None:
        detail.append(f"priority {priority}")
    if cap:
        detail.append(f"cap {cap} cores")
    note = ", ".join(detail)
    print(f"qos        {qos}" + (f"  ({note})" if note else "") + f"  [from {source}]")


def warn_unverified(campus_name, campus):
    if not campus.get("verified", True):
        print(f"note       {campus_name}'s partition table comes from its documentation, not a "
              "scan; run the scan once logged in")


def cmd_default(rates, argv):
    """Show or set the machine-local default partition, per campus."""
    options, rest = split_options(argv)
    campus_name, campus = select_campus(rates, options)
    if not rest:
        only, source = default_partition(campus_name)
        print(f"campus     {campus_name}")
        if only:
            print(f"default    {only}  (from {source})")
        else:
            print("default    none  (set one with: hpc-job default NAME)")
        return 0
    name = rest[0]
    if name not in campus["partitions"]:
        die(f"unknown partition '{name}' on {campus_name} -- have: "
            + ", ".join(campus["partitions"]))
    spec = campus["partitions"][name]
    defaults = read_partition_defaults()
    defaults.pop("*", None)
    defaults[campus_name] = name
    with open(DEFAULT_PARTITION_FILE, "w", encoding = "utf-8") as handle:
        json.dump(defaults, handle, indent = 2, sort_keys = True)
        handle.write("\n")
    os.chmod(DEFAULT_PARTITION_FILE, 0o600)
    print(f"default    {name}  ({DEFAULT_PARTITION_FILE})")
    print(f"           {spec['cores']} cores, rate {spec['rate']} per {spec.get('unit', 'core-hour')}")
    return 0


def auto_qos(campus, only, cores, hours, efficiency, max_cores):
    """The best QoS that can actually run this job, and why it was picked."""
    candidates = [q for q in QOS_PREFERENCE if q in campus["qos"]]
    if only:
        spec = campus["partitions"].get(only, {})
        allowed = spec.get("qos", [])
        candidates = [q for q in candidates if q in allowed] or allowed
        # a partition may name the QoS it is always run at (douwj: huge), so the
        # choice is recorded in the table rather than inherited from the order
        pinned = spec.get("default_qos")
        if pinned and pinned in allowed:
            candidates = [pinned] + [q for q in candidates if q != pinned]
    for name in candidates:
        try:
            plans = plan_job(campus, cores, hours, efficiency, max_cores, name, only)
        except SystemExit:
            continue
        if plans:
            return name, plans
    die("no QoS on this campus can run the job -- pass --qos")


def cmd_cost(rates, argv):
    options, rest = split_options(argv)
    if rest:
        die(f"unexpected argument '{rest[0]}'")
    campus_name, campus = select_campus(rates, options)
    cores, hours, efficiency, limit, max_cores, qos, only, source = resolve(
        campus, campus_name, options)
    if qos:
        plans = plan_job(campus, cores, hours, efficiency, max_cores, qos, only)
        qos_source = "--qos"
    else:
        qos, plans = auto_qos(campus, only, cores, hours, efficiency, max_cores)
        qos_source = "best available"
    chosen, cheapest, over = choose(plans, limit, bool(options.get("--cheap")))
    print(f"job        {cores} cores, up to {hours:.2f}h, efficiency {efficiency:.2f}\n")
    print_partition(campus_name, only, source)
    print_qos(campus, qos, qos_source)
    warn_unverified(campus_name, campus)
    print_table(plans, chosen, cheapest)
    return describe(campus, chosen, cheapest, over, limit)


def login_name(campus_name = None):
    """The cluster login name, read from oathpass's own config."""
    argv = [OATHPASS] + (["--profile", campus_name] if campus_name else []) + ["target"]
    result = subprocess.run(argv, capture_output = True, text = True)
    if result.returncode != 0:
        die("oathpass target failed -- is the config in place?")
    target = result.stdout.strip()
    if "@" not in target:
        die(f"unexpected oathpass target output: {target!r}")
    return target.split("@", 1)[0]


def remote(command, stdin = None, capture = False, campus_name = None):
    """Run a command on the login node through the master connection.

    oathpass passes the string to ssh, which hands it to the remote shell; the
    login shell is what puts Slurm on PATH, so every command is wrapped in
    `bash -lc`.  The wrapper uses single quotes, so the command may not contain
    one.
    """
    if "'" in command:
        die("internal: a remote command may not contain a single quote")
    argv = [OATHPASS] + (["--profile", campus_name] if campus_name else []) \
        + [f"bash -lc '{command}'"]
    if capture:
        return subprocess.run(argv, stdin = stdin, capture_output = True, text = True)
    return subprocess.run(argv, stdin = stdin)


def job_id_ok(value):
    return bool(value) and value.isdigit()


def cmd_list(rates, argv):
    options, _rest = split_options(argv)
    campus_name, _campus = select_campus(rates, options)
    return remote('squeue -u "$USER" -o "%.8i %.20j %.9T %.11M %.5D %R"',
                  campus_name = campus_name).returncode


def cmd_show(rates, argv):
    options, rest = split_options(argv)
    campus_name, _campus = select_campus(rates, options)
    if not rest or not job_id_ok(rest[0]):
        die("show needs a numeric job id")
    command = (f"sacct -j {rest[0]} --noheader --format=JobID%20,JobName%24,State%12,"
               "Elapsed%12,AllocCPUS%10,ReqMem%10,MaxRSS%12,ExitCode%10")
    return remote(command, campus_name = campus_name).returncode


def cmd_log(rates, argv):
    options, rest = split_options(argv)
    campus_name, _campus = select_campus(rates, options)
    if not rest or not job_id_ok(rest[0]):
        die("log needs a numeric job id")
    return remote(f"cat jobs/slurm-{rest[0]}.out", campus_name = campus_name).returncode


def cmd_cancel(rates, argv):
    options, rest = split_options(argv)
    campus_name, _campus = select_campus(rates, options)
    if not rest or not job_id_ok(rest[0]):
        die("cancel needs a numeric job id")
    return remote(f"scancel {rest[0]}", campus_name = campus_name).returncode


def cmd_shell(rates, argv):
    options, _rest = split_options(argv)
    campus_name, _campus = select_campus(rates, options)
    options, rest = split_options(argv)
    if "--time" not in options:
        die("--time is required: no interactive session without a wall-clock limit")
    if "-p" not in options:
        die("-p PARTITION is required")
    total = int(round(parse_time(options["--time"]) * 3600))
    wall = f"{total // 3600:02d}:{(total // 60) % 60:02d}:{total % 60:02d}"
    cores = int(options.get("-c", 1))
    command = f"srun --pty --time={wall} -c {cores} -p {options['-p']}"
    if "-q" in options:
        command += f" -q {options['-q']}"
    return remote(f"{command} bash", campus_name = campus_name).returncode


def warn_crowded(campus, campus_name, partition):
    """A group partition is shared: say so when it is already busy with your jobs."""
    limit = int(campus.get("warn_jobs", 8))
    result = remote(f'squeue -u "$USER" -h -t RUNNING -p {partition} | wc -l',
                    capture = True, campus_name = campus_name)
    if result.returncode != 0:
        return
    try:
        running = int(result.stdout.strip() or 0)
    except ValueError:
        return
    if running >= limit:
        print(f"busy       {running} of your jobs are already running on {partition} "
              f"(warning at {limit}) -- the partition is shared with the rest of the group")


def mail_flags(campus, options, campus_name):
    if options.get("--no-mail"):
        return ""
    domain = campus.get("mail_domain")
    if not domain:
        return ""
    triggers = options.get("--mail-type", "END,FAIL,TIME_LIMIT_80")
    return f" --mail-user={login_name(campus_name)}@{domain} --mail-type={triggers}"


def cmd_submit(rates, argv):
    options, rest = split_options(argv)
    if not rest:
        die("submit needs a script")
    script = rest[0]
    campus_name, campus = select_campus(rates, options)
    cores, hours, efficiency, limit, max_cores, qos, only, source = resolve(
        campus, campus_name, options)
    if qos:
        plans = plan_job(campus, cores, hours, efficiency, max_cores, qos, only)
        qos_source = "--qos"
    else:
        qos, plans = auto_qos(campus, only, cores, hours, efficiency, max_cores)
        qos_source = "best available"
    chosen, cheapest, over = choose(plans, limit, bool(options.get("--cheap")))
    print_partition(campus_name, only, source)
    print_qos(campus, qos, qos_source)
    warn_unverified(campus_name, campus)
    print_table(plans, chosen, cheapest)
    describe(campus, chosen, cheapest, over, limit)
    if chosen.cost is None and not options.get("--yes"):
        die(f"{chosen.name} has no published rate on this campus -- pass --yes to submit "
            "without a cost estimate")
    if over and not options.get("--yes"):
        die(f"{chosen.cost:.2f} is above the {limit:.2f} cap -- pass --yes to accept it")

    total = int(round(hours * 3600))
    wall = f"{total // 3600:02d}:{(total // 60) % 60:02d}:{total % 60:02d}"
    base = os.path.basename(script)
    if not base or " " in base or "'" in base:
        die("the script name must not contain spaces or quotes")

    command = (f"sbatch --parsable -o jobs/slurm-%j.out -J {base[:40]} -p {chosen.name} "
               f"-c {chosen.cores} -t {wall} -q {qos}")
    if "--mem" in options:
        command += f" --mem={options['--mem']}"
    command += mail_flags(campus, options, campus_name)
    command += f" jobs/{base}"

    if options.get("--dry-run"):
        print()
        print(command)
        return 0

    warn_crowded(campus, campus_name, chosen.name)

    with open(script, "rb") as handle:
        upload = remote(f"mkdir -p jobs && cat > jobs/{base}", stdin = handle,
                        campus_name = campus_name)
    if upload.returncode != 0:
        return upload.returncode

    print()
    result = remote(command, capture = True, campus_name = campus_name)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode
    job_id = result.stdout.strip().split(";")[0]
    if not job_id_ok(job_id):
        die(f"sbatch did not return a job id (got {result.stdout.strip()!r})")

    print(f"submitted  job {job_id}  on {chosen.name}, {chosen.cores} cores, wall {wall}")
    if chosen.cost is None:
        print("cost       unknown (no published rate for this partition)")
    else:
        print(f"cost       {chosen.cost:.2f}")
    if campus.get("mail_domain") and not options.get("--no-mail"):
        print(f"notify     {login_name(campus_name)}@{campus['mail_domain']}  "
              f"({options.get('--mail-type', 'END,FAIL,TIME_LIMIT_80')})")
    print(f"watch      hpc-job show {job_id}   /   hpc-job log {job_id}")
    print(f"cancel     hpc-job cancel {job_id}")
    return 0


def selftest():
    rates = load_rates()
    failures = []

    def check(label, got, want):
        if isinstance(want, float) and isinstance(got, (int, float)) and got is not None:
            good = abs(got - want) < 1e-6
        else:
            good = got == want
        print(f"  {label:<48}{got}   {'OK' if good else 'MISMATCH, want ' + str(want)}")
        if not good:
            failures.append(label)

    check("two campuses in the table", sorted(rates["profiles"]), ["Yungu", "Yunqi"])
    yunqi, yungu = rates["profiles"]["Yunqi"], rates["profiles"]["Yungu"]
    check("Yunqi is marked scanned", yunqi.get("verified"), True)
    check("Yungu is marked scanned", yungu.get("verified"), True)
    check("Yungu has no billing page", yungu.get("source"), None)

    # ---- Yunqi: numbers verified against the live cluster on 2026-11-16
    plans = plan_job(yunqi, 64, 4.0, 1.0, 1 << 30, "normal")
    by_name = {plan.name: plan for plan in plans}
    check("Yunqi 64c/4h: intel-sc3-32c cost", by_name["intel-sc3-32c"].cost, 5.12)
    check("Yunqi 64c/4h: amd-ep5-first cost", by_name["amd-ep5-first"].cost, 7.68)
    check("Yunqi 64c/4h: amd-ep5-first wall", by_name["amd-ep5-first"].wall, 1.0)

    planned = plan_job(yunqi, 33, 2.0, 1.0, 33, "normal")
    rounded = {plan.name: plan.cores for plan in planned}
    check("Yunqi 33c, no scaling: 32c rounds to 64", rounded.get("intel-sc3-32c"), 64)
    check("Yunqi 33c, no scaling: intel-sc3 stays 33", rounded.get("intel-sc3"), 33)

    try:
        plan_job(yunqi, 201, 1.0, 1.0, 1 << 30, "normal")
        over_core = False
    except SystemExit:
        over_core = True
    check("Yunqi 201c: refused under normal", over_core, True)

    wide = plan_job(yunqi, 128, 2.0, 1.0, 1 << 30, "normal", "douwj")
    check("Yunqi 128c on douwj: feasible", len(wide), 1)
    check("Yunqi 128c on douwj: costs nothing", wide[0].cost, 0.0)
    check("Yunqi douwj: capacity 10 x 64", wide[0].cores, 640)

    # ---- Yungu: scanned 2026-11-16, unpriced except douwj
    check("Yungu has the five scanned partitions", sorted(yungu["partitions"]),
          ["douwj", "l40s", "test", "test-intel", "testf"])
    check("Yungu has no Yunqi partition", "amd-ep5-first" in yungu["partitions"], False)
    dy = plan_job(yungu, 64, 2.0, 1.0, 1 << 30, "normal", "douwj")
    check("Yungu douwj: costs nothing", dy[0].cost, 0.0)
    check("Yungu douwj: capacity 5 x 64", dy[0].cores, 320)
    test_plan = plan_job(yungu, 64, 2.0, 1.0, 1 << 30, "normal", "test")
    check("Yungu test: unpriced", test_plan[0].cost, None)
    unpriced = plan_job(yungu, 64, 2.0, 1.0, 1 << 30, "normal")
    chosen, cheapest, over = choose(unpriced, 7.8, False)
    check("Yungu: choose() skips unpriced plans", chosen.cost, 0.0)
    try:
        plan_job(yungu, 64, 1.0, 1.0, 1 << 30, "huge", "amd-ep5-first")
        foreign = False
    except SystemExit:
        foreign = True
    check("Yungu refuses a Yunqi partition", foreign, True)

    # douwj names its own QoS, so it survives a change to the global order
    saved_order = QOS_PREFERENCE
    try:
        globals()["QOS_PREFERENCE"] = ("normal", "huge", "fast")
        picked, _ = auto_qos(yunqi, "douwj", 64, 1.0, 1.0, 64)
        check("douwj keeps huge when the order changes", picked, "huge")
        picked, _ = auto_qos(yunqi, None, 64, 1.0, 1.0, 64)
        check("without a partition the order decides", picked, "normal")
    finally:
        globals()["QOS_PREFERENCE"] = saved_order
    picked, _ = auto_qos(yunqi, "intel-fat", 64, 1.0, 1.0, 64)
    check("intel-fat still resolves to hmem", picked, "hmem")

    # ---- campus selection and the per-campus partition default
    saved = dict(os.environ)
    try:
        os.environ.pop("OATHPASS_PROFILE", None)
        os.environ.pop("HPC_PARTITION", None)
        os.environ["OATHPASS_PROFILE"] = "Yungu"
        name, _ = select_campus(rates, {})
        check("campus: $OATHPASS_PROFILE wins", name, "Yungu")
        name, _ = select_campus(rates, {"--profile": "Yunqi"})
        check("campus: --profile beats the env", name, "Yunqi")

        # scaling is opt-in: resolve() must not widen a job on its own
        _, _, _, _, scaled, _, _, _ = resolve(yunqi, "Yunqi",
                                              {"-c": "4", "--time": "01:00:00", "--any": True})
        check("resolve: no scale-up by default", scaled, 4)
        _, _, _, _, scaled, _, _, _ = resolve(yunqi, "Yunqi",
                                              {"-c": "4", "--time": "01:00:00", "--any": True,
                                               "--max-cores": "640"})
        check("resolve: --max-cores still widens", scaled, 640)

        os.environ["HPC_PARTITION"] = "intel-sc3"
        pinned, source = default_partition("Yunqi")
        check("partition default: $HPC_PARTITION", (pinned, source), ("intel-sc3", "HPC_PARTITION"))
        _, _, _, _, _, _, pinned, _ = resolve(yunqi, "Yunqi", {"-c": "8", "--time": "01:00:00"})
        check("partition default: applied", pinned, "intel-sc3")
        _, _, _, _, _, _, pinned, src = resolve(yunqi, "Yunqi",
                                                {"-c": "8", "--time": "01:00:00", "-p": "amd-ep2"})
        check("partition default: -p beats it", (pinned, src), ("amd-ep2", "-p"))
        _, _, _, _, _, _, pinned, _ = resolve(yunqi, "Yunqi",
                                             {"-c": "8", "--time": "01:00:00", "--any": True})
        check("partition default: --any ignores it", pinned, None)
        try:
            resolve(yungu, "Yungu", {"-c": "8", "--time": "01:00:00", "-p": "amd-ep5-first"})
            campus_bad = False
        except SystemExit:
            campus_bad = True
        check("partition: a foreign partition is refused", campus_bad, True)
    finally:
        os.environ.clear()
        os.environ.update(saved)

    print("selftest passed" if not failures else "selftest FAILED")
    return 0 if not failures else 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if argv[0] == "--selftest":
        return selftest()
    rates = load_rates()
    command = argv[0]
    if command == "cost":
        return cmd_cost(rates, argv[1:])
    if command == "default":
        return cmd_default(rates, argv[1:])
    if command == "submit":
        return cmd_submit(rates, argv[1:])
    if command == "list":
        return cmd_list(rates, argv[1:])
    if command == "show":
        return cmd_show(rates, argv[1:])
    if command == "log":
        return cmd_log(rates, argv[1:])
    if command == "cancel":
        return cmd_cancel(rates, argv[1:])
    if command == "shell":
        return cmd_shell(rates, argv[1:])
    die(f"unknown command '{argv[0]}'")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
