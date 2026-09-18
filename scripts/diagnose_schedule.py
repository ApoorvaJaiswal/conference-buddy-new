"""Find out where Friday's program actually lives.

The rendered HTML only contains one day's conference program. This checks whether
the other days are embedded in the page as script data (Next.js and similar
frameworks inline their props), which markdown extraction and tag-stripping both
throw away.

    python scripts/diagnose_schedule.py

It writes the raw HTML to data/raw/schedule.html and reports what it found.
Nothing is parsed into the agenda by this script; it only tells you what exists.
"""

import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
URL = (
    "https://www.wearedevelopers.com/world-congress-north-america/agenda/schedule"
)

# Sessions confirmed to be on specific days, used as day-presence probes.
PROBES = {
    "Day 0 (Wed)": ["1196173", "DeepAgents: Build Multi-Agent"],
    "Day 1 (Thu)": ["1318895", "Manufacturing trust"],
    "Day 2 (Fri)": ["Closing keynote", "Day 2", "Fri, Sep 25"],
}


def main() -> int:
    req = urllib.request.Request(
        URL, headers={"User-Agent": "Mozilla/5.0 (workshop diagnostic)"}
    )
    try:
        html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    except Exception as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1

    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "schedule.html").write_text(html)
    print(f"raw HTML: {len(html):,} bytes -> {RAW / 'schedule.html'}\n")

    # 1. How many session links, and how many carry a time?
    ids = set(re.findall(r"/agenda/sessions/[A-Za-z0-9\-]+?-(\d{5,})", html))
    times = re.findall(r"\d{1,2}:\d{2}\s*[AP]M\s*[\u2013\-]\s*\d{1,2}:\d{2}\s*[AP]M", html)
    print(f"distinct session ids in HTML : {len(ids)}")
    print(f"time ranges in HTML          : {len(times)}\n")

    # 2. Is there an embedded framework payload holding the other days?
    print("embedded data payloads:")
    for label, pattern in [
        ("__NEXT_DATA__", r"__NEXT_DATA__"),
        ("self.__next_f (Next.js RSC)", r"self\.__next_f"),
        ("application/json script", r'<script[^>]+type="application/json"'),
        ("__NUXT__", r"__NUXT__"),
        ("window.__DATA__", r"window\.__[A-Z_]*DATA[A-Z_]*__"),
    ]:
        hits = len(re.findall(pattern, html))
        print(f"  {label:30} {hits}")

    # 3. Which days are actually present in the markup?
    print("\nday probes (is this day's content in the raw HTML?):")
    for day, needles in PROBES.items():
        found = [n for n in needles if n in html]
        verdict = "PRESENT" if found else "absent"
        print(f"  {day:14} {verdict:8} matched: {found or '-'}")

    # 4. Any hint of an API the tab switcher might call.
    print("\ncandidate data endpoints referenced in the page:")
    endpoints = sorted(
        set(
            re.findall(
                r"[\"'](/(?:api|_next/data|graphql)[^\"'\s]{0,120})[\"']", html
            )
        )
    )
    for e in endpoints[:25]:
        print(f"  {e}")
    if not endpoints:
        print("  none found")

    print(
        "\nNext step:\n"
        "  - If a payload above is non-zero, the other days are already in the HTML\n"
        "    and the fix is to parse that JSON instead of the rendered table.\n"
        "  - If all are zero, open DevTools > Network in a browser, click the\n"
        "    'Day 2' tab, and note the request that fires."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
