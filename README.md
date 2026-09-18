# Conference Buddy — a deepagents workshop

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/YOUR-ORG/wad-conference-buddy?quickstart=1)

Build an agent that plans your three days at WeAreDevelopers World Congress North
America 2026, using the actual agenda, in four executable sections.

**Open [`conference_buddy.ipynb`](conference_buddy.ipynb).** That's the workshop.

| Section | Adds | deepagents surface |
|---|---|---|
| 0 | setup + smoke test | `create_deep_agent` |
| 1 | the real agenda, and a tool you write | `tools=` |
| 2 | a plan that persists | `backend=`, `TodoListMiddleware` |
| 3 | research → analysis → synthesis | `subagents=` |
| 4 | memory and approval gates | `memory=`, `interrupt_on=`, `checkpointer=` |
| 5 | skills | `skills=`, `SKILL.md` |
| 6 | tools you did not write | MCP |

Roughly 100 minutes of material in a 120-minute slot. Nothing is left as an
exercise: every cell is run in the room.

**Every section runs directly after section 0.** Each one re-imports what it
needs, so you can skip any section, run them out of order, or recover from a dead
kernel by running section 0 plus wherever you are. Verified by static analysis,
not by assertion — section 1 defines `AGENDA_TOOLS`, but section 8 imports it
again rather than assuming you got there in order.

## Setup

**GitHub Codespaces (recommended for the workshop).** Click the badge above.
GitHub asks for your API key on the create screen — it becomes a Codespace secret,
so the notebook never prompts. Dependencies and the dataset are installed during
container creation. Open `conference_buddy.ipynb` and run the cells — the kernel is
selected automatically.

Attendees who leave the key blank aren't stuck; the notebook falls back to a
`getpass` prompt.

**Colab / hosted:** open the notebook, run the first two cells. The bootstrap
clones this repo and prompts for your API key with `getpass`. Nothing else needed.
Update the clone URL in the bootstrap cell before you publish.

**Local:**

```bash
git clone <this repo> && cd wad-conference-buddy
uv venv && source .venv/bin/activate
uv pip install -e . jupyterlab
cp .env.example .env        # add your API key
python scripts/fetch_agenda.py
jupyter lab conference_buddy.ipynb
```

Any provider works — set `BUDDY_MODEL` in `.env` as `provider:model-id`
(`anthropic`, `openai`, `google_genai`, `ollama`). Defaults to
`anthropic:claude-sonnet-4-6`. Look the model id up in your provider's current
docs rather than copying one from a tutorial; they change often.

## Repo layout

```
.devcontainer/            Codespaces: image, secrets, extensions
  on-create.sh              slow setup — baked into prebuilds
  post-create.sh            fast per-codespace checks
conference_buddy.ipynb    the workshop
buddy/data.py             dataset access (imported, not taught)
buddy/nb.py               display helpers: run(), show_workspace(), show_todos()
data/                     scraped agenda lands here (gitignored)
seed/AGENTS.md            starting memory file for section 4
seed/skills/              SKILL.md files for section 7, copied into workspace/
workspace/                where the agent writes (gitignored)
scripts/build_notebook.py regenerates the notebook — edit here, not the .ipynb
scripts/fetch_agenda.py   scrapes the real agenda (runs at container start)
tests/fixture.py          structural fixture for testing the parser offline
```

The tools are defined **inside the notebook**, not imported. Tool design is one of
the lessons, so attendees need to see and edit them. `buddy/data.py` holds only
the boring JSON access.

### Editing the notebook

Edit `scripts/build_notebook.py` and re-run it. Keeps diffs readable and avoids
committing execution counts and stale outputs. Commit both files.

## Data

There is no dataset in this repo. `scripts/fetch_agenda.py` pulls the real agenda
from wearedevelopers.com at container creation, and the notebook refreshes it if
the cache is over 12 hours old.

```bash
python scripts/fetch_agenda.py            # refresh if stale
python scripts/fetch_agenda.py --force    # always refetch
python scripts/fetch_agenda.py --check    # parse and report, write nothing
python scripts/fetch_agenda.py --offline  # use cache only, never hit the network
```

The notebook refetches on **every run** (`--force`), because the program is still
being finalised and a cache from this morning is already suspect. It falls back to
the cache when the network is down.

Six pages are read and joined on the numeric session ID:

| Page | Gives |
|---|---|
| `/agenda/sessions` | title, speakers, abstract, topics, format |
| `/agenda/workshops` | workshop cards *and* their grid slots |
| `/agenda/masterclasses` | masterclass cards and slots |
| `/agenda/activities` | side events and slots |
| `/agenda/docker`, `/agenda/github` | partner program cards |
| `/agenda/schedule` | day, start, end, stage, track |

Card pages supply detail, grid pages supply times, and the first page publishing a
real value wins. A page that fails to fetch is skipped rather than aborting the run,
and `sources` in the output records exactly which pages were actually read.

**Coverage is not guaranteed.** The sessions page describes itself as an evolving
preview, and Friday's conference program did not appear in any page fetched as of
writing. Run `python scripts/diagnose_schedule.py` to see where the remaining data
lives — it checks whether the other days are embedded in script payloads or behind
an API call.

**Nothing is invented.** Where the site doesn't publish a field it stays `None`
and the tools report "not published". Three gaps are real and permanent until the
organisers change something:

- Friday's conference program renders client-side; a plain fetch can't see it.
  Those sessions arrive with `scheduled: false`.
- No floor plan or walking distances are published anywhere, so nothing can judge
  whether a room-to-room transition is physically possible. There is no
  walk-time tool.
- No difficulty levels are published, so there is no level filter.

If the site's markup changes, the fetcher's validation gates (session count,
title coverage, scheduled count, time format) fail loudly, refuse to overwrite a
good cache, and leave the raw HTML in `data/raw/` for you to inspect.

## Verifying the repo

```bash
python tests/verify.py
```

50 mechanical checks across four areas: nothing fabricated is committed, every
cell parses and every section is independent, every deepagents/langchain symbol
and keyword matches the installed library, and the notebook covers what the
abstract promises. Exits non-zero on failure, so it belongs in CI.

It does **not** check three things, and says so when it runs: the live site (the
parser is verified against `tests/fixture.py` only), any model call (no API key,
so agents are verified to construct, not to answer well), and VS Code extension
installation in a cold codespace. Those need:

```bash
python scripts/fetch_agenda.py --check    # parses the live site, writes nothing
python scripts/diagnose_schedule.py       # where the unreachable days live
```

## Facilitator notes

**Clear the outputs before you ship it.**
`jupyter nbconvert --clear-output --inplace conference_buddy.ipynb`
Attendees should watch their own agent think, not read yours.

**If a codespace opens without Python or Jupyter,** the container was built
before `.devcontainer/` reached the repo. Extensions, dependencies and settings
are applied only at container creation. Fix with Command Palette → *Codespaces:
Rebuild Container*, or just delete and recreate. The welcome banner in the
terminal is the tell: no banner means the config never ran.

**Slow setup lives in `onCreateCommand`, not `postCreateCommand`.** Only the
former is baked into prebuild images; the latter reruns for every codespace even
when restored from a prebuild. Putting `pip install` in the wrong one makes
prebuilds pointless. If you add dependencies, add them to `on-create.sh`.

**Turn on prebuilds before the session.** Settings → Codespaces → Prebuild
configuration, targeting `main` on the 2-core machine type. Without it every
attendee waits two to three minutes for `pip install` while you talk. With it a
codespace opens in about twenty seconds. Set this up the day before, not the
morning of — the first prebuild takes a while to bake.

**Have a finished run in a second window.** Section 2 is the slow cell — it plans
three days for real. Talk over it using pre-run output rather than watching a
progress spinner with sixty people.

**The moments that land.** Section 1: `agenda_status` shows the agent's blind
spots before it says a word, then the clash cell finds a real overlap in the live
schedule rather than a rehearsed one. Section 3: two `task` calls dispatched in
one turn. Section 4: reject the message and watch it recover.

**Run `--check` the morning of.** The scraper reads a live site that is still
being updated. `python scripts/fetch_agenda.py --check` parses and reports without
writing, so you know before the room does.

**Pin your versions.** Task planning became opt-in in deepagents 0.7. On anything
older `write_todos` appears without `TodoListMiddleware` and section 2 makes no
sense. `uv pip freeze > requirements.lock` once it works.

**Restarting mid-workshop.** Anyone whose kernel dies re-runs section 0 and their
current section — every agent cell is self-contained. `nb.reset_workspace()`
clears the agent's files.

**No wifi plan.** Everything except the model call is local. `BUDDY_MODEL=ollama:...`
keeps it running fully offline, though the plans get noticeably worse.

## Where to go next

Didn't fit in ninety minutes, worth an afternoon:

- **Skills** — `skills=["./skills/"]`, one `SKILL.md` per repeatable procedure
  with templates alongside. The first thing I'd add back.
- **MCP** — swap the stubbed `add_to_calendar` for a real calendar server.
- **Tracing** — `LANGSMITH_TRACING=true`, then re-run section 3 and see where the
  subagents actually spent their tokens.
- **Async subagents** — the scouts block the supervisor. Wrong shape for a buddy
  that keeps working while you're in a talk.
