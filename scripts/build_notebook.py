"""Builds conference_buddy.ipynb.

Kept as a generator so the notebook stays diffable and regenerable. Edit here,
run `python scripts/build_notebook.py`, commit both.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CELLS = []


def md(text: str):
    CELLS.append(
        {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)}
    )


def code(text: str):
    CELLS.append(
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": text.strip("\n").splitlines(True),
        }
    )


# ───────────────────────────── Intro ─────────────────────────────

md("""
# Conference Buddy

### Building agents with `deepagents` — WeAreDevelopers World Congress North America 2026

You are going to build an agent that plans your three days at this conference,
using the actual agenda, in four steps.

| | Adds | The one thing it teaches |
|---|---|---|
| **1** | The agenda | `tools=` — and how to shape what a tool returns |
| **2** | A plan that persists | `backend=` and `TodoListMiddleware` |
| **3** | Specialist scouts | `subagents=` and context isolation |
| **4** | Trust | `memory=` and `interrupt_on=` |

Run the cells in order. Each section works on its own and each one ends with a
cell for you to break things in.

**The conference:** Sept 23–25 2026, San Jose McEnery Convention Center.
Day 0 is workshops and check-in, Day 1 adds the main program and the party,
Day 2 runs through the closing keynote.
""")

md("""
---
## 0. Setup

**In Codespaces:** dependencies and the dataset are already installed. Pick the
kernel *Conference Buddy (Python 3.11)* in the top right, then run the two cells
below — the first will detect the existing install and skip.

**Anywhere else:** run both cells. You'll be prompted for an API key if one isn't
already in your environment.

If the third cell prints a sentence about agent harnesses, you're ready.
""")

code("""
# In Codespaces this is already done — the cell detects that and skips.
try:
    import deepagents, langchain
    print("Dependencies already installed. Skipping.")
except ImportError:
    %pip install -q "deepagents>=0.7" "langchain>=1.0" "langchain-anthropic>=1.0" python-dotenv
    print("Installed. If imports fail below, restart the kernel and re-run.")

# Different provider? Add one of:
#   langchain-openai        langchain-google-genai        langchain-ollama
""")

code("""
import json, os, sys, subprocess
from pathlib import Path

IN_CODESPACES = os.environ.get("CODESPACES") == "true"

# Get the workshop package + dataset. In Codespaces and local clones this is a
# no-op; in Colab it fetches the repo.
if not Path("buddy").exists():
    subprocess.run(
        ["git", "clone", "--depth", "1",
         "https://github.com/YOUR-ORG/wad-conference-buddy.git", "_repo"],
        check=True,
    )
    for item in Path("_repo").iterdir():
        if item.name != ".git":
            item.rename(Path(item.name))

sys.path.insert(0, ".")

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

# Pick your model. Any provider works.
MODEL = os.environ.get("BUDDY_MODEL", "anthropic:claude-sonnet-4-6")

KEY_FOR = {
    "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
    "google_genai": "GOOGLE_API_KEY", "openrouter": "OPENROUTER_API_KEY",
}
key_name = KEY_FOR.get(MODEL.split(":")[0])
if key_name and not os.environ.get(key_name):
    # Codespace secrets and .env files land in os.environ, so we only reach
    # this prompt if neither was set.
    from getpass import getpass
    os.environ[key_name] = getpass(f"{key_name}: ")

# Pull the real agenda fresh from wearedevelopers.com every run. The program is
# still being finalised, so a cached copy from this morning is already suspect.
# Falls back to the cache if the network is unavailable.
subprocess.run([sys.executable, "scripts/fetch_agenda.py", "--force"], check=False)

from buddy import data, nb
data.reload()
nb.reset_workspace()

print(f"Environment: {'GitHub Codespaces' if IN_CODESPACES else 'local / hosted'}")
print(f"Model:       {MODEL}")
print(f"Agenda from: {data.fetched_at()}")
print(f"Sessions:    {len(data.sessions())} "
      f"({len(data.scheduled())} with a published time, "
      f"{len(data.unscheduled())} without)")
print(f"Days:        {', '.join(data.days()) or 'none'}")
print(f"Tracks:      {len(data.tracks())}   Stages: {len(data.stages())}")
print("Pages read:")
for src in json.loads(open("data/sessions.json").read())["sources"]:
    print(f"  {src}")
""")

code("""
from deepagents import create_deep_agent

smoke = create_deep_agent(model=MODEL, system_prompt="Be brief.")
nb.run(smoke, "In one sentence: what is an agent harness?")
""")

# ───────────────────────────── Step 1 ─────────────────────────────

md("""
---
# 1. Give it the agenda  ·  ~15 min

An agent with no tools is a chatbot with opinions about a conference it has never
heard of. Five functions fix that.

The agenda is **scraped live from wearedevelopers.com** by `scripts/fetch_agenda.py`.
Nothing in it is invented, which turns out to be the more interesting constraint.

Three rules are baked into `buddy/tools.py`:

1. **Compact and ID-addressable.** `search_sessions` returns one line per hit. The
   agent pulls detail with `get_session` only where it matters. Returning
   everything on every search is the fastest way to burn a context window.

2. **Arithmetic in Python, not in the model.** `check_plan` is deterministic.
   Models are bad at *"does 13:15-15:15 overlap 14:50-15:20"* and they are
   **confidently** bad at it.

3. **A tool that doesn't know says so.** This is the one worth dwelling on. Real
   chunks of this agenda are unpublished: Friday's conference program is rendered
   client-side and a plain fetch can't see it, there's no floor plan anywhere so
   nothing can tell you whether you can physically get from Stage 9 to Mainstage
   in five minutes, and no difficulty levels exist. None of that gets filled in
   with something plausible. `"time not yet published"` is a real answer, and the
   system prompt tells the agent to pass it on rather than smooth it over.

The third rule is the one people skip. An agent is only as honest as its tools.
""")

code("""
# The tools live in buddy/tools.py so there is exactly one copy of them.
# Open that file alongside this notebook - it is short, and it is the lesson.
from buddy.tools import (
    AGENDA_TOOLS,        # all five
    agenda_status, list_program, search_sessions, get_session, check_plan,
)

import inspect
print(inspect.getsource(check_plan.func))
""")

md("""
### Look at what you actually have before you spend a token

Tools are ordinary functions. Debug them without the model in the loop - faster,
free, and it shows you what the agent is really working with.

Start with the gaps, because they shape everything downstream:
""")

code("""
print(agenda_status.invoke({}))
""")

code("""
# A real clash from the real schedule - found, not asserted.
from itertools import combinations
from buddy import data

clashes = [(a, b) for a, b in combinations(data.scheduled(), 2) if data.overlaps(a, b)]
print(f"{len(clashes)} overlapping pairs in the published schedule\\n")

if clashes:
    a, b = clashes[0]
    print(check_plan.invoke({"session_ids": [a["id"], b["id"]]}))
else:
    print("No overlaps found - check that the agenda actually loaded.")
""")

code("""
print(search_sessions.invoke({"query": "agents security", "limit": 6}))
""")

md("""
The program is not all 30-minute talks. Workshops, masterclasses, start-up
presentations and side events are separate formats, scraped from their own pages,
and most workshops need **pre-registration** - turning up on the day is not
enough. The tools surface both, because an itinerary that sends someone to a full
workshop they cannot enter is worse than no itinerary.
""")

code("""
print(list_program.invoke({}).splitlines()[-1])        # which formats exist
print()
print(search_sessions.invoke({"session_format": "Workshop", "limit": 6}))
""")

md("""
### A sixth tool, built the same way

You have read five tools. Here is a sixth, so the pattern is concrete rather than
described. `find_speaker` takes a name and returns every session that person is on.

Two details carry the whole lesson. It returns compact lines rather than full
records, so the agent can scan many results cheaply. And it returns a plain
"no sessions found" rather than an empty string, because a tool that returns
nothing looks like a broken tool to a model.
""")

code("""
from langchain.tools import tool
from buddy import data

@tool
def find_speaker(name: str) -> str:
    '''Find every session a given speaker appears on. Partial names are fine.'''
    needle = name.lower().strip()
    hits = [
        s for s in data.sessions()
        if any(needle in (p.get("name") or "").lower() for p in s.get("speakers", []))
    ]
    if not hits:
        return f"No sessions found for a speaker matching {name!r}."
    return chr(10).join(data.one_line(s) for s in hits)


# Tools are ordinary functions. Test it before handing it to a model.
print(find_speaker.invoke({"name": "Cavage"}))
""")

md("""
Hand it to the agent and watch whether it prefers your specific tool over the
general `search_sessions`. If a docstring is vague, the model ignores the tool.
""")

code("""
scout = create_deep_agent(
    model=MODEL,
    tools=AGENDA_TOOLS + [find_speaker],
    system_prompt="You are a conference buddy. Use the most specific tool available.",
)
nb.run(scout, "What is Mark Cavage speaking about?")
""")

md("""
Note what `check_plan` refuses to tell you: whether you can physically make the
transition. No floor plan is published, so it says so instead of estimating.

Now hand the tools to an agent:
""")

code("""
SYSTEM_PROMPT = \"\"\"You are a conference buddy for WeAreDevelopers World Congress
North America 2026 in San Jose.

You help one attendee get the most out of three days. Ground every answer in the
agenda tools rather than guessing. If something isn't in the tools, say so.

When you recommend sessions, give the ID, the time, the stage, and one line on why
it fits this particular person. Never recommend two sessions that clash without
saying which one you'd drop.\"\"\"

buddy_v1 = create_deep_agent(
    model=MODEL,
    tools=AGENDA_TOOLS,
    system_prompt=SYSTEM_PROMPT,
)

nb.run(buddy_v1,
    "I'm a backend engineer who just started putting agents in production. "
    "What are the three most useful talks for me on Thursday?")
""")

md("""
**Watch the trace.** It orients with `list_program`, narrows with `search_sessions`,
then pulls detail on only the few it shortlisted. That progression is what the
compact-return rule buys you.
""")

# ───────────────────────────── Step 2 ─────────────────────────────

md("""
---
# 2. Make it plan, and make the plan survive  ·  ~15 min

Two new arguments, one line each.

```python
backend=FilesystemBackend(...)      # the agent's files land in ./workspace, on disk
middleware=[TodoListMiddleware()]   # the agent gets a write_todos tool
```

**Planning is opt-in now.** In `deepagents` 0.7 task planning stopped being on by
default. Older tutorials show `write_todos` appearing for free; it doesn't
anymore. Fair warning about a library moving this fast — pin your versions.

**Why it matters here.** *"Plan my three days"* isn't one question. It's ten
searches, a conflict check, and three files. Without todos the model tends to
answer the first third thoroughly and then drift.
""")

code("""
# Standalone: this section needs only section 0 to have run.
from deepagents import create_deep_agent
from buddy.tools import (AGENDA_TOOLS, agenda_status, list_program,
                         search_sessions, get_session, check_plan)
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import TodoListMiddleware

PLANNER_PROMPT = \"\"\"You are a conference buddy for WeAreDevelopers World Congress
North America 2026 (Sept 23-25, San Jose McEnery Convention Center).

You have a filesystem. Use it as working memory, not just as output:

  /profile.md    what you know about this attendee
  /plan/day1.md  Wednesday Sept 23
  /plan/day2.md  Thursday Sept 24
  /plan/day3.md  Friday Sept 25
  /notes/        anything they tell you during the event

Before answering anything about the attendee, check whether /profile.md exists and
read it. When you learn something durable about them, write it there.

When you build a schedule:
  1. Break the work into todos first.
  2. Search per day and per interest, not in one giant query.
  3. Run check_plan on your picks before writing anything down.
  4. Write one file per day. Each entry: time, ID, title, stage, one line on why it
     fits, and a named backup session for that slot.
  5. Only then summarise for the user, briefly. The detail lives in the files.\"\"\"

buddy_v2 = create_deep_agent(
    model=MODEL,
    tools=AGENDA_TOOLS,
    system_prompt=PLANNER_PROMPT,
    backend=FilesystemBackend(root_dir="workspace", virtual_mode=True),
    middleware=[TodoListMiddleware()],
)
print("built")
""")

md("""
This next cell is the slow one — it's doing real work across three days.
Good moment to look at the `workspace/` folder in the file browser while it runs.
""")

code("""
state = nb.run(buddy_v2,
    "I'm a senior backend engineer at a mid-size fintech. We're about to put our "
    "first agentic feature in front of customers and I'm nervous about evals and "
    "security. I'd rather go deep than broad, I hate crowds, and I'm going to the "
    "party on Thursday so Friday morning should be gentle. "
    "Build me a plan for all three days.",
    show_tool_results=False)
""")

code("""
nb.show_todos(state)
""")

code("""
nb.show_workspace()
""")

md("""
Those files are on disk. Re-run the agent cell with a follow-up — *"actually I'll
skip Wednesday entirely"* — and it reads what it wrote before instead of starting
over.
""")

# ───────────────────────────── Step 3 ─────────────────────────────

md("""
---
# 3. Delegate to specialists  ·  ~15 min

A subagent is a plain dict. It gets its own context window, its own system prompt,
and its own subset of tools. The supervisor calls it through the built-in `task`
tool and only ever sees its **final message**.

**Why this matters:** the session scout burns twenty tool results narrowing down a
track. Without isolation all twenty land in the supervisor's context and stay
there for the rest of the conversation. With it, the supervisor gets back six
lines. That's the difference between an agent that stays sharp over ninety minutes
and one that gets progressively vaguer.

**Note the tool split.** `speaker-scout` doesn't get `check_plan` — it has no
business building schedules. Giving each subagent the smallest useful toolset is
most of what makes them reliable.
""")

code("""
# Standalone: this section needs only section 0 to have run.
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import TodoListMiddleware
from buddy.tools import (AGENDA_TOOLS, agenda_status, list_program,
                         search_sessions, get_session, check_plan)

session_scout = {
    "name": "session-scout",
    "description": (
        "Finds and shortlists sessions for one day or one topic. Give it the "
        "attendee's interests and constraints. Returns a ranked shortlist with IDs, "
        "times and reasons. Use this instead of searching the agenda yourself."
    ),
    "system_prompt": \"\"\"You find sessions. You are thorough where the supervisor
cannot afford to be: search several phrasings, check adjacent tracks, pull detail on
anything promising.

Return at most eight sessions. For each: ID, day, time, stage, title, and one
sentence on why it fits. Add a short 'skipped' line naming anything obvious you
deliberately left out and why.

Your final message is the only thing the supervisor sees. Do not describe your
search process. Just report the shortlist.\"\"\",
    "tools": [list_program, search_sessions, get_session],
}

fit_analyst = {
    "name": "fit-analyst",
    "description": (
        "Takes a shortlist of session IDs plus what you know about the attendee "
        "and returns a ranked verdict: keep, maybe, drop, with a reason each. "
        "Give it candidates; it does not search."
    ),
    "system_prompt": '''You judge fit. You are given candidate sessions and an
attendee profile. For each candidate return KEEP, MAYBE or DROP with one sentence
of reasoning tied to that specific attendee.

Pull detail with get_session when a title is not enough to judge.

Flag anything with no published time as UNSCHEDULED; it cannot be planned around
yet. Do not invent a slot for it.

Rank the KEEPs. Your final message is the only thing the supervisor sees.''',
    "tools": [get_session],
}

brief_writer = {
    "name": "brief-writer",
    "description": (
        "Turns decided sessions into the written day files under /plan/. Give it "
        "the final picks and the reasoning; it writes, it does not decide."
    ),
    "system_prompt": '''You write the plan files. You are given final picks with
reasoning. Write one file per day under /plan/ .

Each entry: time, session ID, title, stage, one line on why it fits, and a named
backup for that slot. Add a short section listing anything relevant that has no
published time yet.

Never add a session that was not given to you. Never state a travel time between
rooms; that data does not exist.

Report back only which files you wrote.''',
    "tools": [get_session],
}

SUPERVISOR_PROMPT = \"\"\"You are the conference buddy for WeAreDevelopers World Congress
North America 2026. You coordinate; you do not do the digging yourself.

Delegate agenda research to session-scout, one task per day or per theme, and launch
them together when they are independent. Delegate venue and timing questions to
speaker-scout.

You keep: the attendee's profile, the final decisions, conflict checking via
check_plan, and the files under /plan/ and /profile.md.

Never write a schedule you have not run through check_plan.\"\"\"

buddy_v3 = create_deep_agent(
    model=MODEL,
    tools=[list_program, check_plan],          # the supervisor's own toolset is tiny
    system_prompt=SUPERVISOR_PROMPT,
    subagents=[session_scout, fit_analyst, brief_writer],
    backend=FilesystemBackend(root_dir="workspace", virtual_mode=True),
    middleware=[TodoListMiddleware()],
)
print("built")
""")

code("""
nb.run(buddy_v3,
    "I lead a platform team. I want Thursday and Friday planned around agent "
    "governance, security and delivery pipelines. Keep my afternoons lighter, and "
    "tell me how tight each transition is.",
    show_tool_results=False)
""")

md("""
**Look for two `task` calls in a single turn.** Independent subagents run
concurrently. Also notice how little comes back from each one relative to the work
it did.
""")

# ───────────────────────────── Step 4 ─────────────────────────────

md("""
---
# 4. It remembers you, and it asks before it acts  ·  ~15 min

Two parameters, and one loop you have to write yourself.

```python
memory=["/AGENTS.md"]   # always in context, and the agent can edit it
interrupt_on={...}      # pause before these tools and hand control back
```

`memory` is different from the files in section 2: those are read on demand, this
is present on every single turn. Keep it a profile, not a transcript.

**These two belong together.** Memory is what lets the agent stop asking you the
same questions. Approvals are what stop it acting on those assumptions
unsupervised. An agent with memory and no gates is the one that emails your CTO at
2am.

**Note the asymmetry.** `search_sessions` isn't gated — reading is cheap and
reversible. `send_message` contacts a human being and can't be undone. Gate on
consequences, not on how impressive the tool sounds.
""")

code("""
# Standalone: this section needs only section 0 to have run.
from langchain.tools import tool
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import TodoListMiddleware
from buddy.tools import (AGENDA_TOOLS, agenda_status, list_program,
                         search_sessions, get_session, check_plan)
import shutil
from pathlib import Path

# Tools with real-world consequences (stubbed here, but pretend they aren't).
@tool
def send_message(to: str, body: str) -> str:
    \"\"\"Send a networking message to an attendee or speaker. Cannot be undone.\"\"\"
    return f"Message sent to {to}."


@tool
def add_to_calendar(session_ids: list[str]) -> str:
    \"\"\"Write the given sessions into the user's real calendar.\"\"\"
    titles = [data.by_id(s)["title"] for s in session_ids if data.by_id(s)]
    return f"Added {len(titles)} events: {'; '.join(titles)}"


# memory= expects the file to exist in the backend before the agent is built.
Path("workspace").mkdir(exist_ok=True)
if not Path("workspace/AGENTS.md").exists():
    shutil.copy("seed/AGENTS.md", "workspace/AGENTS.md")

print(Path("workspace/AGENTS.md").read_text())
""")

code("""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

TRUSTED_PROMPT = \"\"\"You are the conference buddy for WeAreDevelopers World Congress
North America 2026 in San Jose.

/AGENTS.md holds what you know about this attendee and is always in your context.
When you learn something durable about them — role, interests, constraints,
preferences — update that file with edit_file. Keep it tight; it loads on every run,
so it should be a profile, not a transcript. Transient things go in /notes/ instead.

You can contact people on the attendee's behalf. Draft the message and let the
approval step show it to them. Write like the attendee would: specific, short, and
referencing something real from the session.\"\"\"

buddy_v4 = create_deep_agent(
    model=MODEL,
    tools=AGENDA_TOOLS + [send_message, add_to_calendar],
    system_prompt=TRUSTED_PROMPT,
    memory=["/AGENTS.md"],
    backend=FilesystemBackend(root_dir="workspace", virtual_mode=True),
    middleware=[TodoListMiddleware()],
    interrupt_on={
        "send_message": True,      # approve / edit / reject
        "add_to_calendar": True,
        # everything else runs unattended
    },
    checkpointer=MemorySaver(),     # required: pausing means state must live somewhere
)
print("built")
""")

md("""
The interrupt loop is yours to write. `deepagents` pauses the graph and hands you
the pending tool calls with their exact arguments — you're approving a *specific
message*, not a vague intention. How you present that is a product decision:
""")

code("""
def ask_human(interrupts) -> Command:
    \"\"\"Show pending tool calls, collect one decision each.\"\"\"
    decisions = []
    for itr in interrupts:
        value = getattr(itr, "value", itr)
        for request in (value or {}).get("action_requests", []):
            args = request.get("arguments") or request.get("args") or {}
            print("\\n" + "=" * 62)
            print(f"  APPROVAL NEEDED → {request.get('name')}")
            for k, v in args.items():
                print(f"    {k}: {v}")
            print("=" * 62)

            choice = input("  [a]pprove / [r]eject / [e]dit body: ").strip().lower()
            if choice.startswith("r"):
                reason = input("  reason (optional): ").strip()
                decisions.append({"type": "reject",
                                  "message": reason or "Rejected by the user."})
            elif choice.startswith("e"):
                args = dict(args)
                args["body"] = input("  new body: ").strip()
                decisions.append({"type": "edit",
                                  "args": {"name": request["name"], "arguments": args}})
            else:
                decisions.append({"type": "approve"})
    return Command(resume={"decisions": decisions})


def run_with_approvals(prompt, thread="s4"):
    config = {"configurable": {"thread_id": thread}}
    state = nb.run(buddy_v4, prompt, config=config, show_tool_results=False)

    while state and state.get("__interrupt__"):          # it may pause more than once
        command = ask_human(state["__interrupt__"])
        state = None
        for chunk in buddy_v4.stream(command, config=config, stream_mode="values"):
            state = chunk
            msg = chunk["messages"][-1]
            if msg.__class__.__name__ == "AIMessage":
                for call in getattr(msg, "tool_calls", []) or []:
                    print(f"  → {call['name']}")
                body = nb.text_of(msg.content).strip()
                if body:
                    print(f"\\nBuddy: {body}\\n")
    return state
""")

md("""
When you run the next cell an input box appears — in Jupyter Lab it shows under
the cell, in Colab at the bottom. Try **rejecting** the first message and watch the
agent adapt instead of crashing.
""")

code("""
state = run_with_approvals(
    "I'm a staff engineer at a healthcare company, I care about agent security and "
    "evals, and I'm hoping to move into a platform role. Remember that. Then find "
    "the one speaker I should most talk to and send them a short note asking for "
    "ten minutes.")
""")

code("""
print(Path("workspace/AGENTS.md").read_text())
""")

md("""
It rewrote its own profile of you. Run the previous cell again with a different
question and notice it doesn't re-ask who you are.
""")

# ───────────────────────────── Wrap ─────────────────────────────

md("""
---
# 5. Skills  ·  ~15 min

A system prompt is where you put who the agent is. A **skill** is where you put
how a specific job gets done.

A skill is a folder with a `SKILL.md`: YAML front matter giving a `name` and a
`description`, then the procedure in Markdown, plus any templates beside it. The
agent reads the descriptions cheaply and only loads the body when it decides the
skill applies. That is progressive disclosure, and it is why fifty skills do not
cost you fifty skills' worth of context on every turn.

This repo ships two, in `workspace/skills/`:

- `build-my-schedule` — the procedure from section 2, plus a day-file template
- `write-trip-report` — turning `/notes/` into something a manager reads

Open `workspace/skills/build-my-schedule/SKILL.md` now. Notice it encodes the
rules we kept having to repeat in system prompts: check `agenda_status` first,
always name a backup, never claim a travel time.
""")

code("""
from pathlib import Path
print(Path("workspace/skills/build-my-schedule/SKILL.md").read_text())
""")

code("""
# Standalone: this section needs only section 0 to have run.
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import TodoListMiddleware
from buddy.tools import (AGENDA_TOOLS, agenda_status, list_program,
                         search_sessions, get_session, check_plan)

# skills= takes paths relative to the backend root. With FilesystemBackend
# rooted at ./workspace, "/skills/" means ./workspace/skills/ .
skilled = create_deep_agent(
    model=MODEL,
    tools=AGENDA_TOOLS,
    system_prompt=(
        "You are the conference buddy. When a request matches one of your skills, "
        "follow that skill's procedure rather than improvising."
    ),
    skills=["/skills/"],
    memory=["/AGENTS.md"],
    backend=FilesystemBackend(root_dir="workspace", virtual_mode=True),
    middleware=[TodoListMiddleware()],
)

nb.run(
    skilled,
    "I'm a platform engineer focused on agent governance. Plan my Thursday.",
    show_tool_results=False,
)
""")

code("""
nb.show_workspace()
""")

md("""
Compare what it wrote against `templates/day.md`. The shape came from the skill,
not from you re-describing it in the prompt.
""")

md("""
---
# 6. MCP: tools you did not write  ·  ~12 min

Everything in `tools=` so far was a Python function in this repo. MCP servers let
you hand the agent tools somebody else maintains - calendars, ticket systems,
cloud consoles - without writing a client for each one.

The adapter turns a running MCP server into ordinary LangChain tools, so `tools=`
accepts them alongside your own:

```python
# pip install langchain-mcp-adapters
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "calendar": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@some/calendar-mcp-server"],
    },
})
mcp_tools = await client.get_tools()

buddy = create_deep_agent(
    model=MODEL,
    tools=AGENDA_TOOLS + mcp_tools,
    interrupt_on={"create_event": True},      # section 4 still applies
    checkpointer=MemorySaver(),
)
```

**That block is not run here, deliberately.** It needs a server process and
credentials that are not part of this workshop, and a cell that cannot run is
worse than a snippet that is honest about what it needs.

The part worth carrying out of the room is the last two lines. In section 4 you
gated a stubbed `add_to_calendar`. Swap it for a real calendar MCP server and
nothing else changes: the approval gate you already built now stands between the
agent and your actual calendar. The security boundary is yours, not the server's.

That matters, because an MCP server is code you did not write, running with your
credentials, exposing tools whose descriptions the model reads and trusts.
`interrupt_on` is where you decide what a third-party tool may do unattended.

Below, the external tool is stubbed so the wiring is runnable end to end. The
shape is exactly what you get back from `client.get_tools()`.
""")

code("""
# Standalone: this section needs only section 0 to have run.
from langchain.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from deepagents import create_deep_agent
from buddy.tools import AGENDA_TOOLS

@tool
def create_event(title: str, day: str, start: str, end: str) -> str:
    "Create a calendar event. Stands in for a calendar MCP server's tool."
    return f"Created '{title}' on {day} {start}-{end}."

# An MCP client would hand you a list like this one.
mcp_tools = [create_event]

buddy = create_deep_agent(
    model=MODEL,
    tools=AGENDA_TOOLS + mcp_tools,
    system_prompt=(
        "You are the conference buddy. You can put sessions in the attendee's "
        "calendar. Confirm the exact session before you do."
    ),
    interrupt_on={"create_event": True},     # the gate from section 4, unchanged
    checkpointer=MemorySaver(),
)

print(f"{len(AGENDA_TOOLS)} local tools + {len(mcp_tools)} external:")
for t in AGENDA_TOOLS + mcp_tools:
    print(f"  {t.name:16} {t.description.splitlines()[0][:58]}")
""")

md("""
`create_event` is gated; everything else runs unattended. That asymmetry is the
whole design: local read-only tools are cheap and reversible, a tool that writes
to your real calendar is neither - and it makes no difference whether you wrote
that tool or pulled it off an MCP server.
""")

md("""
---
## What you built

```python
create_deep_agent(
    model=...,              # 0  which brain
    tools=...,              # 1  what it can do        6  including tools you did not write
    backend=...,            # 2  where its files live
    middleware=[...],       # 2  planning
    subagents=[...],        # 3  research -> analysis -> synthesis
    memory=[...],           # 4  what it remembers about you
    interrupt_on={...},     # 4  which tools need a human
    checkpointer=...,       # 4  required to pause and resume
    skills=[...],           # 5  how specific jobs get done
)
```

Everything else in the harness - summarization, context offloading, the `task`
tool, prompt caching - you got for free and never configured.

## The repo you are taking away

- `buddy/tools.py` - six tools, including the one from section 1
- `buddy/data.py` - null-aware access to a live agenda
- `scripts/fetch_agenda.py` - the scraper, with validation gates
- `seed/skills/` - two skills with templates, extend by adding a folder
- `.devcontainer/` - the Codespaces setup you are running in
- `tests/verify.py` - checks the repo still does what it claims

## About the data

Everything came from `wearedevelopers.com`, fetched fresh on every run of the
notebook's first cell:

```bash
python scripts/fetch_agenda.py --force    # refetch now
python scripts/fetch_agenda.py --check    # parse and report, write nothing
```

Nothing is invented. Where the site does not publish a field it stays `None` and
the tools say "not published". If the markup changes, the fetcher's validation
gates refuse to overwrite good data and tell you to look in `data/raw/`.

Real, permanent gaps: no floor plan or walking distances exist anywhere, so the
buddy cannot tell you whether a transition is feasible; and no difficulty levels
are published. The agent says so rather than guessing, which is the habit worth
taking home.

Now go build one for a conference you are actually attending.
""")

notebook = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = ROOT / "conference_buddy.ipynb"
out.write_text(json.dumps(notebook, indent=1) + "\n")
print(f"wrote {out} — {len(CELLS)} cells "
      f"({sum(1 for c in CELLS if c['cell_type'] == 'code')} code)")
