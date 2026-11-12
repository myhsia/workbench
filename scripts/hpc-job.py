#!/usr/bin/env python3
"""Price a Slurm job from a local rate table, then submit it through oathpass.

Slurm bills allocated cores per started hour, so cost = cores x rate x
ceil(hours): a two-minute job costs a full core-hour, and an over-sized request
is charged while it sits idle.  The rates live in ``hpc-rates.json`` next to
this script, refreshed by ``hpc-rates.py`` from the cluster's own page -- they
are not compiled into any tool.

    hpc-job cost -c 64 --time 04:00:00
    hpc-job submit -c 64 --time 04:00:00 ./run.sh          # fastest within the cap
    hpc-job submit --cheap -c 64 --time 04:00:00 ./run.sh  # cheapest
    hpc-job list | show ID | log ID | cancel ID
    hpc-job shell -p PARTITION -c 8 --time 01:00:00

The submission itself is `oathpass job submit`, so it rides the single-use
master connection; this script only decides which partition and whether the
price is acceptable.
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
    parts = text.split(":")
    try:
        numbers = [int(p) for p in parts]
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
    def __init__(self, name, spec, cores, wall, billed, cost):
        self.name = name
        self.spec = spec
        self.cores = cores          # cores requested on this partition
        self.wall = wall            # wall-clock hours at that width
        self.billed = billed        # charged hours (ceil)
        self.cost = cost

    def wall_text(self):
        hours = int(self.wall)
        minutes = int(round((self.wall - hours) * 60))
        if minutes == 60:
            hours, minutes = hours + 1, 0
        return f"{hours}h{minutes:02d}m"


def plan_job(rates, cores, hours, efficiency, max_cores):
    plans = []
    for name, spec in rates["partitions"].items():
        if spec.get("unit", "core-hour") != "core-hour":
            continue  # GPU partitions bill per card-hour; not modelled here
        capacity = int(spec.get("cores", 0))
        minimum = int(spec.get("min_cores", 1))
        if capacity < cores or cores < minimum:
            continue
        usable = min(capacity, max_cores)
        usable = max(usable, cores)
        wall = hours * cores / usable / efficiency
        billed = max(1, math.ceil(wall - 1e-9))
        plans.append(Plan(name, spec, usable, wall, billed, spec["rate"] * usable * billed))
    if not plans:
        die(f"no partition can hold {cores} cores")
    return plans


def choose(plans, limit, cheap):
    cheapest = min(plans, key = lambda p: p.cost)
    if cheap:
        return cheapest, cheapest, False
    within = [p for p in plans if p.cost <= limit + 1e-9]
    if not within:
        return cheapest, cheapest, True
    fastest = min(within, key = lambda p: (p.wall, p.cost))
    return fastest, cheapest, False


def print_table(plans, chosen, cheapest):
    print(f"{'partition':<16}{'cores':>7}{'rate':>9}{'wall':>9}{'billed':>8}{'cost':>10}")
    for plan in plans:
        marks = ""
        if plan is chosen:
            marks += "  <-"
        if plan is cheapest:
            marks += " (cheapest)"
        print(f"{plan.name:<16}{plan.cores:>7}{plan.spec['rate']:>9.3f}{plan.wall_text():>9}"
              f"{plan.billed:>7}h{plan.cost:>10.2f}{marks}")


def describe(rates, chosen, cheapest, over, limit):
    print()
    currency = rates.get("currency", "")
    tag = "  (over the cap)" if over else ""
    print(f"plan       {chosen.name}  {chosen.cores} cores  {chosen.cost:.2f} {currency}{tag}")
    if chosen is not cheapest:
        saving = chosen.cost - cheapest.cost
        slower = cheapest.wall - chosen.wall
        print(f"cheaper    {cheapest.name}  {cheapest.cost:.2f}  "
              f"({slower:.1f}h slower, saves {saving:.2f})")
    if over:
        print(f"cap        {limit:.2f} {currency} -- pass --yes to accept {chosen.cost:.2f}")
    return 0


def split_options(argv):
    """Options up to the first non-option; the rest is the script and its gate."""
    options, rest = {}, []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item in ("-c", "--time", "-p", "-q", "--mem", "--efficiency", "--max-cores", "--budget"):
            if index + 1 >= len(argv):
                die(f"{item} needs a value")
            options[item] = argv[index + 1]
            index += 2
            continue
        if item in ("--cheap", "--yes"):
            options[item] = True
            index += 1
            continue
        rest = argv[index:]
        break
    return options, rest


def cmd_cost(rates, argv):
    options, rest = split_options(argv)
    if rest:
        die(f"unexpected argument '{rest[0]}'")
    if "-c" not in options:
        die("cost needs -c N")
    if "--time" not in options:
        die("cost needs --time HH:MM:SS")
    cores = int(options["-c"])
    hours = parse_time(options["--time"])
    efficiency = float(options.get("--efficiency", 1.0))
    limit = float(options.get("--budget", rates["spend_limit"]))
    max_cores = int(options.get("--max-cores", 1 << 30))

    plans = plan_job(rates, cores, hours, efficiency, max_cores)
    chosen, cheapest, over = choose(plans, limit, False)
    print(f"job        {cores} cores, up to {hours:.2f}h, efficiency {efficiency:.2f}\n")
    print_table(plans, chosen, cheapest)
    return describe(rates, chosen, cheapest, over, limit)


def cmd_submit(rates, argv):
    options, rest = split_options(argv)
    if "--time" not in options:
        die("--time is required: no job is submitted without a wall-clock limit")
    if "-c" not in options:
        die("-c N is required")
    if not rest:
        die("submit needs a script")
    script = rest[0]

    cores = int(options["-c"])
    hours = parse_time(options["--time"])
    efficiency = float(options.get("--efficiency", 1.0))
    limit = float(options.get("--budget", rates["spend_limit"]))
    max_cores = int(options.get("--max-cores", 1 << 30))

    plans = plan_job(rates, cores, hours, efficiency, max_cores)
    chosen, cheapest, over = choose(plans, limit, bool(options.get("--cheap")))
    print_table(plans, chosen, cheapest)
    describe(rates, chosen, cheapest, over, limit)
    if over and not options.get("--yes"):
        die(f"{chosen.cost:.2f} is above the {limit:.2f} cap -- pass --yes to accept it")

    total = int(round(hours * 3600))
    wall = f"{total // 3600:02d}:{(total // 60) % 60:02d}:{total % 60:02d}"
    command = [OATHPASS, "job", "submit", "-p", chosen.name, "-c", str(chosen.cores),
               "--time", wall]
    for option in ("-q", "--mem"):
        if option in options:
            command += [option, options[option]]
    command.append(script)

    print()
    print("running    " + " ".join(command))
    return subprocess.call(command)


def passthrough(argv):
    return subprocess.call([OATHPASS, "job"] + argv)


def selftest():
    rates = load_rates()
    failures = []

    def check(label, got, want):
        if isinstance(want, float):
            good = abs(got - want) < 1e-6
        else:
            good = got == want
        print(f"  {label:<44}{got}   {'OK' if good else 'MISMATCH, want ' + str(want)}")
        if not good:
            failures.append(label)

    plans = plan_job(rates, 64, 4.0, 1.0, 1 << 30)
    by_name = {p.name: p for p in plans}
    check("64 cores/4h: intel-sc3-32c cost", by_name["intel-sc3-32c"].cost, 5.12)
    check("64 cores/4h: amd-ep5-first cost", by_name["amd-ep5-first"].cost, 7.68)
    check("64 cores/4h: amd-ep5-first wall", by_name["amd-ep5-first"].wall, 1.0)
    chosen, cheapest, over = choose(plans, 7.8, False)
    check("64 cores/4h: fastest within cap", chosen.name, "amd-ep5-first")
    check("64 cores/4h: cheapest", cheapest.name, "intel-sc3-32c")

    small = plan_job(rates, 1, 0.5, 1.0, 1)
    check("1 core: no 32-core partition", any(p.name == "intel-sc3-32c" for p in small), False)
    check("1 core: billed as one hour", small[0].billed, 1)
    check("1 core: cost is one core-hour", round(small[0].cost, 2), 0.02)

    over_plans = plan_job(rates, 64, 20.0, 1.0, 1 << 30)
    _, _, over = choose(over_plans, 7.8, False)
    check("64 cores/20h: over the cap", over, True)

    print("selftest passed" if not failures else "selftest FAILED")
    return 0 if not failures else 1


def main(argv):
    if not argv:
        print(__doc__.strip())
        return 0
    command, rest = argv[0], argv[1:]
    if command in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if command == "--selftest":
        return selftest()
    if command in ("list", "show", "log", "cancel", "shell"):
        return passthrough(argv)

    rates = load_rates()
    if command == "cost":
        return cmd_cost(rates, rest)
    if command == "submit":
        return cmd_submit(rates, rest)
    die(f"unknown command '{command}'")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
