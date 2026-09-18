"""Verify this workshop repo. Run: python tests/verify.py

Checks four things, mechanically:

  DATA   nothing fabricated is committed, and no invented facts in source
  CODE   everything parses, sections are independent, nothing is undefined
  API    every deepagents / langchain symbol and keyword actually exists
  SAY    the sections we claim to teach are present and reachable

Exits non-zero if any check fails. What it deliberately cannot check is listed
at the end, because a verifier that implies full coverage is its own kind of lie.
"""

from __future__ import annotations

import ast
import builtins
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Must come before any `buddy` import: an editable install of this package
# elsewhere on the machine would otherwise shadow the repo under test.
sys.path.insert(0, str(ROOT))
NB = ROOT / "conference_buddy.ipynb"
BUILTIN = set(dir(builtins)) | {"__name__", "_"}

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append((name, detail))
    mark = "\033[32m ok \033[0m" if ok else "\033[31mFAIL\033[0m"
    print(f"  [{mark}] {name}" + (f"\n         {detail}" if detail and not ok else ""))


# ── notebook helpers ────────────────────────────────────────────────────────


def load_cells():
    nb = json.loads(NB.read_text())
    out, sec = [], "0 setup"
    for c in nb["cells"]:
        src = "".join(c["source"])
        if c["cell_type"] == "markdown":
            for line in src.splitlines():
                if line.startswith("# ") and any(ch.isdigit() for ch in line[:6]):
                    sec = line.lstrip("# ").split("·")[0].strip()
            continue
        if "%pip" in src:
            continue
        out.append((sec, src))
    return nb, out


def names(src):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set(), set()
    load, store = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            (load if isinstance(n.ctx, ast.Load) else store).add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            store.add(n.name)
        elif isinstance(n, ast.alias):
            store.add((n.asname or n.name).split(".")[0])
        elif isinstance(n, ast.arg):
            store.add(n.arg)
    return load, store


# ── DATA: nothing fabricated ────────────────────────────────────────────────


def check_data():
    print("\nDATA — is anything fabricated?")

    check(
        "no dataset committed (agenda is fetched, never shipped)",
        not (ROOT / "data" / "sessions.json").exists(),
        "data/sessions.json is committed; it must be fetched at runtime",
    )

    # Invented concepts that were removed. Their return would mean fake data is back.
    banned = {
        "walk_minutes": "invented room-to-room distances",
        "walking_time": "tool built on invented distances",
        '"synthetic"': "fabricated session marker",
        "build_dataset": "the generator that made up sessions",
        "beginner/intermediate/advanced": "difficulty levels the site does not publish",
    }
    src_files = [
        p for p in ROOT.rglob("*")
        if p.suffix in {".py", ".md", ".ipynb", ".json", ".sh"}
        and "data/raw" not in str(p) and "/tests/" not in str(p)
        and ".venv" not in str(p) and "__pycache__" not in str(p)
    ]
    for token, why in banned.items():
        hits = [p.relative_to(ROOT) for p in src_files if token in p.read_text(errors="ignore")]
        check(f"no '{token}' ({why})", not hits, f"found in {hits}")

    # Speaker names must never be hardcoded: they come from the live fetch only.
    invented_people = ["Priya Raman", "Marcus Webb", "Sofia Lindqvist", "Daniel Okoye"]
    hits = [
        (p.relative_to(ROOT), n) for p in src_files for n in invented_people
        if n in p.read_text(errors="ignore")
    ]
    check("no invented speaker names in source", not hits, f"found {hits}")

    # Model identifiers must not be asserted; they change and I got them wrong before.
    bad_models = ["gpt-5.5", "gemini-3.6", "llama3.1"]
    hits = [
        (p.relative_to(ROOT), m) for p in src_files for m in bad_models
        if m in p.read_text(errors="ignore")
    ]
    check("no unverified model identifiers", not hits, f"found {hits}")

    # The fetcher must declare its sources and refuse a bad parse.
    fetcher = (ROOT / "scripts" / "fetch_agenda.py").read_text()
    check("fetcher records which URLs it read", '"sources": sorted(pages)' in fetcher)
    check(
        "fetcher refuses to overwrite good data with a bad parse",
        "Refusing to overwrite good data" in fetcher and "def validate(" in fetcher,
    )
    check(
        "fetcher only reads wearedevelopers.com",
        set(re.findall(r"https?://([a-z0-9.\-]+)", fetcher)) <= {"www.wearedevelopers.com"},
        f"other hosts: {set(re.findall(r'https?://([a-z0-9.-]+)', fetcher))}",
    )


# ── CODE: does it actually work ─────────────────────────────────────────────


def check_code():
    print("\nCODE — does it parse, and is it wired correctly?")

    nb, cells = load_cells()

    bad = [i for i, (_, src) in enumerate(cells) if _syntax_error(src)]
    check("every notebook code cell parses", not bad, f"cells {bad}")

    check(
        "notebook ships with no stale outputs",
        not any(c.get("outputs") for c in nb["cells"]),
        "run: jupyter nbconvert --clear-output --inplace conference_buddy.ipynb",
    )

    # No name used before it is defined anywhere.
    defined, undefined = set(), []
    for sec, src in cells:
        load, store = names(src)
        missing = {x for x in load if x not in BUILTIN and x not in store and x not in defined}
        if missing:
            undefined.append((sec, sorted(missing)))
        defined |= store
    check("no names used before definition", not undefined, f"{undefined}")

    # Every section must run straight after section 0.
    setup = set()
    for sec, src in cells:
        if sec == "0 setup":
            setup |= names(src)[1]
    broken = []
    for target in {s for s, _ in cells} - {"0 setup"}:
        have, missing = set(setup), set()
        for sec, src in cells:
            if sec != target:
                continue
            load, store = names(src)
            missing |= {x for x in load if x not in BUILTIN and x not in have and x not in store}
            have |= store
        if missing:
            broken.append((target, sorted(missing)))
    check("every section runs directly after section 0", not broken, f"{broken}")

    # Supporting files.
    for rel in ["scripts/fetch_agenda.py", "scripts/build_notebook.py",
                "scripts/diagnose_schedule.py", "buddy/tools.py", "buddy/data.py",
                "buddy/config.py", "buddy/nb.py"]:
        check(f"{rel} compiles", not _syntax_error((ROOT / rel).read_text()))

    dc = (ROOT / ".devcontainer" / "devcontainer.json").read_text()
    try:
        cfg = json.loads(re.sub(r"^\s*//.*$", "", dc, flags=re.M))
        ok, detail = True, ""
    except Exception as e:
        cfg, ok, detail = {}, False, str(e)
    check("devcontainer.json is valid JSON", ok, detail)
    check(
        "slow setup is baked into prebuilds (onCreateCommand)",
        "onCreateCommand" in cfg and "setup.sh" in cfg.get("onCreateCommand", ""),
    )
    for sh in ["setup.sh", "verify.sh"]:
        r = subprocess.run(["bash", "-n", str(ROOT / ".devcontainer" / sh)],
                           capture_output=True, text=True)
        check(f".devcontainer/{sh} is valid bash", r.returncode == 0, r.stderr.strip())

    # The notebook must refetch every run, not trust a cache.
    src_all = "\n".join(s for _, s in cells)
    check("notebook refetches the agenda on every run",
          '"--force"' in src_all and "fetch_agenda.py" in src_all)


def _syntax_error(src: str):
    try:
        ast.parse(src)
        return None
    except SyntaxError as e:
        return e


# ── API: do the symbols and keywords exist ──────────────────────────────────


def check_api():
    print("\nAPI — do the calls match the installed libraries?")
    try:
        import deepagents
        from deepagents import create_deep_agent
    except ImportError:
        check("deepagents importable", False, "pip install 'deepagents>=0.7'")
        return

    _, cells = load_cells()
    src_all = "\n".join(s for _, s in cells)

    # Keywords passed to create_deep_agent must exist in its signature.
    allowed = set(inspect.signature(create_deep_agent).parameters)
    used = set()
    for _, src in cells:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "create_deep_agent"):
                used |= {kw.arg for kw in node.keywords if kw.arg}
    check("create_deep_agent keywords all exist", used <= allowed,
          f"unknown: {sorted(used - allowed)}")
    check("create_deep_agent keywords exercised", len(used) >= 8,
          f"only {sorted(used)}")

    # Every symbol the notebook imports from these libs must resolve.
    bad = []
    for mod, sym in re.findall(r"from ([\w.]+) import \(([^)]*)\)", src_all) + \
                    [(m, s) for m, s in re.findall(r"from ([\w.]+) import ([^(\n]+)", src_all)]:
        if not mod.startswith(("deepagents", "langchain", "langgraph", "buddy")):
            continue
        try:
            m = __import__(mod, fromlist=["x"])
        except Exception as e:
            bad.append((mod, str(e)[:60])); continue
        sym = re.sub(r"#.*", "", sym)           # strip inline comments
        for name in [x.strip() for x in sym.replace("\n", " ").split(",") if x.strip()]:
            if hasattr(m, name):
                continue
            try:                                  # may be a submodule, not an attribute
                __import__(f"{mod}.{name}")
            except Exception:
                bad.append((f"{mod}.{name}", "missing"))
    check("every imported symbol resolves", not bad, f"{bad}")

    # Middleware keyword arguments must match real signatures.
    from langchain.agents import middleware as mw
    problems = []
    for cls_name in ["ToolRetryMiddleware", "ModelCallLimitMiddleware", "TodoListMiddleware"]:
        cls = getattr(mw, cls_name, None)
        if cls is None:
            problems.append((cls_name, "class missing")); continue
        params = set(inspect.signature(cls.__init__).parameters)
        for call in re.findall(rf"{cls_name}\(([^)]*)\)", src_all, re.S):
            for kw in re.findall(r"(\w+)\s*=", call):
                if kw not in params:
                    problems.append((cls_name, kw))
    check("middleware keyword arguments all exist", not problems, f"{problems}")

    # Backend and permission constructors used in the notebook.
    from deepagents.backends import StateBackend, StoreBackend, CompositeBackend, FilesystemBackend
    from deepagents import FilesystemPermission
    from langgraph.store.memory import InMemoryStore
    try:
        store = InMemoryStore()
        CompositeBackend(
            default=StateBackend(),
            routes={"/plan/": StoreBackend(namespace=lambda rt: ("plans",), store=store)},
        )
        FilesystemPermission(operations=["write"], paths=["/x"], mode="deny")
        FilesystemBackend(root_dir="workspace", virtual_mode=True)
        ok, detail = True, ""
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e}"
    check("backend and permission constructors work", ok, detail)


# ── SAY: did we build what we said ──────────────────────────────────────────


def check_promises():
    print("\nSAY — does the notebook cover what the abstract promises?")
    _, cells = load_cells()
    sections = {s for s, _ in cells}
    src_all = "\n".join(s for _, s in cells)

    promises = {
        "coordinator delegating to three subagents": (
            "session_scout" in src_all and "fit_analyst" in src_all and "brief_writer" in src_all
        ),
        "human-in-the-loop approval gates": "interrupt_on" in src_all,
        "long-term memory": "memory=" in src_all,
        "planning": "TodoListMiddleware" in src_all,
        "a filesystem backend": "FilesystemBackend" in src_all,
        "skills": "skills=" in src_all,
        "MCP integration": "MultiServerMCPClient" in NB.read_text(),
        "a tool built in front of the room": "def find_speaker" in src_all,
        "runs in GitHub Codespaces with no installs": (ROOT / ".devcontainer" / "setup.sh").exists(),
        "nothing left as an exercise": not any(
            t in src_all for t in ["Your turn", "YOUR CODE HERE", "Exercise:", "experiments here"]
        ),
    }
    for name, ok in promises.items():
        check(name, ok)

    # Skills must exist as real files, not just a parameter.
    skills = list((ROOT / "seed" / "skills").rglob("SKILL.md"))
    check("SKILL.md files ship with front matter", len(skills) >= 2 and all(
        s.read_text().startswith("---") and "description:" in s.read_text() for s in skills
    ), f"found {[str(s.relative_to(ROOT)) for s in skills]}")


# ── tool honesty, exercised for real ────────────────────────────────────────


def check_tool_honesty():
    print("\nDATA — do the tools admit what they do not know?")
    fixture = ROOT / "tests" / "fixture.py"
    if not fixture.exists():
        check("parser fixture present", False, "tests/fixture.py missing")
        return

    import importlib.util
    spec = importlib.util.spec_from_file_location("fa", ROOT / "scripts" / "fetch_agenda.py")
    fa = importlib.util.module_from_spec(spec); spec.loader.exec_module(fa)
    sys.path.insert(0, str(ROOT))
    from tests.fixture import SESSIONS_HTML, SCHEDULE_HTML

    payload = fa.build({
        f"{fa.BASE}/agenda/sessions": SESSIONS_HTML,
        f"{fa.BASE}/agenda/schedule": SCHEDULE_HTML,
    })
    check("parser extracts sessions from fixture HTML", len(payload["sessions"]) >= 3,
          f"{len(payload['sessions'])} parsed")
    check("parser assigns real times and stages",
          any(s["scheduled"] and s["stage"] for s in payload["sessions"]))
    check("validation gates reject a thin parse", bool(fa.validate(payload)),
          "a 4-session parse should fail the 40-session gate")

    # Drive the real tools over a session with no published time.
    unscheduled = dict(payload["sessions"][0])
    unscheduled.update({"id": "999999", "scheduled": False, "day": None,
                        "start": None, "end": None, "stage": None})
    payload["sessions"].append(unscheduled)
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "sessions.json").write_text(json.dumps(payload))
    try:
        from buddy import data
        data.reload()
        from buddy.tools import get_session, check_plan, agenda_status
        detail = get_session.invoke({"session_id": "999999"})
        check("get_session says 'time not yet published'", "not yet published" in detail, detail[:80])
        plan = check_plan.invoke({"session_ids": ["999999"]})
        check("check_plan flags unscheduled instead of assuming", "NO PUBLISHED TIME" in plan, plan[:90])
        check("check_plan states travel time is unknown", "not published anywhere" in plan)
        status = agenda_status.invoke({})
        check("agenda_status lists its own gaps", "Known gaps" in status)
    finally:
        (ROOT / "data" / "sessions.json").unlink(missing_ok=True)


def main() -> int:
    print("=" * 66)
    print("  Conference Buddy — verification")
    print("=" * 66)
    check_data()
    check_code()
    check_api()
    check_promises()
    check_tool_honesty()

    print("\n" + "=" * 66)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("\n  Failures:")
        for name, detail in FAIL:
            print(f"    - {name}: {detail}")
    print("""
  NOT CHECKED HERE, and it matters:
    - the live site. Nothing here fetches wearedevelopers.com, so the parser
      is verified only against tests/fixture.py. Run:
          python scripts/fetch_agenda.py --check
    - any model call. No API key is used, so no agent is ever invoked. The
      notebook's agents are verified to *construct*, not to answer well.
    - VS Code extension installation in a cold codespace.
""")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
