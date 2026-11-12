#!/usr/bin/env python3
"""Check the cluster's published partition rates against the local table.

The rates in ``hpc-rates.json`` are what ``hpc-job`` prices jobs with.  They
come from the HPC centre's page and can change, so the daily upkeep runs this
and compares rather than trusting a copy:

    hpc-rates.py --check     # report a difference, change nothing
    hpc-rates.py --update    # rewrite the rate and cores of known partitions

``min_cores`` is not published anywhere; it is local knowledge (this cluster's
intel-sc3-32c cancels jobs under 32 cores) and is preserved across updates.
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
PAGE = "https://hpc.westlake.edu.cn/document/science/en/money.html#partition-billing-standards"


def fetch(url = PAGE):
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


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    update = "--update" in argv
    if not update and "--check" not in argv:
        print(__doc__.strip())
        return 0

    with open(RATES, encoding = "utf-8") as handle:
        local = json.load(handle)

    published = parse(fetch())
    if not published:
        print("hpc-rates: the page parsed to nothing -- its layout probably changed", file = sys.stderr)
        return 2

    differences = 0
    for name, spec in sorted(published.items()):
        have = local["partitions"].get(name)
        if have is None:
            print(f"  new        {name}  ¥{spec['rate']}/{spec['unit']}  ({spec['cores']} cores)")
            differences += 1
            continue
        if abs(have["rate"] - spec["rate"]) > 1e-9:
            print(f"  rate       {name}: {have['rate']} -> {spec['rate']} ¥/{spec['unit']}")
            differences += 1
        if spec["cores"] and have.get("cores") != spec["cores"]:
            print(f"  cores      {name}: {have.get('cores')} -> {spec['cores']}")
            differences += 1

    for name in sorted(set(local["partitions"]) - set(published)):
        print(f"  gone       {name} is in the local table but not on the page")
        differences += 1

    if not differences:
        print(f"hpc-rates: {len(published)} partitions match {RATES} (updated {local.get('updated')})")
        return 0

    if not update:
        print(f"\nhpc-rates: {differences} difference(s); rerun with --update to accept them")
        return 1

    for name, spec in published.items():
        entry = local["partitions"].setdefault(name, {"min_cores": 1})
        entry["rate"] = spec["rate"]
        if spec["cores"]:
            entry["cores"] = spec["cores"]
    local["updated"] = datetime.date.today().isoformat()
    with open(RATES, "w", encoding = "utf-8") as handle:
        json.dump(local, handle, indent = 2)
        handle.write("\n")
    print(f"hpc-rates: {RATES} updated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
