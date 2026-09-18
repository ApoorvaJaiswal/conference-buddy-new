"""A small pretty-printer so attendees can see what the agent is doing.

Not part of deepagents. Just enough terminal output that the agent loop is
visible rather than a black box that eventually prints a paragraph.
"""

import sys

DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RESET = "\033[0m"


def _text(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block["text"])
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts)


def run(agent, prompt: str, config: dict | None = None, quiet_tools: bool = False):
    """Invoke the agent, streaming a readable trace of what happens."""
    print(f"\n{BOLD}You:{RESET} {prompt}\n")
    config = config or {"configurable": {"thread_id": "workshop"}}

    final_state = None
    for chunk in agent.stream(
        {"messages": [{"role": "user", "content": prompt}]},
        config=config,
        stream_mode="values",
    ):
        final_state = chunk
        msg = chunk["messages"][-1]
        kind = msg.__class__.__name__

        if kind == "AIMessage":
            for call in getattr(msg, "tool_calls", []) or []:
                args = ", ".join(
                    f"{k}={v!r}" for k, v in list(call["args"].items())[:3]
                )
                print(f"  {CYAN}→ {call['name']}{RESET}{DIM}({args[:140]}){RESET}")
            body = _text(msg.content).strip()
            if body:
                print(f"\n{GREEN}Buddy:{RESET} {body}\n")

        elif kind == "ToolMessage" and not quiet_tools:
            preview = _text(msg.content).strip().replace("\n", " ")[:160]
            print(f"    {DIM}← {preview}{RESET}")

    return final_state


def show_files(state) -> None:
    """Print the virtual filesystem the agent built up, if any."""
    files = (state or {}).get("files") or {}
    if not files:
        print(f"{DIM}(no files in agent state){RESET}")
        return
    print(f"\n{BOLD}Files in agent state:{RESET}")
    for path in sorted(files):
        print(f"  {YELLOW}{path}{RESET}")


def prompt_from_argv(default: str) -> str:
    return " ".join(sys.argv[1:]) or default
