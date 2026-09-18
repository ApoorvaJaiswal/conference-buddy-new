---
name: build-my-schedule
description: Build a personalised multi-day conference schedule for an attendee. Use when someone asks for a plan, an itinerary, or "what should I go to".
---

# Building a schedule

## Before you start
Read `/AGENTS.md`. If the attendee's role, interests or constraints are unset,
ask one question covering all of them rather than three separate questions.

## Steps
1. Call `agenda_status` first. Tell the attendee up front which days have
   published times. Never present an unscheduled session as if it had a slot.
2. Search per day and per interest. Several narrow searches beat one broad one.
3. Shortlist roughly twice as many sessions as slots, then cut.
4. Run `check_plan` on the shortlist. Fix every clash before writing anything.
5. Write one file per day under `/plan/`, using `templates/day.md` as the shape.
6. Summarise in three lines. The detail lives in the files.

## Rules
- Every recommendation names the session ID and why it fits *this* attendee.
- Every slot gets a named backup.
- Room-to-room travel time is not published. Never claim a transition is
  comfortable or tight; say the distance is unknown.
