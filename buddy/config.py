"""Paths and model default. Small on purpose: the notebook selects its own
model and prompts for keys in section 0, so this only holds what buddy/data.py
and anything you build on top of it needs."""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Explicit path: the default walks the call stack, which can fail when this
    # module is imported from an unusual context.
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
except Exception:  # pragma: no cover
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = REPO_ROOT / "data" / "sessions.json"
WORKSPACE = REPO_ROOT / "workspace"

# Any provider works. Override with BUDDY_MODEL in .env using "provider:model".
# Check your provider's current model list rather than copying an identifier
# from a tutorial - they change often.
#   BUDDY_MODEL=openai:<model-id>
#   BUDDY_MODEL=google_genai:<model-id>
#   BUDDY_MODEL=ollama:<model-id>
MODEL = os.environ.get("BUDDY_MODEL", "anthropic:claude-sonnet-4-6")

# Kept deliberately small: the notebook does its own model selection and key
# prompting in section 0, so this module only holds paths that buddy/data.py needs.
