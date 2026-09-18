"""Access to the scraped agenda. Null-aware throughout.

Every field here came from the conference website. Where the site does not
publish something, the value is None and callers must say so rather than guess.
"""

import json
from datetime import datetime
from functools import lru_cache

from buddy.config import DATA_FILE


@lru_cache(maxsize=1)
def _load() -> dict:
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"{DATA_FILE} is missing. Run: python scripts/fetch_agenda.py"
        )
    return json.loads(DATA_FILE.read_text())


def reload() -> None:
    _load.cache_clear()


def event() -> dict:
    return _load()["event"]


def caveats() -> list[str]:
    return _load().get("caveats", [])


def fetched_at() -> str:
    return _load().get("fetched_at", "unknown")


def sessions() -> list[dict]:
    return _load()["sessions"]


def scheduled() -> list[dict]:
    return [s for s in sessions() if s.get("scheduled")]


def unscheduled() -> list[dict]:
    return [s for s in sessions() if not s.get("scheduled")]


def days() -> list[str]:
    return sorted({s["day"] for s in sessions() if s.get("day")})


def tracks() -> list[str]:
    return sorted({s["track"] for s in sessions() if s.get("track")})


def stages() -> list[str]:
    return sorted({s["stage"] for s in sessions() if s.get("stage")})


def topics() -> list[str]:
    return sorted({t for s in sessions() for t in s.get("topics", [])})


def by_id(session_id: str) -> dict | None:
    return next((s for s in sessions() if s["id"] == str(session_id)), None)


def to_minutes(hhmm: str) -> int:
    return datetime.strptime(hhmm, "%H:%M").hour * 60 + datetime.strptime(hhmm, "%H:%M").minute


def overlaps(a: dict, b: dict) -> bool:
    """False if either session has no published time. Unknown is not a conflict."""
    if not (a.get("scheduled") and b.get("scheduled")):
        return False
    if a.get("day") != b.get("day") or a.get("day") is None:
        return False
    return (
        to_minutes(a["start"]) < to_minutes(b["end"])
        and to_minutes(b["start"]) < to_minutes(a["end"])
    )


def speaker_names(session: dict) -> str:
    names = [p["name"] for p in session.get("speakers", [])]
    return ", ".join(names) if names else "speakers not published"


def when(session: dict) -> str:
    if not session.get("scheduled"):
        return "time not yet published"
    day = session.get("day") or "day not published"
    stage = session.get("stage") or "stage not published"
    return f"{day} {session['start']}-{session['end']} @ {stage}"


def one_line(session: dict) -> str:
    bits = [f"[{session['id']}]", when(session)]
    if session.get("track"):
        bits.append(f"| {session['track']}")
    if session.get("format"):
        bits.append(f"| {session['format']}")
    title = session.get("title") or "(untitled)"
    if session.get("title_from_slug"):
        title += " (title derived from URL; no detail page found)"
    bits.append(f"| {title} — {speaker_names(session)}")
    return " ".join(bits)
