#!/usr/bin/env python3
"""Watch the cluster's documentation for changes.

The skill's tables are only as good as the page they came from, so the daily
upkeep hashes every English documentation page and reports what moved:

    hpc-docs.py --check     # report added / changed / removed pages
    hpc-docs.py --update    # accept the current state into hpc-docs.json

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
SITEMAP = "https://hpc.westlake.edu.cn/document/science/sitemap.xml"
BROKEN_HOST = "http://0.0.0.0:8000"
REAL_HOST = "https://hpc.westlake.edu.cn"
DELAY = 0.2


def fetch(url, timeout = 25):
    request = urllib.request.Request(url, headers = {"User-Agent": "hpc-docs/1"})
    with urllib.request.urlopen(request, timeout = timeout) as response:
        return response.read().decode("utf-8", errors = "replace")


def page_list(html):
    urls = []
    for loc in re.findall(r"<loc>([^<]+)</loc>", html):
        if "/en/" not in loc:
            continue
        urls.append(loc.replace(BROKEN_HOST, REAL_HOST))
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


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    update = "--update" in argv
    if not update and "--check" not in argv:
        print(__doc__.strip())
        return 0

    try:
        urls = page_list(fetch(SITEMAP))
    except Exception as error:  # noqa: BLE001 - any failure means "cannot read it"
        print(f"hpc-docs: cannot fetch the sitemap: {error}", file = sys.stderr)
        print("hpc-docs: this is a campus site -- connect to the network or the VPN", file = sys.stderr)
        return 2
    if not urls:
        print("hpc-docs: the sitemap listed no English pages", file = sys.stderr)
        return 2

    try:
        current = snapshot(urls)
    except Exception as error:  # noqa: BLE001
        print(f"hpc-docs: cannot read a page: {error}", file = sys.stderr)
        return 2

    previous = load_manifest().get("pages", {})
    changes = 0
    for url in sorted(current):
        name = url.replace(REAL_HOST + "/document/science/en/", "")
        if url not in previous:
            print(f"  new        {name}  ({current[url]['title']})")
            changes += 1
        elif previous[url]["hash"] != current[url]["hash"]:
            print(f"  changed    {name}  ({current[url]['title']})")
            changes += 1
    for url in sorted(set(previous) - set(current)):
        print(f"  gone       {url.replace(REAL_HOST + '/document/science/en/', '')}")
        changes += 1

    if not changes:
        print(f"hpc-docs: {len(current)} pages match {MANIFEST} (updated {load_manifest().get('updated')})")
        return 0

    if not update:
        print(f"\nhpc-docs: {changes} page(s) moved; read them and update the hpc-cluster skill,")
        print("          then accept the new state with --update")
        return 1

    with open(MANIFEST, "w", encoding = "utf-8") as handle:
        json.dump({"updated": datetime.date.today().isoformat(), "source": SITEMAP, "pages": current},
                  handle, indent = 2, sort_keys = True)
        handle.write("\n")
    print(f"hpc-docs: {MANIFEST} updated with {len(current)} pages")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
