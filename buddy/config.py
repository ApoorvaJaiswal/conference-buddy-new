"""Shared configuration. Every step imports MODEL from here."""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
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

_KEY_FOR_PROVIDER = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def preflight() -> None:
    """Fail loudly and usefully instead of deep inside a stack trace."""
    provider = MODEL.split(":", 1)[0]
    key = _KEY_FOR_PROVIDER.get(provider)
    if key and not os.environ.get(key):
        sys.exit(
            f"\n  Model is '{MODEL}' but {key} is not set.\n"
            f"  Copy .env.example to .env and add your key, or set BUDDY_MODEL\n"
            f"  to a provider you do have a key for.\n"
        )
    if not DATA_FILE.exists():
        sys.exit("\n  data/sessions.json is missing. Run: python scripts/fetch_agenda.py\n")
    WORKSPACE.mkdir(exist_ok=True)
