#!/usr/bin/env python3
"""Check the cluster's published partition rates against the local table.

The rates in ``hpc-rates.json`` are what ``hpc-job`` prices jobs with.  They
come from the HPC centre's page and can change, so the daily upkeep runs this
and compares rather than trusting a copy:

    hpc-rates.py --check                    # every campus, change nothing
    hpc-rates.py --check --profile Yungu    # one campus
    hpc-rates.py --update [--profile NAME]  # rewrite rates/cores of known partitions

Each campus in ``hpc-rates.json`` carries its own ``source`` page (the two
campuses bill differently: flat ¥0.045/core-hour at Yungu against
¥0.02--0.15 at Yunqi).  ``min_cores`` is local knowledge the page does not
publish, and is preserved across updates.
"""

import datetime
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
RATES = os.path.join(ROOT, "hpc-rates.json")
def fetch(url):
    request = urllib.request.Request(url, headers = {"User-Agent": "hpc-rates/1"})
    try:
        with urllib.request.urlopen(request, timeout = 25) as response:
            return response.read().decode("utf-8", errors = "replace")
    except Exception as error:  # noqa: BLE001 - any failure means "cannot read it"
        print(f"hpc-rates: cannot fetch {url}: {error}", file = sys.stderr)
        print("hpc-rates: this is a campus page -- connect to the network or the VPN", file = sys.stderr)
        raise SystemExit(2)


def cells(row):
    return [re.sub(r"<[^>]+>", "", cell).strip() for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]


def parse(html):
    """{partition: {"rate": float, "cores": int, "unit": "core-hour"|"card-hour"}}"""
    found = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        columns = cells(row)
        if len(columns) < 3:
            continue
        name = re.sub(r"\s*\(.*?\)\s*", "", columns[0]).strip()
        if not name or " " in name:
            continue
        billing = next((c for c in columns[1:] if "¥" in c), None)
        if not billing:
            continue
        match = re.match(r"¥\s*([0-9.]+)\s*/\s*(core|card)-hour", billing)
        if not match:
            continue
        spec = next((c for c in columns[1:] if "core" in c and "-core" in c), "")
        cores = re.search(r"(\d+)-core", spec)
        found[name] = {
            "rate": float(match.group(1)),
            "unit": f"{match.group(2)}-hour",
            "cores": int(cores.group(1)) if cores else None,
        }
    return found


def check_profile(name, local, update):
    """Compare one campus with its page; returns (differences, unreadable)."""
    page = local.get("source")
    if not page:
        # Yungu publishes no billing page; its partitions were scanned instead
        print(f"  {name}: no billing page -- not checked (table from the scan, "
              f"updated {local.get('updated')})")
        return 0, False
    try:
        published = parse(fetch(page))
    except SystemExit:
        return 0, True
    if not published:
        print(f"{name}: {page} parsed to nothing -- its layout probably changed", file = sys.stderr)
        return 0, True

    differences = 0
    partitions = local.get("partitions", {})
    for part_name, spec in sorted(published.items()):
        have = partitions.get(part_name)
        if have is None:
            print(f"  {name}: new        {part_name}  ¥{spec['rate']}/{spec['unit']}  "
                  f"({spec['cores']} cores)")
            differences += 1
            continue
        if abs(have["rate"] - spec["rate"]) > 1e-9:
            print(f"  {name}: rate       {part_name}: {have['rate']} -> {spec['rate']} "
                  f"¥/{spec['unit']}")
            differences += 1
        if spec["unit"] == "core-hour" and spec["cores"] and have.get("cores") != spec["cores"]:
            print(f"  {name}: cores      {part_name}: {have.get('cores')} -> {spec['cores']}")
            differences += 1

    for part_name in sorted(set(partitions) - set(published)):
        # a group-private partition (douwj) is deliberately absent from the
        # published page, so it is not a difference
        if partitions[part_name].get("private"):
            continue
        print(f"  {name}: gone       {part_name} is local but not on {page}")
        differences += 1

    if differences and update:
        for part_name, spec in published.items():
            entry = partitions.setdefault(part_name, {"min_cores": 1})
            entry["rate"] = spec["rate"]
            if spec["cores"]:
                entry["cores"] = spec["cores"]
            entry.setdefault("unit", spec["unit"])
        local["updated"] = datetime.date.today().isoformat()
        print(f"  {name}: updated ({len(published)} partitions from {page})")
    elif not differences:
        print(f"  {name}: {len(published)} partitions match (updated {local.get('updated')})")
    return differences, False


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    update = "--update" in argv
    if not update and "--check" not in argv:
        print(__doc__.strip())
        return 0
    only = None
    for i, item in enumerate(argv):
        if item == "--profile" and i + 1 < len(argv):
            only = argv[i + 1]
        elif item.startswith("--profile="):
            only = item.split("=", 1)[1]

    with open(RATES, encoding = "utf-8") as handle:
        document = json.load(handle)
    profiles = document.get("profiles") or {"default": document}
    if only and only not in profiles:
        print(f"hpc-rates: no campus '{only}' -- have: " + ", ".join(profiles), file = sys.stderr)
        return 2

    total, unreadable = 0, False
    for name, local in profiles.items():
        if only and name != only:
            continue
        differences, failed = check_profile(name, local, update)
        total += differences
        unreadable = unreadable or failed

    if total and not update:
        print(f"\nhpc-rates: {total} difference(s); rerun with --update to accept them")
        return 1
    if unreadable and not total:
        return 2
    if update and total:
        with open(RATES, "w", encoding = "utf-8") as handle:
            json.dump(document, handle, indent = 1)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
