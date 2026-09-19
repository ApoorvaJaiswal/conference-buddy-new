"""Fetch the real WeAreDevelopers World Congress North America agenda.

Two public pages, joined on the numeric session ID that ends every session URL:

  /agenda/sessions   title, speakers, abstract, topics, format+duration
  /agenda/schedule   day, start, end, stage, track

Nothing here invents data. A field the site does not publish stays None, and the
tools downstream report it as unknown rather than guessing. In particular:

  - Friday's (Day 2) conference program is rendered client-side on the schedule
    page, so a plain fetch cannot see it. Those sessions come through with
    day/start/end/stage = None. That is the truth as of writing; if the site
    changes, this script will simply pick them up.
  - There is no floor plan or walk-time data published anywhere, so there is no
    walk-time field and no walk-time tool.
  - There are no difficulty levels published, so there is no level field.

Safety: a parse that looks broken never overwrites a good data file. Raw HTML is
saved to data/raw/ so you can see what actually came back when it breaks.

Usage:
    python scripts/fetch_agenda.py              # refresh if stale (>12h) or missing
    python scripts/fetch_agenda.py --force      # always refetch
    python scripts/fetch_agenda.py --check      # parse only, write nothing, report
    python scripts/fetch_agenda.py --offline    # fail immediately if no cache
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "sessions.json"

BASE = "https://www.wearedevelopers.com/world-congress-north-america"
SESSIONS_URL = f"{BASE}/agenda/sessions"
SCHEDULE_URL = f"{BASE}/agenda/schedule"

# Pages that render session *cards* (title, speakers, abstract, topics).
CARD_PAGES = [
    f"{BASE}/agenda/sessions",
    f"{BASE}/agenda/workshops",
    f"{BASE}/agenda/masterclasses",
    f"{BASE}/agenda/activities",
    f"{BASE}/agenda/docker",
    f"{BASE}/agenda/github",
]

# Pages that render a *grid* (time, stage, track inside the link text).
GRID_PAGES = [
    f"{BASE}/agenda/schedule",
    f"{BASE}/agenda/workshops",
    f"{BASE}/agenda/masterclasses",
    f"{BASE}/agenda/activities",
]

ALL_PAGES = sorted(set(CARD_PAGES) | set(GRID_PAGES))

STALE_AFTER_SECONDS = 12 * 3600

# Every session link ends in -<numeric id>. That ID is the join key and the one
# thing on these pages we can rely on completely.
SESSION_HREF = re.compile(
    r"/agenda/sessions/([A-Za-z0-9\-]+?)-(\d{5,})(?=[\"'\s/?#>]|$)"
)

# "10:20 AM–10:50 AM"  /  "8:00 PM-11:00 PM"  (en dash or hyphen)
TIME_RANGE = re.compile(
    r"\b(\d{1,2}:\d{2}\s*[AP]M)\s*[–\-—]\s*(\d{1,2}:\d{2}\s*[AP]M)", re.I
)

# "Mainstage", "Tech Leaders Stage", "Stage 7", "Outdoor Stage", "All stages"
STAGE = re.compile(
    r"\b(Mainstage|Tech Leaders Stage|Outdoor Stage|All stages|Stage\s+\d{1,2})\b", re.I
)

# "Session (30 min, incl. Q&A)", "Workshop (120 min)", "Full-Day Masterclass (480 min...)"
FORMAT = re.compile(
    r"\b(Full-Day Masterclass|Masterclass|Workshop|Start-?Up Presentation|Session)\b"
    r"(?:\s*\((\d+)\s*min)?",
    re.I,
)

# The event's own track labels, as they appear on the schedule page.
PREREG = re.compile(r"pre-?registration\s+required", re.I)

KNOWN_TRACKS = [
    "AI Agents", "AI Engineering", "AI Models & Infrastructure", "AI Trust & Safety",
    "Applied AI", "Architecture & Backend", "Career, Culture & Community",
    "Data & Databases", "DevEx & Productivity", "DevOps & Platform Engineering",
    "Languages, Web & Mobile", "Leadership & Strategy", "Physical AI",
    "Security & Privacy", "Startups & Innovation",
]

DAYS = {
    "day 0": "2026-09-23",
    "day 1": "2026-09-24",
    "day 2": "2026-09-25",
}


# ── fetching ────────────────────────────────────────────────────────────────


def fetch(url: str, timeout: int = 40) -> str:
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "wad-conference-buddy-workshop/1.0 (+educational workshop)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def visible_text(html: str) -> str:
    """Strip tags without a parser dependency, keeping link boundaries visible."""
    html = re.sub(r"(?is)<(script|style|svg)\b.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|li|td|tr|h[1-6])>", "\n", html)
    html = re.sub(r"<[^>]*$", " ", html)      # chunk may end mid-tag
    html = re.sub(r"<[^>]+>", " ", html)
    html = (
        html.replace("&amp;", "&").replace("&nbsp;", " ")
        .replace("&#x27;", "'").replace("&quot;", '"')
        .replace("&lt;", "<").replace("&gt;", ">")
        .replace("&#8211;", "–").replace("&ndash;", "–").replace("&mdash;", "—")
        .replace("&middot;", "·").replace("&#183;", "·").replace("&#8901;", "·")
    )
    return re.sub(r"[ \t]+", " ", html)


# ── parsing ─────────────────────────────────────────────────────────────────


def _cards_before_links(html: str) -> dict[str, str]:
    """Sessions page: each card's body sits BEFORE its 'View Session Details' link.

    A card therefore runs from the end of the previous session link to the start
    of this one. Bounding by neighbouring links rather than a fixed window is
    what stops one session's speakers and topics leaking into the next.
    """
    matches = list(SESSION_HREF.finditer(html))
    blocks: dict[str, str] = {}
    for i, m in enumerate(matches):
        prev_end = matches[i - 1].end() if i else 0
        raw = html[prev_end : m.start()]
        # The previous card's "View Session Details</a>" tail sits at the front
        # of this slice. Left in, its word "Session" wins the format match.
        if "</a>" in raw[:400]:
            raw = raw.split("</a>", 1)[1]
        chunk = visible_text(raw)
        sid = m.group(2)
        if len(chunk) > len(blocks.get(sid, "")):
            blocks[sid] = chunk
    return blocks


ANCHOR = re.compile(
    r"<a\b[^>]*href=\"[^\"]*?/agenda/sessions/[A-Za-z0-9\-]+?-(\d{5,})[^\"]*\"[^>]*>(.*?)</a>",
    re.I | re.S,
)


def _anchor_texts(html: str) -> dict[str, tuple[str, int]]:
    """Schedule page: time, stage and track live INSIDE the anchor text.

    Returns id -> (text, position). Position is the offset in the raw HTML, used
    to work out which day heading the row falls under.
    """
    found: dict[str, tuple[str, int]] = {}
    for m in ANCHOR.finditer(html):
        sid, text = m.group(1), visible_text(m.group(2))
        if sid not in found or len(text) > len(found[sid][0]):
            found[sid] = (text, m.start())
    return found


def _slugs(html: str) -> dict[str, str]:
    return {m.group(2): m.group(1) for m in SESSION_HREF.finditer(html)}


def parse_sessions_page(html: str) -> dict[str, dict]:
    """Title, format, duration, speakers, abstract, topics. No times here."""
    out: dict[str, dict] = {}
    slugs = _slugs(html)

    for sid, block in _cards_before_links(html).items():
        record = {
            "id": sid,
            "url": f"{BASE}/agenda/sessions/{slugs[sid]}-{sid}",
            "title": None,
            "format": None,
            "duration_minutes": None,
            "speakers": [],
            "abstract": None,
            "topics": [],
            "requires_registration": bool(PREREG.search(block)),
        }

        fmt = FORMAT.search(block)
        if fmt:
            record["format"] = fmt.group(1).title().replace("Up", "up")
            if fmt.group(2):
                record["duration_minutes"] = int(fmt.group(2))

        # Title: derived from the slug, which is stable. Prefer a cased title
        # from the block when we can find one that matches the slug's shape.
        record["title"] = _title_from_block(block, slugs[sid])
        record["title_from_slug"] = record["title"] is None
        if record["title"] is None:
            # Derived from the real URL, not invented. Flagged so the tools
            # and the reader can tell it apart from a published title.
            record["title"] = slugs[sid].replace("-", " ").strip()
        record["speakers"] = _speakers_from_block(block)
        record["topics"] = _topics_from_block(block)
        record["abstract"] = _abstract_from_block(block)

        out[sid] = record
    return out


def _title_from_block(block: str, slug: str) -> str | None:
    """Find the line in the block that matches the slug's word sequence."""
    words = [w for w in slug.split("-") if len(w) > 3][:5]
    if not words:
        return None
    best, best_score = None, 0
    for line in (l.strip() for l in block.split("\n")):
        if not (8 <= len(line) <= 200):
            continue
        low = line.lower()
        score = sum(1 for w in words if w in low)
        if score > best_score:
            best, best_score = line, score
    return best if best_score >= 2 else None


def _speakers_from_block(block: str) -> list[dict]:
    """Speakers appear as 'Name · Role at Company' or 'Name · Role · Company'."""
    speakers = []
    for line in block.split("\n"):
        for part in line.split(","):
            part = part.strip()
            if "·" not in part or len(part) > 160:
                continue
            chunks = [c.strip() for c in part.split("·") if c.strip()]
            if len(chunks) < 2:
                continue
            name = chunks[0]
            # A speaker name: two-to-four capitalised words, no sentence punctuation.
            if not re.fullmatch(r"[^.!?;:]{2,60}", name) or len(name.split()) > 5:
                continue
            role, company = chunks[1], (chunks[2] if len(chunks) > 2 else None)
            if company is None and " at " in role:
                role, company = role.rsplit(" at ", 1)
            entry = {"name": name, "role": role or None, "company": company}
            if entry not in speakers:
                speakers.append(entry)
    return speakers


def _topics_from_block(block: str) -> list[str]:
    m = re.search(r"\bTopics\b(.{0,600})", block, re.S)
    if not m:
        return []
    tail = m.group(1)
    topics = [
        t.strip(" *\u2022-")
        for t in tail.split("\n")
        if 2 < len(t.strip(" *\u2022-")) < 60
    ]
    return [t for t in topics[:15] if t and not t.lower().startswith("view session")]


def _abstract_from_block(block: str) -> str | None:
    body = block.split("Topics")[0]
    paragraphs = [p.strip() for p in body.split("\n") if len(p.strip()) > 120]
    if not paragraphs:
        return None
    return " ".join(paragraphs)[:4000]


def parse_schedule_page(html: str) -> dict[str, dict]:
    """Day, start, end, stage, track for sessions the page actually renders.

    Anything the page does not render (Friday's conference program is built
    client-side) simply does not appear here, and stays unscheduled downstream.
    """
    # Day headings, located in the raw HTML so offsets line up with anchors.
    headings = sorted(
        (m.start(), DAYS[re.sub(r"\s+", " ", m.group(1)).lower()])
        for m in re.finditer(r"\b(Day\s*[012])\b", html, re.I)
    )

    out: dict[str, dict] = {}
    for sid, (text, pos) in _anchor_texts(html).items():
        times = TIME_RANGE.search(text)
        if not times:
            continue

        stage = STAGE.search(text)
        track = next((t for t in KNOWN_TRACKS if t in text), None)

        prior = [iso for offset, iso in headings if offset <= pos]
        out[sid] = {
            "requires_registration": bool(PREREG.search(text)) or None,
            "day": prior[-1] if prior else None,
            "start": _to_24h(times.group(1)),
            "end": _to_24h(times.group(2)),
            "stage": stage.group(1).strip() if stage else None,
            "track": track,
        }
    return out


def _to_24h(value: str) -> str:
    return datetime.strptime(value.upper().replace(" ", ""), "%I:%M%p").strftime("%H:%M")


# ── assembly and validation ─────────────────────────────────────────────────


def merge(into: dict, extra: dict) -> dict:
    """Fill empty fields only. First page to publish a real value wins."""
    for key, value in extra.items():
        if value in (None, [], "") :
            continue
        if into.get(key) in (None, [], ""):
            into[key] = value
    return into


def build(pages: dict[str, str]) -> dict:
    """pages maps URL -> raw HTML. Details come from card pages, times from grids."""
    details: dict[str, dict] = {}
    for url in CARD_PAGES:
        html = pages.get(url)
        if not html:
            continue
        for sid, record in parse_sessions_page(html).items():
            if sid in details:
                merge(details[sid], record)
            else:
                details[sid] = record

    times: dict[str, dict] = {}
    for url in GRID_PAGES:
        html = pages.get(url)
        if not html:
            continue
        for sid, slot in parse_schedule_page(html).items():
            if sid in times:
                merge(times[sid], slot)
            else:
                times[sid] = slot

    # A session can appear in a grid but have no card anywhere.
    all_slugs: dict[str, str] = {}
    for html in pages.values():
        all_slugs.update(_slugs(html))

    for sid in times:
        if sid in details:
            continue
        slug = all_slugs.get(sid, "")
        details[sid] = {
            "id": sid,
            "url": f"{BASE}/agenda/sessions/{slug}-{sid}" if slug else None,
            "title": slug.replace("-", " ").strip() or None,
            "title_from_slug": True,
            "format": None, "duration_minutes": None,
            "speakers": [], "abstract": None, "topics": [],
            "requires_registration": False,
        }

    records = []
    for sid, record in details.items():
        slot = times.get(sid, {})
        record.update(
            {
                "day": slot.get("day"),
                "start": slot.get("start"),
                "end": slot.get("end"),
                "stage": slot.get("stage"),
                "track": record.get("track") or slot.get("track"),
                "requires_registration": bool(
                    record.get("requires_registration") or slot.get("requires_registration")
                ),
                "scheduled": bool(slot.get("start")),
            }
        )
        records.append(record)

    records.sort(
        key=lambda r: (r["day"] or "9999", r["start"] or "99:99", r["stage"] or "~")
    )

    return {
        "event": {
            "name": "WeAreDevelopers World Congress North America 2026",
            "dates": ["2026-09-23", "2026-09-24", "2026-09-25"],
            "venue": "San Jose McEnery Convention Center",
            "address": "150 W San Carlos St, San Jose, CA",
            "timezone": "America/Los_Angeles",
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": sorted(pages),
        "caveats": [
            "Scraped from the public agenda pages. Every field came from the site; "
            "nothing is invented.",
            "The organisers note that exact session times are still being finalised "
            "and may shift closer to the event.",
            "Sessions with scheduled=false have no published time or stage in any "
            "page fetched. Run scripts/diagnose_schedule.py to see whether more is "
            "reachable.",
            "No floor plan or walking-distance data is published, so the buddy "
            "cannot judge whether a room-to-room transition is feasible.",
            "No difficulty levels are published.",
        ],
        "sessions": records,
    }


def validate(payload: dict) -> list[str]:
    """Gates that must pass before this is allowed to replace a good data file."""
    sessions = payload["sessions"]
    problems = []

    if len(sessions) < 40:
        problems.append(f"only {len(sessions)} sessions parsed (expected 40+)")

    titled = [s for s in sessions if s["title"]]
    if len(titled) < len(sessions) * 0.8:
        problems.append(f"only {len(titled)}/{len(sessions)} sessions got a title")

    scheduled = [s for s in sessions if s["scheduled"]]
    if len(scheduled) < 20:
        problems.append(f"only {len(scheduled)} sessions have times (expected 20+)")

    if not any(s["speakers"] for s in sessions):
        problems.append("no speakers parsed on any session")

    bad_times = [
        s for s in scheduled
        if not re.fullmatch(r"\d{2}:\d{2}", s["start"] or "")
        or not re.fullmatch(r"\d{2}:\d{2}", s["end"] or "")
    ]
    if bad_times:
        problems.append(f"{len(bad_times)} sessions have malformed times")

    return problems


def summarise(payload: dict) -> str:
    sessions = payload["sessions"]
    by_day: dict[str, int] = {}
    for s in sessions:
        by_day[s["day"] or "unscheduled"] = by_day.get(s["day"] or "unscheduled", 0) + 1
    lines = [
        f"  sessions parsed : {len(sessions)}",
        f"  with a time slot: {sum(1 for s in sessions if s['scheduled'])}",
        f"  with speakers   : {sum(1 for s in sessions if s['speakers'])}",
        f"  with an abstract: {sum(1 for s in sessions if s['abstract'])}",
        "  by day:",
    ]
    for day in sorted(by_day):
        lines.append(f"    {day}: {by_day[day]}")
    stages = sorted({s["stage"] for s in sessions if s["stage"]})
    lines.append(f"  stages seen     : {', '.join(stages) or 'none'}")
    return "\n".join(lines)


# ── entry point ─────────────────────────────────────────────────────────────


def is_stale() -> bool:
    if not OUT.exists():
        return True
    return (time.time() - OUT.stat().st_mtime) > STALE_AFTER_SECONDS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch even if fresh")
    ap.add_argument("--check", action="store_true", help="parse and report, write nothing")
    ap.add_argument("--offline", action="store_true", help="never hit the network")
    args = ap.parse_args()

    if args.offline:
        if OUT.exists():
            print(f"offline: using cached {OUT}")
            return 0
        print("offline: no cached agenda available", file=sys.stderr)
        return 1

    if not (args.force or args.check) and not is_stale():
        print(f"agenda is fresh ({OUT}); use --force to refetch")
        return 0

    DATA.mkdir(exist_ok=True)
    RAW.mkdir(exist_ok=True)

    pages: dict[str, str] = {}
    for url in ALL_PAGES:
        name = url.rstrip("/").rsplit("/", 1)[-1]
        try:
            html = fetch(url)
        except Exception as exc:
            print(f"  {name:14} FAILED ({exc})")
            continue
        pages[url] = html
        (RAW / f"{name}.html").write_text(html)
        print(f"  {name:14} {len(html):>9,} bytes")

    if not pages:
        print("\n  Could not reach any agenda page.", file=sys.stderr)
        if OUT.exists():
            print(f"  Keeping the existing {OUT.name}.", file=sys.stderr)
            return 0
        return 1

    payload = build(pages)
    problems = validate(payload)

    print("\n" + summarise(payload))

    if problems:
        print("\n  PARSE LOOKS WRONG:", file=sys.stderr)
        for p in problems:
            print(f"    - {p}", file=sys.stderr)
        print(
            "\n  The site's markup has probably changed. Raw HTML is in data/raw/ .\n"
            "  Refusing to overwrite good data with a bad parse.",
            file=sys.stderr,
        )
        return 2

    if args.check:
        print("\n  --check: parse is healthy, nothing written.")
        return 0

    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(OUT)
    print(f"\n  wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
