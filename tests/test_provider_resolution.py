"""
Tests for centralized per-role provider resolution.

The defect these lock down: LLM_PROVIDER used to act as an on/off gate rather
than a fallback, so a configuration that set only INVESTIGATOR_PROVIDER /
VERIFIER_PROVIDER silently ran both agents against the offline demo emulator
while reporting AUTO_RESOLVED decisions.
"""

import logging
import os
from unittest.mock import patch

import pytest

from src.config import DEFAULT_GEMINI_MODEL
from src.agent.provider_resolution import (
    format_resolution_banner,
    is_demo_mode_forced,
    normalize_provider,
    resolve_base_provider,
    resolve_providers,
    resolve_role,
    role_credentials_present,
)

# Dummy credentials, shaped to pass the credential-vs-model validator.
OR_KEY = "sk-or-v1-dummykey12345678901234567890"
GEM_KEY = "AIzaSyDummyKey12345678901234567890"

#: Every provider/credential variable, so patch.dict can start from a blank slate
#: instead of inheriting the developer's real .env.
_ALL_PROVIDER_VARS = {
    "DEMO_MODE": "",
    "LLM_PROVIDER": "",
    "INVESTIGATOR_PROVIDER": "",
    "INVESTIGATOR_API_KEY": "",
    "INVESTIGATOR_MODEL": "",
    "VERIFIER_PROVIDER": "",
    "VERIFIER_API_KEY": "",
    "VERIFIER_MODEL": "",
    "GEMINI_API_KEY": "",
    "GEMINI_MODEL": "",
    "OPENROUTER_API_KEY": "",
    "OPENROUTER_MODEL": "",
    "AGENTROUTER_API_KEY": "",
    "AGENTROUTER_MODEL": "",
}


def env(**overrides):
    """Builds a fully-specified provider environment, blank except for overrides."""
    return patch.dict(os.environ, {**_ALL_PROVIDER_VARS, **overrides})


# ----------------------------------------------------------------------
# The core regression: role variables are sufficient on their own
# ----------------------------------------------------------------------
def test_role_providers_alone_produce_a_live_run():
    """
    Setting only the role providers must NOT fall back to demo.

    This is the exact configuration that silently ran offline before: both roles
    fully configured, LLM_PROVIDER absent.
    """
    with env(
        INVESTIGATOR_PROVIDER="gemini",
        VERIFIER_PROVIDER="gemini",
        GEMINI_API_KEY=GEM_KEY,
        GEMINI_MODEL="gemini-2.5-flash",
    ):
        res = resolve_providers()

    assert res.investigator.provider == "gemini"
    assert res.verifier.provider == "gemini"
    assert res.is_demo is False
    assert res.degraded is False
    assert res.provider_label == "gemini"


def test_role_providers_alone_with_mixed_providers():
    """Each role resolves its own provider and model with no LLM_PROVIDER set."""
    with env(
        INVESTIGATOR_PROVIDER="openrouter",
        INVESTIGATOR_API_KEY=OR_KEY,
        INVESTIGATOR_MODEL="meta-llama/llama-3.3-70b-instruct",
        VERIFIER_PROVIDER="gemini",
        VERIFIER_API_KEY=GEM_KEY,
        VERIFIER_MODEL="gemini-2.5-flash",
    ):
        res = resolve_providers()

    assert res.investigator.provider == "openrouter"
    assert res.investigator.model == "meta-llama/llama-3.3-70b-instruct"
    assert res.verifier.provider == "gemini"
    assert res.verifier.model == "gemini-2.5-flash"
    assert res.provider_label == "openrouter+gemini"
    assert res.degraded is False


def test_llm_provider_acts_as_fallback_not_gate():
    """A role without its own provider inherits LLM_PROVIDER."""
    with env(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY=GEM_KEY,
        INVESTIGATOR_PROVIDER="openrouter",
        INVESTIGATOR_API_KEY=OR_KEY,
        INVESTIGATOR_MODEL="meta-llama/llama-3.3-70b-instruct",
    ):
        res = resolve_providers()

    assert res.investigator.provider == "openrouter"
    assert res.verifier.provider == "gemini"  # inherited
    assert res.degraded is False


# ----------------------------------------------------------------------
# Roles degrade independently
# ----------------------------------------------------------------------
def test_roles_degrade_independently():
    """A missing Verifier key must not drag the Investigator offline too."""
    with env(
        INVESTIGATOR_PROVIDER="gemini",
        INVESTIGATOR_API_KEY=GEM_KEY,
        INVESTIGATOR_MODEL="gemini-2.5-flash",
        VERIFIER_PROVIDER="openrouter",
        # no OpenRouter key anywhere
        VERIFIER_MODEL="meta-llama/llama-3.3-70b-instruct",
    ):
        res = resolve_providers()

    assert res.investigator.provider == "gemini"
    assert res.investigator.degraded is False
    assert res.verifier.provider == "demo"
    assert res.verifier.degraded is True
    assert res.degraded is True
    assert res.is_demo is False
    assert res.provider_label == "gemini+demo"


def test_missing_key_reports_reason_and_does_not_raise():
    with env(VERIFIER_PROVIDER="gemini"):
        role = resolve_role("verifier")

    assert role.provider == "demo"
    assert role.degraded is True
    assert "no API key is configured" in role.degraded_reason
    assert "VERIFIER_API_KEY" in role.degraded_reason
    assert role.requested_provider == "gemini"


def test_missing_model_for_gateway_provider_degrades():
    """OpenRouter has no default model, so an unset model is a config error."""
    with env(INVESTIGATOR_PROVIDER="openrouter", INVESTIGATOR_API_KEY=OR_KEY):
        role = resolve_role("investigator")

    assert role.provider == "demo"
    assert role.degraded is True
    assert "no model is configured" in role.degraded_reason


def test_provider_with_default_model_does_not_need_one_set():
    """Gemini carries a sensible default model, so a key alone suffices."""
    with env(INVESTIGATOR_PROVIDER="gemini", INVESTIGATOR_API_KEY=GEM_KEY):
        role = resolve_role("investigator")

    assert role.provider == "gemini"
    # Pinned to the single shared default rather than a literal, so the four
    # copies of this value cannot drift apart again.
    assert role.model == DEFAULT_GEMINI_MODEL
    assert role.degraded is False


def test_unsupported_provider_degrades_with_clear_reason():
    with env(INVESTIGATOR_PROVIDER="not-a-real-provider", GEMINI_API_KEY=GEM_KEY):
        role = resolve_role("investigator")

    assert role.provider == "demo"
    assert role.degraded is True
    assert "unsupported provider" in role.degraded_reason


# ----------------------------------------------------------------------
# Demo mode is explicit, and separable from "nothing configured"
# ----------------------------------------------------------------------
def test_demo_mode_env_var_forces_demo_over_real_credentials():
    """DEMO_MODE is a kill switch: real credentials must not override it."""
    with env(
        DEMO_MODE="true",
        LLM_PROVIDER="gemini",
        INVESTIGATOR_PROVIDER="openrouter",
        INVESTIGATOR_API_KEY=OR_KEY,
        INVESTIGATOR_MODEL="meta-llama/llama-3.3-70b-instruct",
        GEMINI_API_KEY=GEM_KEY,
    ):
        res = resolve_providers()

    assert res.is_demo is True
    assert res.demo_explicit is True
    # Explicitly requested demo is not a degradation.
    assert res.degraded is False


def test_llm_provider_demo_still_forces_demo():
    """Backwards compatibility: LLM_PROVIDER=demo remains a kill switch."""
    with env(
        LLM_PROVIDER="demo",
        INVESTIGATOR_PROVIDER="gemini",
        INVESTIGATOR_API_KEY=GEM_KEY,
    ):
        res = resolve_providers()

    assert res.is_demo is True
    assert res.demo_explicit is True
    assert res.degraded is False


def test_provider_argument_demo_forces_demo():
    with env(INVESTIGATOR_PROVIDER="gemini", GEMINI_API_KEY=GEM_KEY):
        res = resolve_providers(provider="demo")

    assert res.is_demo is True
    assert res.demo_explicit is True


def test_nothing_configured_is_demo_but_not_degraded():
    """Empty configuration yields demo without warning -- nothing was asked for."""
    with env():
        res = resolve_providers()

    assert res.is_demo is True
    assert res.demo_explicit is False
    assert res.degraded is False


def test_demo_mode_forced_reads_truthy_values():
    for value in ("1", "true", "TRUE", "yes", "on"):
        with env(DEMO_MODE=value):
            assert is_demo_mode_forced() is True
    for value in ("0", "false", "no", "", "off"):
        with env(DEMO_MODE=value):
            assert is_demo_mode_forced() is False


def test_demo_role_never_carries_a_real_model_name():
    """A demo run must not be labelled with a model it never called."""
    with env(
        DEMO_MODE="true",
        INVESTIGATOR_MODEL="meta-llama/llama-3.3-70b-instruct",
        VERIFIER_MODEL="gemini-2.5-flash",
    ):
        res = resolve_providers()

    assert res.investigator.model == "demo"
    assert res.verifier.model == "demo"


# ----------------------------------------------------------------------
# Degradation is loud
# ----------------------------------------------------------------------
def test_degradation_emits_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="src.agent.provider_resolution"):
        with env(INVESTIGATOR_PROVIDER="gemini", VERIFIER_PROVIDER="gemini"):
            resolve_providers()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2  # one per role
    combined = " ".join(r.getMessage() for r in warnings)
    assert "degraded to DEMO" in combined
    assert "offline rule-based emulator" in combined


def test_no_warning_when_demo_is_explicit(caplog):
    with caplog.at_level(logging.WARNING, logger="src.agent.provider_resolution"):
        with env(DEMO_MODE="true"):
            resolve_providers()

    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_warn_false_suppresses_logging(caplog):
    with caplog.at_level(logging.WARNING, logger="src.agent.provider_resolution"):
        with env(INVESTIGATOR_PROVIDER="gemini"):
            resolve_providers(warn=False)

    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def test_normalize_provider_trims_and_lowercases():
    assert normalize_provider("  GEMINI ") == "gemini"
    assert normalize_provider("OpenRouter") == "openrouter"
    assert normalize_provider(None) == ""


def test_resolve_base_provider_prefers_explicit_argument():
    with env(LLM_PROVIDER="gemini"):
        assert resolve_base_provider("openrouter") == "openrouter"
        assert resolve_base_provider(None) == "gemini"
    with env():
        assert resolve_base_provider(None) == ""


def test_role_credentials_present_matches_resolution():
    with env(INVESTIGATOR_PROVIDER="gemini", INVESTIGATOR_API_KEY=GEM_KEY):
        assert role_credentials_present("investigator") is True
    with env(INVESTIGATOR_PROVIDER="gemini"):
        assert role_credentials_present("investigator") is False


def test_role_scoped_key_wins_over_shared_key():
    with env(
        INVESTIGATOR_PROVIDER="gemini",
        INVESTIGATOR_API_KEY="role-scoped-key",
        GEMINI_API_KEY="shared-key",
    ):
        role = resolve_role("investigator")

    assert role.api_key == "role-scoped-key"


def test_banner_reports_degradation():
    with env(INVESTIGATOR_PROVIDER="gemini", VERIFIER_PROVIDER="gemini"):
        res = resolve_providers(warn=False)

    banner = format_resolution_banner(res)
    assert "DEGRADED from 'gemini'" in banner
    assert "Mode: DEMO (no usable provider credentials)" in banner


def test_banner_distinguishes_explicit_demo():
    with env(DEMO_MODE="true"):
        res = resolve_providers()

    banner = format_resolution_banner(res)
    assert "Mode: DEMO (explicitly requested)" in banner
    assert "DEGRADED" not in banner
