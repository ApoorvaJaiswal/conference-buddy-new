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
### Lab: write a tool yourself

You have read five tools. Write the sixth. `find_speaker` takes a name and returns
every session that person is on.

Two things to get right, because they are the whole lesson: return compact lines
rather than full records, and say "not published" rather than guessing when a
field is missing.
""")

code("""
from langchain.tools import tool
from buddy import data

@tool
def find_speaker(name: str) -> str:
    '''Find every session a given speaker appears on. Partial names are fine.'''
    # YOUR CODE HERE.
    #   data.sessions()   -> every session dict
    #   s["speakers"]     -> [{"name":..., "role":..., "company":...}, ...]
    #   data.one_line(s)  -> the compact format the other tools return
    #   data.when(s)      -> "2026-09-24 11:40-12:10 @ Stage 4"
    #                        or "time not yet published"
    return "not implemented"


# Try it before handing it to a model.
print(find_speaker.invoke({"name": "Cavage"}))
""")

md("""
<details>
<summary>One working answer</summary>

```python
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
```

</details>

Now hand it to the agent and see whether it prefers your tool over
`search_sessions`. If your docstring is vague, it will not.
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

### Your turn

- Ask something the data can't answer — *"where's the nearest coffee?"* — and see
  how it behaves. That gap is where your next tool goes.
- Remove `check_plan` from `AGENDA_TOOLS`, rebuild the agent, and ask for a packed
  Thursday. Put it back. Compare.
- **Exercise:** write `find_speaker(name)` returning every session a person is on.
  Does the model prefer it over `search_sessions`?
""")

code("""
# Your experiments here.
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

### Your turn

- Comment out the `middleware=[...]` line, rebuild, run the same prompt. How much
  of the request actually gets done?
- Swap `FilesystemBackend` for the default `StateBackend` (just delete the
  `backend=` line). The plan still gets built — where does it go?
- **Exercise:** ask it to write `/notes/` entries during a session, then produce a
  trip report from them.
""")

code("""
# Your experiments here.
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

### Your turn

- Ask something needing both scouts: *"plan Thursday around the sessions I care
  about, and tell me where to eat between them."*
- Give `fit-analyst` the `search_sessions` tool. Watch it start second-guessing
  the scout instead of judging, and the pipeline blur.
- **Exercise:** add a `people-scout` that finds speakers worth meeting and drafts an
  opener. Then read section 4 for why that subagent must not be allowed to send it.
""")

code("""
# Your experiments here.
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

### Your turn

- Change `send_message` to `{"allowed_decisions": ["approve", "reject"]}` so the
  text can't be edited at approval time. Which would you actually ship?
- Gate `write_file` instead. Annoying? That's the lesson.
- **Exercise:** add a `when` predicate so only messages to speakers need approval,
  and messages to yourself don't.
""")

code("""
# Your experiments here.
""")

# ───────────────────────────── Wrap ─────────────────────────────

md("""
---
# 5. When things break  ·  ~15 min

Everything so far assumed the happy path. Production is mostly the other one.

Three failure modes, three prebuilt middleware, all from
`langchain.agents.middleware`:

| Fails | Middleware | What it does |
|---|---|---|
| a tool throws | `ToolRetryMiddleware` | retries with backoff, then hands the error to the model as a `ToolMessage` |
| the model errors | `ModelFallbackMiddleware` | tries alternative models in order |
| the agent loops | `ModelCallLimitMiddleware` | caps calls per run or per thread and exits |

The one that matters most is the least dramatic. `on_failure="continue"` means a
tool that stays broken returns its error **to the model as text**, and the agent
gets to decide what to do about it. An agent that can read "the agenda service is
down" and tell the user so is worth more than one that retries silently and then
invents an answer.
""")

code("""
# Standalone: this section needs only section 0 to have run.
from langchain.tools import tool
from deepagents import create_deep_agent
from langchain.agents.middleware import (
    ToolRetryMiddleware,
    ModelFallbackMiddleware,
    ModelCallLimitMiddleware,
)

# A fault injector. Not fake data - a tool that genuinely raises, so you can
# watch the retry machinery work instead of taking my word for it.
_attempts = {"count": 0}

@tool
def flaky_venue_lookup(query: str) -> str:
    '''Look up venue information. (Teaching stub: fails twice, then succeeds.)'''
    _attempts["count"] += 1
    if _attempts["count"] < 3:
        raise ConnectionError(f"venue service unavailable (attempt {_attempts['count']})")
    return "Venue service responded: San Jose McEnery Convention Center, 150 W San Carlos St."

print("fault injector ready")
""")

code("""
# Without retry: the agent sees the exception on its first try.
_attempts["count"] = 0
fragile = create_deep_agent(
    model=MODEL,
    tools=[flaky_venue_lookup],
    system_prompt="Answer using the tools. If a tool fails, say so plainly.",
)
nb.run(fragile, "Where is the venue?")
print()
print(f"tool was called {_attempts['count']} time(s)")
""")

code("""
# With retry: same tool, same failure, different outcome.
_attempts["count"] = 0
resilient = create_deep_agent(
    model=MODEL,
    tools=[flaky_venue_lookup],
    system_prompt="Answer using the tools. If a tool fails, say so plainly.",
    middleware=[
        ToolRetryMiddleware(
            max_retries=3,
            initial_delay=0.5,
            backoff_factor=2.0,
            on_failure="continue",   # exhausted retries -> error text to the model
        ),
    ],
)
nb.run(resilient, "Where is the venue?")
print()
print(f"tool was called {_attempts['count']} time(s)")
""")

md("""
### Model failure, demonstrated with one API key

`ModelFallbackMiddleware` normally means provider redundancy, which you can't show
with a single key. So point the primary at a model that doesn't exist. The failure
is real, and the fallback is the model you actually have.
""")

code("""
from buddy.tools import (AGENDA_TOOLS, agenda_status, list_program,
                         search_sessions, get_session, check_plan)

guarded = create_deep_agent(
    model="anthropic:this-model-does-not-exist",     # guaranteed to fail
    tools=[agenda_status],
    system_prompt="Be brief.",
    middleware=[
        ModelFallbackMiddleware(MODEL),               # your real model
        ModelCallLimitMiddleware(run_limit=8, exit_behavior="end"),
    ],
)
nb.run(guarded, "How many sessions do you know about, and what are you missing?")
""")

md("""
`ModelCallLimitMiddleware` is in there too, and it's the unglamorous one worth
keeping. An agent stuck in a tool-call loop is an agent spending your money. A run
limit turns a runaway into a bounded, explainable failure.

### Recovery the middleware can't do for you

Two failures here are yours to design around, not configure away:

- **A subagent returns nothing useful.** The supervisor still has to answer. Tell
  it in the system prompt what to do with an empty scout report.
- **A tool succeeds but the data is wrong or missing.** This is why `agenda_status`
  and the `"time not yet published"` markers exist. A tool that reports its own
  gaps lets the agent recover; one that silently returns a partial answer doesn't.

### Your turn

- Set `on_failure="raise"` instead. Where does the error surface, and is that
  better or worse for your user?
- Raise `max_retries` to 2 so the fault injector never succeeds. Watch what the
  agent tells the user.
- **Exercise:** give the buddy `refresh_agenda`, break your network, and see
  whether it degrades gracefully to the cached agenda.
""")

code("""
# Your experiments here.
""")

md("""
### Losing context mid-task

The failure that kills long-running agents is not a crash. It is the agent forty
tool calls deep that has quietly forgotten what it was asked to do.

Section 3's subagents are one answer: keep the noisy work out of the supervisor's
window. Two middleware handle the rest, and they are opposites.

`SummarizationMiddleware` compresses old turns into a summary once the window
fills. `ContextEditingMiddleware` with `ClearToolUsesEdit` discards old tool
*results* outright, keeping the decisions and dropping the evidence.

Summarise when the history carries reasoning you still need. Clear when it carries
bulk you do not. A buddy running across three days wants both.
""")

code("""
from langchain.agents.middleware import (
    SummarizationMiddleware,
    ContextEditingMiddleware,
    ClearToolUsesEdit,
    TodoListMiddleware,
)

long_running = create_deep_agent(
    model=MODEL,
    tools=AGENDA_TOOLS,
    system_prompt=(
        "You are the conference buddy, running across all three days. "
        "Keep track of what the attendee has already asked for."
    ),
    middleware=[
        TodoListMiddleware(),
        # Compress once the window is ~70% full, always keeping the last 20 messages.
        SummarizationMiddleware(model=MODEL, trigger=("fraction", 0.7),
                                keep=("messages", 20)),
        # And drop bulky old tool results rather than summarising them.
        ContextEditingMiddleware(edits=[ClearToolUsesEdit()]),
    ],
)
print("built: summarisation + tool-result clearing")
""")

code("""
# Drive it long enough that the middleware has work to do, then check whether the
# original constraints survived.
state = nb.run(long_running,
    "I am a platform engineer, I hate early mornings, and I only care about agent "
    "governance. Find me candidates on Thursday, then on Friday, then tell me what "
    "you would drop if I could attend only three things total - and repeat my "
    "constraints back to me so I know you still have them.",
    show_tool_results=False)

print(f"messages in final state: {len(state['messages'])}")
""")

md("""
The tell is whether it can still repeat your constraints back after all that work.
An agent that says "you mentioned you hate early mornings" after forty tool calls
is preserving context. One that asks you to restate it has lost the thread, and
that is the wall the workshop is about.
""")

md("""
---
# 6. Seeing what it did  ·  ~12 min

When an agent gives a bad answer, the question is always *where* it went wrong:
the tools, the plan, a subagent, or the final synthesis. Guessing is expensive.
Three levels of visibility, cheapest first.
""")

code("""
# Standalone: this section needs only section 0 to have run.
from deepagents import create_deep_agent
from buddy.tools import (AGENDA_TOOLS, agenda_status, list_program,
                         search_sessions, get_session, check_plan)

# Level 1: the harness's own debug output.
# `debug=True` is a create_deep_agent parameter, not a wrapper.
noisy = create_deep_agent(
    model=MODEL,
    tools=[agenda_status, search_sessions],
    system_prompt="Be brief.",
    debug=True,
)
nb.run(noisy, "What are you missing from the agenda?", show_tool_results=False)
""")

code("""
# Level 2: count what it actually cost. Token usage rides on each AI message.
def usage_of(state):
    prompt = completion = calls = 0
    for m in state["messages"]:
        u = getattr(m, "usage_metadata", None)
        if u:
            calls += 1
            prompt += u.get("input_tokens", 0)
            completion += u.get("output_tokens", 0)
    return calls, prompt, completion

plain = create_deep_agent(model=MODEL, tools=AGENDA_TOOLS,
                          system_prompt="You are a conference buddy. Be brief.")
state = nb.run(
    plain,
    "Three talks for a platform engineer on Thursday.",
    show_tool_results=False,
)
calls, prompt, completion = usage_of(state)
print(f"model calls: {calls}   input tokens: {prompt:,}   output tokens: {completion:,}")
""")

md("""
Run that same cell against the subagent agent from section 3 (if you ran it) and
compare the supervisor's input tokens. Context isolation is a claim in section 3; this is
where you check it.

### Level 3: LangSmith

Every run is already a trace; you just aren't collecting it. Add to `.env`:

```
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=wad-conference-buddy
```

Restart the kernel, re-run section 3, and open the trace at smith.langchain.com.
You get the subagent tree, the exact prompt each one received, timing per step,
and token cost per node. It is the difference between "the plan was bad" and
"fit-analyst never received the unscheduled flag".

### Your turn

- Diff the supervisor's token count between `buddy_v1` and `buddy_v3`.
- Turn `debug=True` on for a subagent instead of the supervisor.
- **Exercise:** find the single most expensive step in a section-3 run, then make
  it cheaper without making the answer worse.
""")

code("""
# Your experiments here.
""")

md("""
---
# 7. Skills  ·  ~15 min

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

### Your turn

- Delete the "never claim a travel time" line from the SKILL.md, re-run, and see
  whether the agent starts estimating.
- **Exercise:** write a third skill, `find-me-people`, that encodes how to pick
  who to approach and what an opener should say. Drop it in `workspace/skills/`
  and it is picked up on the next run - no code change.
""")

code("""
# Your experiments here.
""")

md("""
---
# 8. Backends  ·  ~10 min

`backend=` decides where the agent's files actually live. Four options, and the
choice is about who else needs to see them.

| Backend | Files live in | Use when |
|---|---|---|
| `StateBackend()` | the run's state | default; nothing survives the run |
| `FilesystemBackend(root_dir=...)` | real disk | you want to open them in an editor |
| `StoreBackend(namespace=..., store=...)` | a LangGraph store | per-user, persists across sessions and processes |
| `CompositeBackend(default, routes)` | several of the above | different prefixes go different places |

`CompositeBackend` is the one that matches a real conference buddy: the attendee's
profile and plans should outlive the session, but scratch files should not.
""")

code("""
# Standalone: this section needs only section 0 to have run.
from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware
from buddy.tools import (AGENDA_TOOLS, agenda_status, list_program,
                         search_sessions, get_session, check_plan)
from deepagents.backends import StateBackend, StoreBackend, CompositeBackend
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()   # swap for a Postgres store in production

routed = CompositeBackend(
    default=StateBackend(),                       # scratch: dies with the run
    routes={
        "/plan/":  StoreBackend(namespace=lambda rt: ("plans",), store=store),
        "/notes/": StoreBackend(namespace=lambda rt: ("notes",), store=store),
    },
)

persistent = create_deep_agent(
    model=MODEL,
    tools=AGENDA_TOOLS,
    system_prompt=(
        "You are the conference buddy. Durable work goes in /plan/ and /notes/. "
        "Anything scratch goes elsewhere and is expected to vanish."
    ),
    backend=routed,
    store=store,                                  # required when a route uses StoreBackend
    middleware=[TodoListMiddleware()],
)

nb.run(persistent,
       "Note that I care about agent security, then draft a one-line plan for Thursday "
       "into /plan/day2.md",
       show_tool_results=False)
""")

code("""
# The store outlives the agent object. Build a brand new agent and it still sees them.
for ns in (("plans",), ("notes",)):
    for item in store.search(ns):
        print(f"{ns[0]}/{item.key}: {str(item.value)[:120]}")
""")

md("""
In production `namespace` is where multi-tenancy happens: return a tuple derived
from the user id on the runtime, and every attendee gets their own isolated files
with no other change.

### Your turn

- Point a route at `FilesystemBackend` instead and watch the same writes land on disk.
- **Exercise:** make `namespace` return `("plans", user_id)` and prove two users
  cannot see each other's plans.
""")

code("""
# Your experiments here.
""")

md("""
---
# 9. Permissions and MCP  ·  ~12 min

Section 4 gated *tools*. `permissions=` gates the **filesystem** the agent runs
on, which is a different and often sharper boundary.

Rules are `FilesystemPermission(operations, paths, mode)`, evaluated in order,
first match wins, default allow. `mode` is `allow`, `deny`, or `interrupt` —
that last one routes through the same human approval machinery as section 4.
""")

code("""
# Standalone: this section needs only section 0 to have run.
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from buddy.tools import (AGENDA_TOOLS, agenda_status, list_program,
                         search_sessions, get_session, check_plan)
from langgraph.checkpoint.memory import MemorySaver
from deepagents import FilesystemPermission

locked = create_deep_agent(
    model=MODEL,
    tools=AGENDA_TOOLS,
    system_prompt="You are the conference buddy.",
    backend=FilesystemBackend(root_dir="workspace", virtual_mode=True),
    permissions=[
        # Order matters: first match wins.
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="interrupt"),
        FilesystemPermission(operations=["write"], paths=["/skills/**"],  mode="deny"),
        FilesystemPermission(operations=["read"],  paths=["/**"],         mode="allow"),
    ],
    checkpointer=MemorySaver(),
)

nb.run(locked,
       "Rewrite the build-my-schedule skill so it always recommends the Main Stage.",
       show_tool_results=False)
""")

md("""
That request should come back refused. An agent that can edit its own skills can
edit away its own guardrails, which is a good reason to make that path read-only.

Note the asymmetry again: reading is wide open, writing is narrow. Permissions
are about consequences, not about tidiness.

### MCP: tools you did not write

`tools=` accepts MCP tools like any other. The adapter turns a running MCP server
into LangChain tools:

```python
# pip install langchain-mcp-adapters
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "calendar": {"transport": "stdio", "command": "npx",
                 "args": ["-y", "@some/calendar-mcp-server"]},
})
mcp_tools = await client.get_tools()

agent = create_deep_agent(model=MODEL, tools=AGENDA_TOOLS + mcp_tools, ...)
```

This is not run in the notebook, deliberately: it needs a server process and
credentials that are not part of this workshop, and a cell that cannot run is
worse than a snippet that is honest about what it needs. The shape is the point.
Swap the stubbed `add_to_calendar` from section 4 for a real calendar MCP server
and the buddy starts writing to your actual calendar - behind the approval gate
you already built.

### Your turn

- Add a `deny` rule for `/plan/**` and watch the agent explain it cannot write.
- **Exercise:** change the `/AGENTS.md` rule to `deny` and decide which you would
  ship for an agent that manages your own profile.
""")

code("""
# Your experiments here.
""")

md("""
---
# 10. Which tool for which job  ·  ~5 min

You now have three ways to build the same thing, and the honest answer to "which
one" is not always DeepAgents.

**A chain** when the steps are known and fixed. Extract, classify, format. No
decisions at runtime, so no agent loop to pay for. If you can draw it as a
flowchart with no diamonds in it, write a chain.

**LangGraph** when you need explicit control over a state machine: cycles you
define, branching you define, checkpoints where you choose. You are writing the
graph. Use it when the control flow *is* the product, and when you need to reason
about every transition.

**DeepAgents** when the work is open-ended and long-horizon, and the sequence
depends on what the agent finds. That is exactly this workshop's use case: you
cannot know in advance how many searches a good three-day plan takes.

The tell is: can you enumerate the steps ahead of time? Yes and few → chain.
Yes and many, with structure → LangGraph. No → deep agent.

And the thing worth carrying out of here: DeepAgents is a harness built *on*
LangGraph. Everything in section 8 and section 6 is LangGraph underneath. You are
not choosing a different framework so much as choosing how much of the harness you
want to write yourself.

### What is battle-tested and what is not

Being straight about this, since your production systems will care:

- **Solid:** tools, the filesystem backends, subagents, human-in-the-loop, the
  retry and fallback middleware. These are the boring parts and they work.
- **Newer, moving fast:** skills, permissions, the composite backend routing.
  Useful and real, but the API has been changing release to release - which is
  why section 2 opens with "pin your versions" rather than closing with it.
- **Your job, not the framework's:** deciding what a subagent is allowed to touch,
  what needs approval, and what the agent should say when it does not know. No
  amount of harness saves you from getting those three wrong.

""")

md("""
---
## What you built

```python
create_deep_agent(
    model=...,              # 0  which brain
    tools=...,              # 1  what it can do
    backend=...,            # 2, 8  where its files live
    middleware=[...],       # 2  planning   5  retry, fallback, call limits
    subagents=[...],        # 3  research -> analysis -> synthesis
    memory=[...],           # 4  what it remembers about you
    interrupt_on={...},     # 4  which tools need a human
    skills=[...],           # 7  how specific jobs get done
    permissions=[...],      # 9  what it may read and write
    store=...,              # 8  persistence behind StoreBackend
    debug=True,             # 6  narrate the loop
)
```

Everything else in the harness — summarization, context offloading, prompt caching,
the `task` tool — you got for free and never configured.

## Where to go next

Things that didn't fit in ninety minutes:

- **Skills.** `skills=["./skills/"]` with a `SKILL.md` per repeatable procedure —
  *build-my-schedule*, *write-the-trip-report* — plus templates alongside. Loaded
  progressively, so they cost nothing until needed. This is the one I'd do first.
- **MCP.** Swap the stubbed `add_to_calendar` for a real calendar MCP server.
  `tools=` takes MCP tools directly.
- **Tracing.** Set `LANGSMITH_TRACING=true` and re-run section 3 to see where the
  subagents actually spent their tokens.
- **Async subagents.** The scouts here are synchronous — the supervisor blocks. For
  a buddy that keeps working while you're sitting in a talk, that's the wrong shape.

## About the data

Everything came from `wearedevelopers.com`, scraped by `scripts/fetch_agenda.py`
at container start and refreshable any time:

```bash
python scripts/fetch_agenda.py --force    # refetch now
python scripts/fetch_agenda.py --check    # parse and report, write nothing
```

Nothing in the dataset is invented. Where the site doesn't publish a field, it is
`None` and the tools say "not published". If the site's markup changes, the
fetcher's validation gates refuse to overwrite good data with a bad parse and tell
you to look in `data/raw/`.

Known gaps, all real: Friday's conference program renders client-side so a plain
fetch can't reach it; there is no floor plan or walking-distance data anywhere; and
no difficulty levels are published.

Now go build one for a conference you're actually attending.
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
