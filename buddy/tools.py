"""Tools over the real agenda.

Design rules worth saying out loud in the room:

1. Tool results are compact and ID-addressable. search_sessions returns one line
   per hit; the agent pulls detail with get_session only where it matters.

2. Time arithmetic happens in Python, not in the model. check_plan is
   deterministic.

3. A tool that does not know something says so. Large parts of this agenda are
   genuinely unpublished: Friday's conference program is rendered client-side and
   a plain fetch cannot see it, no floor plan exists so nothing here can judge
   whether you can physically make a transition, and no difficulty levels are
   published. None of that is filled in with plausible guesses. "Not published"
   is a real answer and the agent is told to pass it on.
"""

try:
    from langchain.tools import tool
except ImportError:
    from langchain_core.tools import tool

from buddy import data


@tool
def agenda_status() -> str:
    """What this agenda data covers and what it is missing. Call this first.

    Always tell the user about relevant gaps rather than implying full coverage.
    """
    all_s = data.sessions()
    sched = data.scheduled()
    lines = [
        f"Agenda fetched: {data.fetched_at()}",
        f"Sessions known: {len(all_s)} ({len(sched)} with a published time, "
        f"{len(all_s) - len(sched)} without)",
        "Days with published times: " + (", ".join(data.days()) or "none"),
        "",
        "Known gaps and caveats:",
    ]
    lines += [f"  - {c}" for c in data.caveats()]
    return "\n".join(lines)


@tool
def list_program() -> str:
    """List the event, its days, tracks and stages as actually published."""
    ev = data.event()
    return "\n".join(
        [
            f"{ev['name']} — {ev['venue']}, {ev['address']}",
            f"Dates: {', '.join(ev['dates'])}",
            f"Days with published session times: {', '.join(data.days()) or 'none'}",
            f"Tracks: {'; '.join(data.tracks()) or 'none published'}",
            f"Stages: {'; '.join(data.stages()) or 'none published'}",
        ]
    )


@tool
def search_sessions(
    query: str = "",
    day: str = "",
    track: str = "",
    stage: str = "",
    topic: str = "",
    scheduled_only: bool = False,
    limit: int = 12,
) -> str:
    """Search the agenda.

    Args:
        query: keywords matched against title, abstract, topics, speaker and company.
        day: ISO date, one of 2026-09-23, 2026-09-24, 2026-09-25.
        track: exact track name (see list_program).
        stage: exact stage name (see list_program).
        topic: exact topic tag (e.g. "Agentic AI", "LangChain").
        scheduled_only: if true, return only sessions with a published time.
        limit: maximum results.

    Results include sessions whose time is not yet published; those are marked
    "time not yet published". Do not invent times for them.
    """
    terms = [t for t in query.lower().split() if t]
    hits = []
    for s in data.sessions():
        if day and s.get("day") != day:
            continue
        if track and (s.get("track") or "").lower() != track.lower():
            continue
        if stage and (s.get("stage") or "").lower() != stage.lower():
            continue
        if topic and topic.lower() not in [t.lower() for t in s.get("topics", [])]:
            continue
        if scheduled_only and not s.get("scheduled"):
            continue

        haystack = " ".join(
            [
                s.get("title") or "",
                s.get("abstract") or "",
                s.get("track") or "",
                " ".join(s.get("topics", [])),
                " ".join(p.get("name") or "" for p in s.get("speakers", [])),
                " ".join(p.get("company") or "" for p in s.get("speakers", [])),
            ]
        ).lower()

        score = sum(1 for t in terms if t in haystack)
        if terms and score == 0:
            continue
        hits.append((score, s))

    hits.sort(key=lambda h: (-h[0], h[1].get("day") or "9999", h[1].get("start") or "99:99"))
    if not hits:
        return "No sessions matched. Try broader keywords or drop a filter."

    body = "\n".join(data.one_line(s) for _, s in hits[:limit])
    shown = hits[:limit]
    unscheduled = sum(1 for _, s in shown if not s.get("scheduled"))
    if unscheduled:
        body += (
            f"\n\n({unscheduled} of these have no published time yet. "
            "Say so rather than guessing.)"
        )
    return body


@tool
def get_session(session_id: str) -> str:
    """Full detail for one session: abstract, speakers, topics, time if published."""
    s = data.by_id(session_id)
    if not s:
        return f"No session with id {session_id}."

    speakers = (
        "\n".join(
            f"  - {p['name']}"
            + (f", {p['role']}" if p.get("role") else "")
            + (f" at {p['company']}" if p.get("company") else "")
            for p in s["speakers"]
        )
        or "  (not published)"
    )
    parts = [
        s.get("title") or "(untitled)",
        data.when(s),
        f"Track: {s.get('track') or 'not published'}",
        f"Format: {s.get('format') or 'not published'}"
        + (f" ({s['duration_minutes']} min)" if s.get("duration_minutes") else ""),
        f"Topics: {', '.join(s.get('topics', [])) or 'not published'}",
        f"Speakers:\n{speakers}",
        f"Abstract: {s.get('abstract') or 'not published'}",
        f"URL: {s.get('url') or 'not published'}",
    ]
    if s.get("title_from_slug"):
        parts.append(
            "NOTE: this session appears on the schedule but has no detail page, "
            "so the title is derived from its URL."
        )
    return "\n".join(parts)


@tool
def check_plan(session_ids: list[str]) -> str:
    """Check a draft schedule for time clashes.

    Only compares sessions that have published times. Anything unscheduled is
    reported separately as uncheckable rather than assumed fine.

    This cannot tell you whether a transition between two rooms is physically
    possible: the conference publishes no floor plan or walking distances.
    """
    picked, missing, unscheduled = [], [], []
    for sid in session_ids:
        s = data.by_id(sid)
        if not s:
            missing.append(sid)
        elif not s.get("scheduled"):
            unscheduled.append(s)
        else:
            picked.append(s)

    notes = []
    if missing:
        notes.append(f"Unknown session IDs: {', '.join(missing)}")
    for s in unscheduled:
        notes.append(f"NO PUBLISHED TIME, cannot check: [{s['id']}] {s.get('title')}")

    picked.sort(key=lambda s: (s.get("day") or "", data.to_minutes(s["start"])))
    clashes = []
    for i, a in enumerate(picked):
        for b in picked[i + 1:]:
            if data.overlaps(a, b):
                clashes.append(
                    f"CLASH: [{a['id']}] {a['start']}-{a['end']} and "
                    f"[{b['id']}] {b['start']}-{b['end']} on {a['day']}"
                )

    out = []
    if clashes:
        out.append("Clashes:\n" + "\n".join(f"- {c}" for c in clashes))
    else:
        out.append(f"No clashes among the {len(picked)} sessions with published times.")
    if notes:
        out.append("Caveats:\n" + "\n".join(f"- {n}" for n in notes))
    out.append(
        "Room-to-room travel time is not published anywhere, so feasibility of "
        "back-to-back sessions in different rooms is unverified."
    )
    return "\n\n".join(out)


@tool
def refresh_agenda() -> str:
    """Re-fetch the agenda from wearedevelopers.com and reload it.

    Use when the user suspects the data is stale, or after a failure that might
    have been caused by a bad cache. This hits the network and can genuinely
    fail; the failure is returned as text, not raised.
    """
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    try:
        proc = subprocess.run(
            [sys.executable, str(root / "scripts" / "fetch_agenda.py"), "--force"],
            capture_output=True, text=True, timeout=180, cwd=root,
        )
    except subprocess.TimeoutExpired:
        return "Refresh timed out after 180s. The cached agenda is unchanged."

    data.reload()
    if proc.returncode != 0:
        return (
            f"Refresh failed (exit {proc.returncode}). The cached agenda is "
            f"unchanged and still usable.\n{proc.stderr.strip()[-400:]}"
        )
    return f"Agenda refreshed. Now holding {len(data.sessions())} sessions."


AGENDA_TOOLS = [
    agenda_status, list_program, search_sessions, get_session, check_plan,
    refresh_agenda,
]
