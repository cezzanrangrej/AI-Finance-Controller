"""
Centralized environment configuration loader for AI Finance Controller.

Ensures .env is loaded automatically before reading LLM_PROVIDER, GEMINI_API_KEY,
GEMINI_MODEL, OPENROUTER_API_KEY, OPENROUTER_MODEL, or DATABASE_URL regardless of the Python entry point used.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Locate project root directory containing .env
_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent
_env_path = _project_root / ".env"

# Load environment variables from .env file if it exists, otherwise standard load_dotenv()
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()


def get_llm_provider() -> str:
    """Returns the configured LLM provider ('openrouter', 'gemini', or 'demo')."""
    return os.getenv("LLM_PROVIDER", "demo").strip().lower()


def get_gemini_api_key() -> str:
    """Returns the Gemini API key or empty string."""
    return os.getenv("GEMINI_API_KEY", "").strip()


def get_gemini_model() -> str:
    """Returns the configured Gemini model name."""
    return os.getenv("GEMINI_MODEL") or os.getenv("MODEL_NAME") or "gemini-3.5-flash"


def is_gemini_key_configured() -> bool:
    """Returns True if a non-empty Gemini API key is loaded."""
    return bool(get_gemini_api_key())


def get_openrouter_api_key() -> str:
    """Returns the OpenRouter API key or empty string."""
    return os.getenv("OPENROUTER_API_KEY", "").strip()


def get_openrouter_model() -> str:
    """Returns the configured OpenRouter model name or empty string."""
    return os.getenv("OPENROUTER_MODEL", "").strip()




def get_openrouter_base_url() -> str:
    """Returns the OpenRouter base URL (default: https://openrouter.ai/api/v1)."""
    return os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()


def is_openrouter_key_configured() -> bool:
    """Returns True if a non-empty OpenRouter API key is loaded."""
    return bool(get_openrouter_api_key())


def get_max_parallel_batches() -> int:
    """Returns MAX_PARALLEL_BATCHES configured in environment (default 5, validated 1-5)."""
    try:
        val = int(os.getenv("MAX_PARALLEL_BATCHES", "5").strip())
        return max(1, min(5, val))
    except (ValueError, TypeError):
        return 5


