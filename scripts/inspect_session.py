"""Show where the day actually lives in the markup for one session.

Use when a session comes back with the wrong day, or no day:

    python scripts/inspect_session.py 1196173

It fetches each agenda page, finds that session's link, and prints the raw HTML
around it plus every date-bearing attribute nearby. That tells you whether the
date is in a <time> tag, a data- attribute, a heading, or nowhere at all —
instead of guessing, which is how the wrong-day bug happened in the first place.
"""

import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = "https://www.wearedevelopers.com/world-congress-north-america"
PAGES = [
    f"{BASE}/agenda/schedule",
    f"{BASE}/agenda/workshops",
    f"{BASE}/agenda/masterclasses",
    f"{BASE}/agenda/activities",
    f"{BASE}/agenda/sessions",
]

DATE_ISH = re.compile(
    r"""(\w[\w-]*)\s*=\s*["']([^"']*(?:2026-09-2[345]|Sep|Wed|Thu|Fri)[^"']*)["']""",
    re.I,
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "wad-workshop-diagnostic/1.0"})
    return urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")


def main(sid: str) -> int:
    for url in PAGES:
        name = url.rsplit("/", 1)[-1]
        try:
            html = fetch(url)
        except Exception as exc:
            print(f"\n=== {name}: fetch failed ({exc})")
            continue

        m = re.search(rf'<a\b[^>]*href="[^"]*-{sid}"[^>]*>', html)
        if not m:
            print(f"\n=== {name}: session {sid} not on this page")
            continue

        print(f"\n{'=' * 70}\n=== {name}: found session {sid}\n{'=' * 70}")

        before = html[max(0, m.start() - 2500):m.start()]
        after = html[m.start():m.start() + 800]

        print("\n--- date-bearing attributes in the 2500 chars BEFORE the link ---")
        attrs = DATE_ISH.findall(before)
        for k, v in attrs[-12:]:
            print(f"    {k} = {v[:70]}")
        if not attrs:
            print("    (none)")

        print("\n--- nearest headings before the link ---")
        heads = re.findall(r"<h[1-4][^>]*>(.*?)</h[1-4]>", before, re.S | re.I)
        for h in heads[-4:]:
            print("    " + re.sub(r"<[^>]+>", " ", h).strip()[:90])
        if not heads:
            print("    (none)")

        print("\n--- raw markup, 600 chars before the link ---")
        print("    " + before[-600:].replace("\n", "\n    "))

        print("\n--- the link itself ---")
        print("    " + after[:300].replace("\n", "\n    "))

    print(
        "\n\nWhat to look for:\n"
        "  - a <time datetime=...> or data-date attribute on the row  -> parser reads it\n"
        "  - only a heading far above                                 -> fragile, tell me\n"
        "  - nothing at all                                           -> the day is loaded\n"
        "    by JavaScript and we need the API call instead (see diagnose_schedule.py)\n"
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python scripts/inspect_session.py <session-id>   e.g. 1196173")
    sys.exit(main(sys.argv[1]))
