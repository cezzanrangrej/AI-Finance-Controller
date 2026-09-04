"""
Centralized environment configuration loader for AI Finance Controller.

Uses pydantic-settings BaseSettings to manage typed environment configuration with defaults.
Loads .env into os.environ at startup so os.getenv and monkeypatch work standardly across tests.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_current_dir = Path(__file__).resolve().parent
_project_root = _current_dir.parent
_env_path = _project_root / ".env"

if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_env_path) if _env_path.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    database_url: str = Field(default="sqlite:///./data/finance_controller.db", validation_alias="DATABASE_URL")
    llm_provider: str = Field(default="", validation_alias="LLM_PROVIDER")

    # Read as a string, not a bool: a blank `DEMO_MODE=` in .env is a normal state and
    # pydantic's bool parser rejects "", which would crash every import of this module.
    # Use is_demo_mode() rather than reading this directly.
    demo_mode: str = Field(default="", validation_alias="DEMO_MODE")
    
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", validation_alias="GEMINI_MODEL")
    
    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="", validation_alias="OPENROUTER_MODEL")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", validation_alias="OPENROUTER_BASE_URL")
    
    investigator_provider: str = Field(default="", validation_alias="INVESTIGATOR_PROVIDER")
    investigator_api_key: str = Field(default="", validation_alias="INVESTIGATOR_API_KEY")
    investigator_model: str = Field(default="", validation_alias="INVESTIGATOR_MODEL")
    
    verifier_provider: str = Field(default="", validation_alias="VERIFIER_PROVIDER")
    verifier_api_key: str = Field(default="", validation_alias="VERIFIER_API_KEY")
    verifier_model: str = Field(default="", validation_alias="VERIFIER_MODEL")
    
    max_parallel_batches: int = Field(default=5, validation_alias="MAX_PARALLEL_BATCHES")
    env: str = Field(default="development", validation_alias="ENV")


settings = Settings()


def get_llm_provider() -> str:
    """
    Returns the base LLM provider, defaulting to 'demo' when nothing is set.

    This is the CLI/single-agent default only. The multi-agent pipeline resolves
    each role independently via src.agent.provider_resolution, where this value
    acts as a fallback rather than a gate -- setting only
    INVESTIGATOR_PROVIDER/VERIFIER_PROVIDER is a valid configuration there.
    """
    if is_demo_mode():
        return "demo"
    return (os.getenv("LLM_PROVIDER") or settings.llm_provider or "demo").strip().lower()


def is_demo_mode() -> bool:
    """
    Returns True when offline demo mode was explicitly requested via DEMO_MODE.

    Exists so that "deliberately offline" and "no provider configured" are
    distinguishable; LLM_PROVIDER=demo remains supported for compatibility.
    """
    env_val = os.getenv("DEMO_MODE")
    if env_val is None:
        env_val = settings.demo_mode
    return str(env_val).strip().lower() in ("1", "true", "yes", "on")


def get_gemini_api_key() -> str:
    """Returns the Gemini API key or empty string."""
    return os.getenv("GEMINI_API_KEY", settings.gemini_api_key).strip()


def get_gemini_model() -> str:
    """Returns the configured Gemini model name."""
    return (os.getenv("GEMINI_MODEL") or os.getenv("MODEL_NAME") or settings.gemini_model or "gemini-2.5-flash").strip()


def is_gemini_key_configured() -> bool:
    """Returns True if a non-empty Gemini API key is loaded."""
    return bool(get_gemini_api_key())


def get_openrouter_api_key() -> str:
    """Returns the OpenRouter API key or empty string."""
    return os.getenv("OPENROUTER_API_KEY", settings.openrouter_api_key).strip()


def get_openrouter_model() -> str:
    """Returns the configured OpenRouter model name or empty string."""
    return os.getenv("OPENROUTER_MODEL", settings.openrouter_model).strip()


def get_openrouter_base_url() -> str:
    """Returns the OpenRouter base URL (default: https://openrouter.ai/api/v1)."""
    return os.getenv("OPENROUTER_BASE_URL", settings.openrouter_base_url or "https://openrouter.ai/api/v1").strip()


def is_openrouter_key_configured() -> bool:
    """Returns True if a non-empty OpenRouter API key is loaded."""
    return bool(get_openrouter_api_key())


def get_max_parallel_batches() -> int:
    """Returns MAX_PARALLEL_BATCHES configured in environment (default 5, validated 1-5)."""
    env_val = os.getenv("MAX_PARALLEL_BATCHES")
    if env_val is not None:
        try:
            val = int(env_val.strip())
            return max(1, min(5, val))
        except (ValueError, TypeError):
            pass
    try:
        val = settings.max_parallel_batches
        return max(1, min(5, val))
    except (ValueError, TypeError):
        return 5
