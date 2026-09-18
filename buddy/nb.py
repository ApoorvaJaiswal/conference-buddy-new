"""Display helpers for the workshop notebook.

Nothing here is deepagents. It just makes the agent loop visible in a notebook
cell instead of arriving as one wall of text at the end.
"""

from pathlib import Path

CYAN = "\033[36m"
DIM = "\033[2m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block["text"])
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts)


def run(agent, prompt, config=None, show_tool_results=True):
    """Invoke the agent and stream a readable trace. Returns the final state."""
    print(f"{BOLD}You:{RESET} {prompt}\n")
    config = config or {"configurable": {"thread_id": "notebook"}}

    state = None
    for chunk in agent.stream(
        {"messages": [{"role": "user", "content": prompt}]},
        config=config,
        stream_mode="values",
    ):
        state = chunk
        msg = chunk["messages"][-1]
        kind = msg.__class__.__name__

        if kind == "AIMessage":
            for call in getattr(msg, "tool_calls", []) or []:
                args = ", ".join(f"{k}={v!r}" for k, v in list(call["args"].items())[:3])
                print(f"{CYAN}  → {call['name']}{RESET}{DIM}({args[:150]}){RESET}")
            body = text_of(msg.content).strip()
            if body:
                print(f"\n{GREEN}Buddy:{RESET} {body}\n")

        elif kind == "ToolMessage" and show_tool_results:
            preview = text_of(msg.content).strip().replace("\n", " ⏎ ")[:180]
            print(f"{DIM}    ← {preview}{RESET}")

    return state


def show_workspace(root="workspace", max_chars=1200):
    """Print every file the agent wrote to disk."""
    root = Path(root)
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name != ".gitkeep")
    if not files:
        print(f"{DIM}(nothing in {root}/ yet){RESET}")
        return
    for path in files:
        body = path.read_text(errors="replace")
        clipped = body[:max_chars] + ("\n…" if len(body) > max_chars else "")
        print(f"{YELLOW}{BOLD}── {path} {RESET}")
        print(clipped)
        print()


def show_todos(state):
    """Print the agent's task list from its final state."""
    todos = (state or {}).get("todos") or []
    if not todos:
        print(f"{DIM}(no todos; is TodoListMiddleware enabled?){RESET}")
        return
    marks = {"completed": "✓", "in_progress": "▸", "pending": "·"}
    for t in todos:
        print(f"  {marks.get(t.get('status'), '?')} {t.get('content')}")


def reset_workspace(root="workspace"):
    """Wipe the agent's files so you can re-run a section cleanly."""
    import shutil

    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    print(f"{root}/ cleared")
