#!/usr/bin/env python3
"""Watch the cluster's documentation for changes.

The skill's tables are only as good as the page they came from, so the daily
upkeep hashes every English documentation page and reports what moved:

    hpc-docs.py --check                    # every campus
    hpc-docs.py --check --profile Yungu    # one campus
    hpc-docs.py --update [--profile NAME]  # accept the current state

Each campus has its own documentation site, recorded as ``docs[NAME].sitemap``
in ``hpc-docs.json``; Yungu's is an internal address, so its check fails without
the campus network or the VPN (exit 2) rather than reporting a change.

Exit codes follow the other session checks: 0 nothing changed, 1 something
changed, 2 the site could not be read.  A changed page is a prompt to read it
and update `skills/hpc-cluster/SKILL.md` -- this script never edits the skill.
"""

import datetime
import hashlib
import html as htmllib
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
MANIFEST = os.path.join(ROOT, "hpc-docs.json")
# Yungu has no documentation of its own: the only site there mirrors Yunqi's
# pages with different prices, so watching it would only raise false alarms.
SITEMAPS = {"Yunqi": "https://hpc.westlake.edu.cn/document/science/sitemap.xml"}
BROKEN_HOST = "http://0.0.0.0:8000"
REAL_HOST = "https://hpc.westlake.edu.cn"
YUNGU_HOST = "http://10.28.0.22:30538"
DELAY = 0.2


def fetch(url, timeout = 25):
    request = urllib.request.Request(url, headers = {"User-Agent": "hpc-docs/1"})
    with urllib.request.urlopen(request, timeout = timeout) as response:
        return response.read().decode("utf-8", errors = "replace")


def page_list(html, real_host = REAL_HOST):
    """English page URLs, with the sitemap's placeholder host rewritten."""
    urls = []
    for loc in re.findall(r"<loc>([^<]+)</loc>", html):
        if "/en/" not in loc:
            continue
        urls.append(loc.replace(BROKEN_HOST, real_host))
    return sorted(set(urls))


def content(html):
    """The article body, tags stripped and whitespace collapsed."""
    match = re.search(r"(?is)<article[^>]*>(.*?)</article>", html)
    body = match.group(1) if match else html
    body = re.sub(r"(?is)<(script|style|nav)[^>]*>.*?</\1>", " ", body)
    text = re.sub(r"(?s)<[^>]+>", " ", body)
    return htmllib.unescape(re.sub(r"\s+", " ", text)).strip()


def title(html):
    match = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", html)
    if not match:
        return ""
    return htmllib.unescape(re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", "", match.group(1)))).strip()


def snapshot(urls):
    pages = {}
    for index, url in enumerate(urls):
        if index:
            time.sleep(DELAY)
        html = fetch(url)
        body = content(html)
        pages[url] = {
            "title": title(html),
            "hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "bytes": len(body),
        }
    return pages


def load_manifest():
    if not os.path.exists(MANIFEST):
        return {"updated": None, "pages": {}}
    with open(MANIFEST, encoding = "utf-8") as handle:
        return json.load(handle)


def migrate_flat_manifest(manifest):
    """A pre-campus manifest becomes the Yunqi entry."""
    if "profiles" in manifest:
        return
    pages = manifest.get("pages")
    if not pages:
        return
    manifest["profiles"] = {"Yunqi": {"sitemap": SITEMAPS["Yunqi"],
                                      "updated": manifest.get("updated"),
                                      "pages": pages}}
    manifest.pop("pages", None)
    manifest.pop("source", None)
    manifest.pop("updated", None)


def check_campus(name, sitemap, manifest, update):
    """Compare one campus's site with its recorded hashes."""
    try:
        real_host = YUNGU_HOST if sitemap.startswith(YUNGU_HOST) else REAL_HOST
        urls = page_list(fetch(sitemap), real_host)
    except Exception as error:  # noqa: BLE001 - any failure means "cannot read it"
        print(f"hpc-docs: {name}: cannot fetch {sitemap}: {error}", file = sys.stderr)
        print("hpc-docs: this is a campus site -- connect to the network or the VPN",
              file = sys.stderr)
        return 0, True
    if not urls:
        print(f"hpc-docs: {name}: the sitemap listed no English pages", file = sys.stderr)
        return 0, True

    try:
        current = snapshot(urls)
    except Exception as error:  # noqa: BLE001
        print(f"hpc-docs: {name}: cannot read a page: {error}", file = sys.stderr)
        return 0, True

    # a manifest written before campuses were separate holds one flat "pages"
    migrate_flat_manifest(manifest)
    previous = (manifest.get("profiles", {}).get(name, {}) or {}).get("pages", {})
    changes = 0
    for url in sorted(current):
        label = url.replace(REAL_HOST + "/document/science/en/", "").replace(
            YUNGU_HOST + "/en/", "")
        if url not in previous:
            print(f"  {name}: new        {label}  ({current[url]['title']})")
            changes += 1
        elif previous[url]["hash"] != current[url]["hash"]:
            print(f"  {name}: changed    {label}  ({current[url]['title']})")
            changes += 1
    for url in sorted(set(previous) - set(current)):
        print(f"  {name}: gone       {url}")
        changes += 1

    if not changes:
        print(f"  {name}: {len(current)} pages match (updated "
              f"{(manifest.get('profiles', {}).get(name, {}) or {}).get('updated')})")
    elif update:
        manifest.setdefault("profiles", {})[name] = {
            "sitemap": sitemap,
            "updated": datetime.date.today().isoformat(),
            "pages": current,
        }
        print(f"  {name}: recorded {len(current)} pages")
    return changes, False


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

    manifest = load_manifest()
    if only and only not in SITEMAPS:
        print(f"hpc-docs: no campus '{only}' -- have: " + ", ".join(SITEMAPS), file = sys.stderr)
        return 2

    total, unreadable = 0, False
    for name, sitemap in SITEMAPS.items():
        if only and name != only:
            continue
        changes, failed = check_campus(name, sitemap, manifest, update)
        total += changes
        unreadable = unreadable or failed

    if update and total:
        with open(MANIFEST, "w", encoding = "utf-8") as handle:
            json.dump(manifest, handle, indent = 2, sort_keys = True)
            handle.write("\n")
        return 0
    if total:
        print(f"\nhpc-docs: {total} page(s) moved; read them and update the hpc-cluster skill,")
        print("          then accept the new state with --update")
        return 1
    return 2 if unreadable else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
