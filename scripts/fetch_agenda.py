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
DAY_CACHE = DATA / "day_cache.json"

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

# Explicit calendar dates are far safer section markers than "Day N", which also
# appears in nav, tab labels and body copy. Order matters: longest first.
DATE_MARK = re.compile(
    r"(?:\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s*)?"
    r"(?:(2026-09-2[345])"
    r"|(?:Sep(?:t(?:ember)?)?\.?\s*(2[345]))"
    r"|(?:(2[345])\s*Sep(?:t(?:ember)?)?))",
    re.I,
)
ISO_FOR_DOM = {"23": "2026-09-23", "24": "2026-09-24", "25": "2026-09-25"}

# The date is usually in markup, not in visible text: <time datetime="...">,
# data-date, data-day. Tag stripping threw these away, which is why day
# detection was falling back to guessing from nearby headings.
DATE_ATTR = re.compile(
    r"""(?:datetime|data-date|data-day|data-start|data-start-time|content)\s*=\s*"""
    r"""["']([^"']*2026-09-2[345][^"']*)["']""",
    re.I,
)


# schema.org Event markup, if the site emits it, is the most reliable signal of
# all: an unambiguous ISO date rather than a layout convention we have to infer.
JSONLD_DATE = re.compile(
    r'"(?:startDate|start_date|startTime|date)"\s*:\s*"([^"]*2026-09-2[345][^"]*)"', re.I
)


def _date_from_jsonld(fragment: str) -> str | None:
    m = JSONLD_DATE.search(fragment)
    if m:
        d = re.search(r"2026-09-2[345]", m.group(1))
        if d:
            return d.group(0)
    return None


def _date_from_attrs(fragment: str) -> str | None:
    """Pull an ISO date out of any date-bearing attribute in this fragment."""
    m = DATE_ATTR.search(fragment)
    if m:
        d = re.search(r"2026-09-2[345]", m.group(1))
        if d:
            return d.group(0)
    return None


def _date_marks(html: str) -> list[tuple[int, str]]:
    """Offsets of explicit date markers in the raw HTML, in document order."""
    out = []
    for m in DATE_MARK.finditer(html):
        iso = m.group(1) or ISO_FOR_DOM.get(m.group(2) or m.group(3) or "")
        if iso:
            out.append((m.start(), iso))
    return out


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


def _anchor_texts(html: str) -> dict[str, tuple[str, int, str]]:
    """Schedule page: time, stage and track live INSIDE the anchor text.

    Returns id -> (visible_text, position, raw_row). The raw row keeps the markup
    so date attributes can be read; the visible text is for the human-readable
    fields.
    """
    matches = list(ANCHOR.finditer(html))
    found: dict[str, tuple[str, int, str]] = {}
    for i, m in enumerate(matches):
        sid, text = m.group(1), visible_text(m.group(2))
        # Context either side, so a <time> tag just outside the anchor still
        # counts - but never past a neighbouring row, or a row steals the next
        # row's date. (This exact leak sent a Friday workshop to Wednesday.)
        # In these layouts the date/time markup PRECEDES its link, so look
        # backwards to the previous row and not one character forwards. Looking
        # forward steals the next row's <time> and shifts it a day.
        lo = matches[i - 1].end() if i else 0
        raw = html[max(lo, m.start() - 2000):m.end()]
        if sid not in found or len(text) > len(found[sid][0]):
            found[sid] = (text, m.start(), raw)
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

    Day assignment is the dangerous part. These pages stack several programmes on
    one document, so "the nearest preceding heading" silently mislabels anything
    that appears after an unrelated section - a Day 0 workshop listed below the
    Day 1 programme inherits Day 1.

    So: prefer explicit calendar dates over "Day N" labels, and only accept a
    marker that is reasonably close to the session. When nothing qualifies, the
    day is None. A session with a time but no day is honest; a session on the
    wrong day is not.
    """
    dates = _date_marks(html)
    fallback = sorted(
        (m.start(), DAYS[re.sub(r"\s+", " ", m.group(1)).lower()])
        for m in re.finditer(r"\b(Day\s*[012])\b", html, re.I)
    ) if not dates else []

    marks = dates or fallback
    MAX_DISTANCE = 30_000   # chars; beyond this the marker is a different section

    out: dict[str, dict] = {}
    for sid, (text, pos, raw) in _anchor_texts(html).items():
        times = TIME_RANGE.search(text)
        if not times:
            continue

        # Best evidence first: a date attribute on this row, then a date in the
        # row's own text, then the nearest preceding section marker.
        day = _date_from_jsonld(raw) or _date_from_attrs(raw)
        inline = _date_marks(text) if not day else None
        if day:
            pass
        elif inline:
            day = inline[0][1]
        else:
            prior = [(off, iso) for off, iso in marks if off <= pos]
            day = None
            if prior:
                off, iso = prior[-1]
                if pos - off <= MAX_DISTANCE:
                    day = iso

        stage = STAGE.search(text)
        track = next((t for t in KNOWN_TRACKS if t in text), None)

        try:
            start, end = _to_24h(times.group(1)), _to_24h(times.group(2))
        except ValueError:
            # A single unparseable time must not abort the whole page. Skip the
            # row; it comes through as unscheduled, which the tools handle.
            continue

        out[sid] = {
            "requires_registration": bool(PREREG.search(text)) or None,
            "day": day,
            "start": start,
            "end": end,
            "stage": stage.group(1).strip() if stage else None,
            "track": track,
        }
    return out


def _to_24h(value: str) -> str:
    return datetime.strptime(value.upper().replace(" ", ""), "%I:%M%p").strftime("%H:%M")


# ── assembly and validation ─────────────────────────────────────────────────


def day_from_detail_page(html: str) -> str | None:
    """Find the date on a single session's own page.

    Tried in order of reliability: schema.org JSON-LD, date-bearing attributes,
    then an explicit date in the visible text. A detail page describes exactly one
    session, so there is no neighbouring row to steal a date from - which is what
    makes this the reliable fallback when the grid pages defeat us.
    """
    return (
        _date_from_jsonld(html)
        or _date_from_attrs(html)
        or (lambda m: m[0][1] if m else None)(_date_marks(visible_text(html)))
    )


DAY_CACHE_MAX_AGE_DAYS = 7


def _load_day_cache() -> dict[str, str]:
    """Cached id -> date, ignored once stale.

    Dates are stable, but not guaranteed: an organiser can move a session. An
    expiry means a cache committed to the repo cannot quietly serve a wrong date
    for the rest of the event.
    """
    try:
        blob = json.loads(DAY_CACHE.read_text())
        stamp = datetime.fromisoformat(blob["updated"])
        age = (datetime.now(timezone.utc) - stamp).days
        if age > DAY_CACHE_MAX_AGE_DAYS:
            print(f"  day cache is {age} days old; refetching dates")
            return {}
        return blob.get("days", {})
    except Exception:
        return {}


def _save_day_cache(days: dict[str, str]) -> None:
    DAY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DAY_CACHE.write_text(
        json.dumps(
            {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "days": days},
            indent=2,
        )
        + "\n"
    )


def resolve_days_from_details(records: list[dict], refresh: bool = False,
                              workers: int = 8) -> int:
    """Authoritative day for each session, from its own detail page.

    The grid pages do not carry a reliable per-row date; detail pages do, because
    each describes exactly one session. So this is the primary source of truth for
    dates, not a fallback.

    It is cached in data/day_cache.json and fetched concurrently, so the cost is
    paid once (at container build, baked into a prebuild) rather than on every
    refresh. Session dates do not move; new sessions are picked up automatically
    because only ids missing from the cache are fetched.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cache = {} if refresh else _load_day_cache()

    # Apply what we already know, for free.
    from_cache = 0
    todo = []
    for rec in records:
        cached = cache.get(rec["id"])
        if cached:
            rec["day"] = cached
            rec["day_source"] = "detail-page (cached)"
            from_cache += 1
        elif rec.get("url"):
            todo.append(rec)

    if from_cache:
        print(f"  {from_cache} session dates from cache")
    if not todo:
        return from_cache

    print(f"  fetching {len(todo)} new session dates ({workers} at a time)...")

    def one(rec):
        try:
            return rec, day_from_detail_page(fetch(rec["url"], timeout=20))
        except Exception:
            return rec, None

    fixed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, r) for r in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            rec, day = fut.result()
            if day:
                rec["day"] = day
                rec["day_source"] = "detail-page"
                cache[rec["id"]] = day
                fixed += 1
            if i % 50 == 0 or i == len(todo):
                print(f"    {i}/{len(todo)} ({fixed} resolved)")

    _save_day_cache(cache)
    print(f"  cached {len(cache)} dates in {DAY_CACHE.name}; "
          f"future runs will not refetch these")
    return from_cache + fixed


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
    conflicts: set[str] = set()
    for url in GRID_PAGES:
        html = pages.get(url)
        if not html:
            continue
        for sid, slot in parse_schedule_page(html).items():
            if sid not in times:
                times[sid] = slot
                continue
            seen, new = times[sid].get("day"), slot.get("day")
            if seen and new and seen != new:
                # Two pages disagree about which day this runs. Neither is
                # trustworthy, so record none and say so.
                conflicts.add(sid)
                times[sid]["day"] = None
                slot = {k: v for k, v in slot.items() if k != "day"}
            merge(times[sid], slot)
    for sid in conflicts:
        times[sid]["day"] = None

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
                "day_conflict": sid in conflicts,
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
            "A session with a time but no day means the source pages disagreed or "
            "gave no reliable date marker. It is reported as unknown rather than "
            "guessed.",
        ],
        "sessions": records,
    }


def validate(payload: dict) -> list[str]:
    """Gates that must pass before this is allowed to replace a good data file.

    Must never raise: it runs on exactly the malformed input it exists to catch,
    so every field access here is defensive.
    """
    sessions = payload.get("sessions") or []
    problems = []

    if len(sessions) < 40:
        problems.append(f"only {len(sessions)} sessions parsed (expected 40+)")

    titled = [s for s in sessions if s.get("title")]
    if sessions and len(titled) < len(sessions) * 0.8:
        problems.append(f"only {len(titled)}/{len(sessions)} sessions got a title")

    scheduled = [s for s in sessions if s.get("scheduled")]
    if len(scheduled) < 20:
        problems.append(f"only {len(scheduled)} sessions have times (expected 20+)")

    if not any(s.get("speakers") for s in sessions):
        problems.append("no speakers parsed on any session")

    dated = [s for s in sessions if s.get("day")]
    if len(sessions) >= 40 and dated:
        counts: dict[str, int] = {}
        for s in dated:
            counts[s["day"]] = counts.get(s["day"], 0) + 1
        spread = sorted(counts)
        breakdown = ", ".join(f"{d}: {counts[d]}" for d in spread)

        if len(spread) < 2:
            problems.append(
                f"every dated session landed on {spread[0]} - day detection is wrong "
                f"({breakdown})"
            )
        elif max(counts.values()) > len(dated) * 0.9:
            problems.append(
                f"over 90% of sessions on one day - day detection is suspect ({breakdown})"
            )

    undated = [s for s in sessions if s.get("scheduled") and not s.get("day")]
    if undated and len(sessions) >= 40:
        problems.append(
            f"{len(undated)} sessions have a time but no day; the site publishes a day "
            f"for every session, so this is a parser bug. Investigate with: "
            f"python scripts/inspect_session.py {undated[0].get('id')}"
        )

    bad_times = [
        s for s in scheduled
        if not re.fullmatch(r"\d{2}:\d{2}", s.get("start") or "")
        or not re.fullmatch(r"\d{2}:\d{2}", s.get("end") or "")
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
    undated = [s for s in sessions if s.get("scheduled") and not s.get("day")]
    lines.append(f"  timed but no day: {len(undated)}")
    if undated:
        lines.append("    ^ the site publishes a day for every session, so any number")
        lines.append("      here means the parser missed it. Run:")
        lines.append(f"        python scripts/inspect_session.py {undated[0]['id']}")
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
    ap.add_argument("--refresh-days", action="store_true",
                    help="ignore data/day_cache.json and refetch every session date")
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

    # The grid pages do not carry a reliable per-row date: rows inherit whatever
    # section heading happens to sit above them. Detail pages do carry it, one
    # session per page, so they are the source of truth. Cached, so this costs
    # nothing after the first run.
    if not args.offline:
        print("\n  resolving session dates (detail pages are authoritative)")
        for rec in payload["sessions"]:
            # Drop the grid's guess; a cached or freshly fetched date replaces it.
            if rec.get("day_source") != "detail-page":
                rec["day"] = None
        resolve_days_from_details(payload["sessions"], refresh=args.refresh_days)
        payload["sessions"].sort(
            key=lambda r: (r["day"] or "9999", r["start"] or "99:99", r["stage"] or "~")
        )
        problems = validate(payload)

    print("\n" + summarise(payload))

    if problems:
        print("\n  PARSE LOOKS WRONG:", file=sys.stderr)
        for p in problems:
            print(f"    - {p}", file=sys.stderr)
        print("\n  The site's markup has probably changed. Raw HTML is in data/raw/ .",
              file=sys.stderr)

        if OUT.exists():
            print("  Keeping the existing agenda rather than overwriting it with this.",
                  file=sys.stderr)
            return 2

        # No cache to fall back on. Writing nothing means no workshop at all, so
        # write it and mark it suspect - the tools tell users the data may be wrong.
        print("  No cached agenda exists, so writing this one marked SUSPECT.\n"
              "  The buddy will warn users that its data may be wrong.", file=sys.stderr)
        payload["parse_health"] = "suspect"
        payload["parse_problems"] = problems
        payload["caveats"].insert(
            0,
            "THIS AGENDA MAY BE WRONG. The scrape failed its own sanity checks: "
            + "; ".join(problems)
            + ". Tell the user this before relying on any time or day.",
        )
    else:
        payload["parse_health"] = "ok"
        payload["parse_problems"] = []

    if args.check:
        print("\n  --check: nothing written. "
              f"parse_health={payload.get('parse_health', 'ok')}")
        return 2 if problems else 0

    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(OUT)
    print(f"\n  wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
