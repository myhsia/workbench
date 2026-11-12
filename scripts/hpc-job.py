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
long wait.  The submission itself is `oathpass job submit`, which rides the
single-use master connection and adds the completion mail.
"""

import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
RATES = os.path.join(ROOT, "hpc-rates.json")
OATHPASS = "oathpass"
DEFAULT_QOS = "normal"


def die(message):
    print(f"hpc-job: {message}", file = sys.stderr)
    raise SystemExit(1)


def load_rates(path = RATES):
    with open(path, encoding = "utf-8") as handle:
        data = json.load(handle)
    if not data.get("partitions"):
        die(f"{path} has no partitions")
    return data


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


def plan_job(rates, cores, hours, efficiency, max_cores, qos_name):
    """Plans for one QoS.  `cores` is the job width, `max_cores` how far it may scale."""
    qos = rates["qos"].get(qos_name)
    if qos is None:
        die(f"unknown QoS '{qos_name}'")
    limit = qos.get("max_cores")
    if limit and cores > limit:
        hint = "" if qos_name != DEFAULT_QOS else "  (pass --qos huge to run wider than 200 cores)"
        die(f"{cores} cores exceed the {qos_name} QoS limit of {limit}{hint}")

    plans = []
    for name, spec in rates["partitions"].items():
        if spec.get("unit", "core-hour") != "core-hour":
            continue  # GPU partitions bill per card-hour; not modelled here
        if qos_name not in spec.get("qos", []):
            continue
        capacity = int(spec.get("cores", 0))
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
        plans.append(Plan(name, spec, request, wall, billed, spec["rate"] * request * billed, qos_name))
    if not plans:
        die(f"no partition can hold {cores} cores under QoS {qos_name}")
    return plans


def choose(plans, limit, cheap):
    cheapest = min(plans, key = lambda plan: plan.cost)
    if cheap:
        return cheapest, cheapest, False
    within = [plan for plan in plans if plan.cost <= limit + 1e-9]
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
        if plan is cheapest:
            marks += " (cheapest)"
        print(f"{plan.name:<16}{plan.cores:>7}{plan.spec['rate']:>9.3f}{plan.wall_text():>9}"
              f"{plan.billed:>7}h{plan.cost:>10.2f}  {plan.qos}{marks}")


def describe(rates, chosen, cheapest, over, limit):
    print()
    currency = rates.get("currency", "")
    priority = rates["qos"][chosen.qos].get("priority", "?")
    tag = "  (over the cap)" if over else ""
    print(f"plan       {chosen.name}  {chosen.cores} cores  {chosen.cost:.2f} {currency}"
          f"  qos {chosen.qos} ({priority} priority){tag}")
    if chosen is not cheapest:
        saving = chosen.cost - cheapest.cost
        slower = cheapest.wall - chosen.wall
        print(f"cheaper    {cheapest.name}  {cheapest.cost:.2f}  "
              f"({slower:.1f}h slower, saves {saving:.2f})")
    if chosen.qos != DEFAULT_QOS:
        print(f"queue      {chosen.qos} is low priority; a normal plan may start sooner")
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
        if item in ("-c", "--time", "-p", "-q", "--mem", "--efficiency", "--max-cores", "--budget",
                    "--qos", "--mail-type"):
            if index + 1 >= len(argv):
                die(f"{item} needs a value")
            options[item] = argv[index + 1]
            index += 2
            continue
        if item in ("--cheap", "--yes", "--no-mail", "--dry-run"):
            options[item] = True
            index += 1
            continue
        rest = argv[index:]
        break
    return options, rest


def resolve(rates, options):
    if "-c" not in options:
        die("-c N is required")
    if "--time" not in options:
        die("--time is required: no job is submitted without a wall-clock limit")
    cores = int(options["-c"])
    hours = parse_time(options["--time"])
    efficiency = float(options.get("--efficiency", 1.0))
    limit = float(options.get("--budget", rates["spend_limit"]))
    max_cores = int(options.get("--max-cores", 1 << 30))
    qos = options.get("--qos", DEFAULT_QOS)
    return cores, hours, efficiency, limit, max_cores, qos


def cmd_cost(rates, argv):
    options, rest = split_options(argv)
    if rest:
        die(f"unexpected argument '{rest[0]}'")
    cores, hours, efficiency, limit, max_cores, qos = resolve(rates, options)
    plans = plan_job(rates, cores, hours, efficiency, max_cores, qos)
    chosen, cheapest, over = choose(plans, limit, False)
    print(f"job        {cores} cores, up to {hours:.2f}h, efficiency {efficiency:.2f}, qos {qos}\n")
    print_table(plans, chosen, cheapest)
    return describe(rates, chosen, cheapest, over, limit)


def cmd_submit(rates, argv):
    options, rest = split_options(argv)
    if not rest:
        die("submit needs a script")
    script = rest[0]
    cores, hours, efficiency, limit, max_cores, qos = resolve(rates, options)

    plans = plan_job(rates, cores, hours, efficiency, max_cores, qos)
    chosen, cheapest, over = choose(plans, limit, bool(options.get("--cheap")))
    print_table(plans, chosen, cheapest)
    describe(rates, chosen, cheapest, over, limit)
    if over and not options.get("--yes"):
        die(f"{chosen.cost:.2f} is above the {limit:.2f} cap -- pass --yes to accept it")

    total = int(round(hours * 3600))
    wall = f"{total // 3600:02d}:{(total // 60) % 60:02d}:{total % 60:02d}"
    command = [OATHPASS, "job", "submit", "-p", chosen.name, "-c", str(chosen.cores),
               "--time", wall, "-q", qos]
    for option in ("--mem", "--mail-type"):
        if option in options:
            command += [option, options[option]]
    for flag in ("--no-mail", "--dry-run"):
        if options.get(flag):
            command.append(flag)
    command.append(script)

    print()
    print("running    " + " ".join(command))
    return subprocess.call(command)


def login_name():
    """The cluster login name, read from oathpass's own config."""
    result = subprocess.run([OATHPASS, "target"], capture_output = True, text = True)
    if result.returncode != 0:
        die("oathpass target failed -- is the config in place?")
    target = result.stdout.strip()
    if "@" not in target:
        die(f"unexpected oathpass target output: {target!r}")
    return target.split("@", 1)[0]


def remote(command, stdin = None, capture = False):
    """Run a command on the login node through the master connection.

    oathpass passes the string to ssh, which hands it to the remote shell; the
    login shell is what puts Slurm on PATH, so every command is wrapped in
    `bash -lc`.  The wrapper uses single quotes, so the command may not contain
    one.
    """
    if "'" in command:
        die("internal: a remote command may not contain a single quote")
    argv = [OATHPASS, f"bash -lc '{command}'"]
    if capture:
        return subprocess.run(argv, stdin = stdin, capture_output = True, text = True)
    return subprocess.run(argv, stdin = stdin)


def job_id_ok(value):
    return bool(value) and value.isdigit()


def cmd_list(rates, argv):
    return remote('squeue -u "$USER" -o "%.8i %.20j %.9T %.11M %.5D %R"').returncode


def cmd_show(argv):
    if not argv or not job_id_ok(argv[0]):
        die("show needs a numeric job id")
    command = (f"sacct -j {argv[0]} --noheader --format=JobID%20,JobName%24,State%12,"
               "Elapsed%12,AllocCPUS%10,ReqMem%10,MaxRSS%12,ExitCode%10")
    return subprocess.run([OATHPASS, f"bash -lc '{command}'"]).returncode


def cmd_log(argv):
    if not argv or not job_id_ok(argv[0]):
        die("log needs a numeric job id")
    return remote(f"cat jobs/slurm-{argv[0]}.out").returncode


def cmd_cancel(argv):
    if not argv or not job_id_ok(argv[0]):
        die("cancel needs a numeric job id")
    return remote(f"scancel {argv[0]}").returncode


def cmd_shell(rates, argv):
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
    return remote(f"{command} bash").returncode


def mail_flags(rates, options):
    if options.get("--no-mail"):
        return ""
    domain = rates.get("mail_domain")
    if not domain:
        return ""
    triggers = options.get("--mail-type", "END,FAIL,TIME_LIMIT_80")
    return f" --mail-user={login_name()}@{domain} --mail-type={triggers}"


def cmd_submit(rates, argv):
    options, rest = split_options(argv)
    if not rest:
        die("submit needs a script")
    script = rest[0]
    cores, hours, efficiency, limit, max_cores, qos = resolve(rates, options)

    plans = plan_job(rates, cores, hours, efficiency, max_cores, qos)
    chosen, cheapest, over = choose(plans, limit, bool(options.get("--cheap")))
    print_table(plans, chosen, cheapest)
    describe(rates, chosen, cheapest, over, limit)
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
    command += mail_flags(rates, options)
    command += f" jobs/{base}"

    if options.get("--dry-run"):
        print()
        print(command)
        return 0

    with open(script, "rb") as handle:
        upload = remote(f"mkdir -p jobs && cat > jobs/{base}", stdin = handle)
    if upload.returncode != 0:
        return upload.returncode

    print()
    result = remote(command, capture = True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode
    job_id = result.stdout.strip().split(";")[0]
    if not job_id_ok(job_id):
        die(f"sbatch did not return a job id (got {result.stdout.strip()!r})")

    print(f"submitted  job {job_id}  on {chosen.name}, {chosen.cores} cores, wall {wall}")
    if rates.get("mail_domain") and not options.get("--no-mail"):
        print(f"notify     {login_name()}@{rates['mail_domain']}  "
              f"({options.get('--mail-type', 'END,FAIL,TIME_LIMIT_80')})")
    print(f"watch      hpc-job show {job_id}   /   hpc-job log {job_id}")
    print(f"cancel     hpc-job cancel {job_id}")
    return 0


def selftest():
    rates = load_rates()
    failures = []

    def check(label, got, want):
        good = abs(got - want) < 1e-6 if isinstance(want, float) else got == want
        print(f"  {label:<46}{got}   {'OK' if good else 'MISMATCH, want ' + str(want)}")
        if not good:
            failures.append(label)

    plans = plan_job(rates, 64, 4.0, 1.0, 1 << 30, "normal")
    by_name = {plan.name: plan for plan in plans}
    check("64c/4h normal: intel-sc3-32c cost", by_name["intel-sc3-32c"].cost, 5.12)
    check("64c/4h normal: amd-ep5-first cost", by_name["amd-ep5-first"].cost, 7.68)
    check("64c/4h normal: amd-ep5-first wall", by_name["amd-ep5-first"].wall, 1.0)
    check("64c/4h normal: 256 cores allowed (<=200? no)", 256 <= 200, False)

    planned = plan_job(rates, 33, 2.0, 1.0, 33, "normal")
    rounded = {plan.name: plan.cores for plan in planned}
    check("33 cores, no scaling: 32c rounds to 64", rounded.get("intel-sc3-32c"), 64)
    check("33 cores, no scaling: intel-sc3 stays 33", rounded.get("intel-sc3"), 33)

    huge = plan_job(rates, 256, 4.0, 1.0, 1 << 30, "huge")
    check("256 cores: huge plans exist", len(huge) > 0, True)
    check("256 cores: amd-ep5-first cost", {p.name: p.cost for p in huge}["amd-ep5-first"], 30.72)

    try:
        plan_job(rates, 201, 1.0, 1.0, 1 << 30, "normal")
        over_core = False
    except SystemExit:
        over_core = True
    check("201 cores: refused under normal", over_core, True)

    small = plan_job(rates, 1, 0.5, 1.0, 1, "normal")
    widths = {plan.name: plan.cores for plan in small}
    check("1 core: 32c partition requests 32", widths.get("intel-sc3-32c"), 32)
    check("1 core: intel-sc3 requests 1", widths.get("intel-sc3"), 1)
    check("1 core: no intel-fat", "intel-fat" in widths, False)
    check("1 core: billed one hour", small[0].billed, 1)
    chosen, _, _ = choose(small, 7.8, False)
    check("1 core: cheapest plan is a 1-core request", chosen.cores, 1)

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
    if command == "submit":
        return cmd_submit(rates, argv[1:])
    if command == "list":
        return cmd_list(rates, argv[1:])
    if command == "show":
        return cmd_show(argv[1:])
    if command == "log":
        return cmd_log(argv[1:])
    if command == "cancel":
        return cmd_cancel(argv[1:])
    if command == "shell":
        return cmd_shell(rates, argv[1:])
    die(f"unknown command '{argv[0]}'")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
