#!/usr/bin/env bash
#
# Runs at container creation (baked into prebuilds) AND again for every
# codespace. Idempotent: a fast no-op when the first run worked, a repair when
# it didn't.
#
# Deliberately NOT using `set -e`. One failed step must not stop the rest —
# losing the dataset is annoying, losing the kernel means nothing runs at all.
#
# Everything installs into ./.venv rather than system Python. Debian-based
# images mark system Python "externally managed" (PEP 668) and refuse pip
# installs, and which python3 you land on varies by image. A venv sidesteps
# both problems and gives VS Code an unambiguous interpreter to select.

LOG=/tmp/buddy-setup.log
exec > >(tee -a "$LOG") 2>&1
echo "=== setup.sh $(date -u +%H:%M:%S) ==="

# 1. Find some Python to bootstrap from
BASE="$(command -v python3 || command -v python)"
if [ -z "$BASE" ]; then
    echo "FATAL: no python on PATH."
    exit 0
fi
echo "Base interpreter: $BASE ($("$BASE" -V 2>&1))"

# 2. Virtualenv in the workspace (persists, and is included in prebuilds)
VENV="$(pwd)/.venv"
if [ ! -x "$VENV/bin/python" ]; then
    echo "Creating virtualenv at $VENV"
    "$BASE" -m venv "$VENV" 2>/dev/null
fi

if [ -x "$VENV/bin/python" ]; then
    PY="$VENV/bin/python"
    PIPFLAGS=""
else
    echo "WARN: venv creation failed; falling back to $BASE with --break-system-packages"
    PY="$BASE"
    PIPFLAGS="--break-system-packages"
fi
echo "Using: $PY"

pipi() { "$PY" -m pip install --quiet $PIPFLAGS "$@"; }

# 3. ipykernel first — without it the notebook cannot run at all
pipi --upgrade pip 2>/dev/null
if ! "$PY" -c "import ipykernel" 2>/dev/null; then
    echo "Installing ipykernel..."
    pipi ipykernel || echo "ERROR: ipykernel install failed"
fi

"$PY" -m ipykernel install --sys-prefix --name python3 \
      --display-name "Python 3 (Conference Buddy)" >/dev/null 2>&1 \
  || "$PY" -m ipykernel install --user --name python3 \
      --display-name "Python 3 (Conference Buddy)" >/dev/null 2>&1 \
  || echo "WARN: no kernelspec registered (VS Code can usually still find the venv)"

# 4. Workshop dependencies, with a fallback if the editable install trips
if ! "$PY" -c "import deepagents" 2>/dev/null; then
    echo "Installing dependencies..."
    pipi -e ".[all-providers]" jupyterlab || {
        echo "Editable install failed; installing packages directly."
        pipi "deepagents>=0.7" "langchain>=1.0" "langchain-anthropic>=1.0" \
             langchain-openai langchain-google-genai python-dotenv jupyterlab \
          || echo "ERROR: dependency install failed"
    }
fi

# 5. Point VS Code at the interpreter we actually built
mkdir -p .vscode
cat > .vscode/settings.json <<JSON
{
  "python.defaultInterpreterPath": "$PY",
  "python.terminal.activateEnvironment": true,
  "jupyter.kernels.filter": []
}
JSON

# 6. Fetch the real agenda. Non-fatal: the notebook can refetch on demand, and a
#    stale cache is better than a broken container.
echo "Fetching the conference agenda..."
"$PY" scripts/fetch_agenda.py || echo "WARN: agenda fetch failed; the notebook will retry"
# Seed the agent's workspace: memory file and the skills from section 7.
mkdir -p workspace
[ -f workspace/AGENTS.md ] || cp seed/AGENTS.md workspace/AGENTS.md
mkdir -p workspace/skills && cp -rn seed/skills/. workspace/skills/ 2>/dev/null || true

echo "=== setup.sh done ==="
exit 0