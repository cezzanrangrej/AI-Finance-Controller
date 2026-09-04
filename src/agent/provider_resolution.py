"""
Single source of truth for resolving per-role LLM provider configuration.

Historically the Investigator/Verifier provider resolution logic was duplicated in
three places (MultiAgentOrchestrator, BatchMultiAgentController, and the API
preflight in src/api/routes/runs.py). The copies drifted, producing two defects:

1.  ``LLM_PROVIDER`` acted as an on/off gate rather than a fallback. Both
    controllers resolved ``self.provider`` to ``"demo"`` when ``LLM_PROVIDER``
    was unset, then took a branch that hardcoded both roles to demo -- so the
    ``INVESTIGATOR_PROVIDER`` / ``VERIFIER_PROVIDER`` variables were only read in
    the branch an unset ``LLM_PROVIDER`` skipped. A fully configured role-only
    setup silently ran against the offline emulator.
2.  The API preflight and the controllers ran independent resolution ladders over
    the same variables with different fallback rules, so they could disagree
    about whether a run was live.

This module replaces all three. Roles resolve independently; ``LLM_PROVIDER`` is
a fallback, never a gate. Demo mode is only entered when explicitly requested
(``DEMO_MODE=true``, ``LLM_PROVIDER=demo``, or ``provider="demo"``) or when
credentials are genuinely absent -- and the absent case always emits a warning,
because a reconciliation run that reports AUTO_RESOLVED decisions from a
rule-based emulator while the operator believed a real model reviewed them is
the failure mode that matters most here.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from src.config import DEFAULT_GEMINI_MODEL

logger = logging.getLogger(__name__)

DEMO = "demo"

#: Providers accepted in LLM_PROVIDER / INVESTIGATOR_PROVIDER / VERIFIER_PROVIDER.
VALID_PROVIDERS: Tuple[str, ...] = ("demo", "gemini", "openrouter", "agentrouter")

#: Provider aliases normalised before resolution. Empty for now; kept as the single
#: place to add one, since every call path funnels through normalize_provider().
_PROVIDER_ALIASES: Dict[str, str] = {}


@dataclass(frozen=True)
class _ProviderSpec:
    """Where a provider's credentials live, and whether a model name is mandatory."""

    key_vars: Tuple[str, ...]
    model_vars: Tuple[str, ...]
    default_model: str
    #: Providers fronting many models (gateways) cannot be given a sensible
    #: default -- an unset model is a configuration error, not an inherited value.
    model_required: bool


_PROVIDER_SPECS: Dict[str, _ProviderSpec] = {
    "gemini": _ProviderSpec(
        key_vars=("GEMINI_API_KEY",),
        model_vars=("GEMINI_MODEL",),
        default_model=DEFAULT_GEMINI_MODEL,
        model_required=False,
    ),
    "openrouter": _ProviderSpec(
        key_vars=("OPENROUTER_API_KEY",),
        model_vars=("OPENROUTER_MODEL",),
        default_model="",
        model_required=True,
    ),
    "agentrouter": _ProviderSpec(
        key_vars=("AGENTROUTER_API_KEY", "INVESTIGATOR_API_KEY", "VERIFIER_API_KEY"),
        model_vars=("AGENTROUTER_MODEL",),
        default_model="",
        model_required=True,
    ),
}

_TRUTHY = ("1", "true", "yes", "on")


def normalize_provider(provider: Optional[str]) -> str:
    """Lowercases, trims, and resolves aliases for a provider name."""
    name = (provider or "").strip().lower()
    return _PROVIDER_ALIASES.get(name, name)


def _first_env(*names: str) -> str:
    """Returns the first non-empty environment value among ``names``."""
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def is_demo_mode_forced() -> bool:
    """
    Reports whether demo mode was explicitly requested via ``DEMO_MODE``.

    Separate from ``LLM_PROVIDER=demo`` so that "deliberately offline" and
    "no provider configured" stop being the same value.
    """
    return (os.getenv("DEMO_MODE") or "").strip().lower() in _TRUTHY


@dataclass(frozen=True)
class RoleResolution:
    """Resolved provider configuration for a single agent role."""

    role: str
    provider: str
    api_key: str
    model: str
    #: Provider the configuration asked for, before any fallback to demo.
    requested_provider: str
    #: True when ``requested_provider`` could not be honoured.
    degraded: bool = False
    degraded_reason: Optional[str] = None

    @property
    def is_demo(self) -> bool:
        return self.provider == DEMO

    @property
    def env_prefix(self) -> str:
        """Role-scoped environment variable prefix, e.g. ``INVESTIGATOR``."""
        return self.role.upper()


@dataclass(frozen=True)
class ProviderResolution:
    """Resolved configuration for both agent roles plus how it was arrived at."""

    investigator: RoleResolution
    verifier: RoleResolution
    #: Base provider after fallback, used for logging and CLI defaults.
    base_provider: str
    #: True when demo mode was explicitly requested rather than fallen back to.
    demo_explicit: bool

    @property
    def roles(self) -> Tuple[RoleResolution, RoleResolution]:
        return (self.investigator, self.verifier)

    @property
    def degraded(self) -> bool:
        """True when either role fell back to demo despite asking for a real provider."""
        return any(r.degraded for r in self.roles)

    @property
    def degraded_reasons(self) -> Tuple[str, ...]:
        return tuple(r.degraded_reason for r in self.roles if r.degraded_reason)

    @property
    def is_demo(self) -> bool:
        """True when neither role will contact a real provider."""
        return all(r.is_demo for r in self.roles)

    @property
    def provider_label(self) -> str:
        """
        Combined provider name for run metadata.

        Reports ``inv+ver`` when the roles differ, so a mixed run is not
        misrecorded under a single provider name.
        """
        inv, ver = self.investigator.provider, self.verifier.provider
        return inv if inv == ver else f"{inv}+{ver}"


def resolve_base_provider(provider: Optional[str] = None) -> str:
    """
    Resolves the base provider used as a fallback for roles that do not name one.

    Unlike the previous implementation this does not decide whether a run is
    live -- it only supplies a default. An empty result means "no base
    configured", which lets each role fall back to credential inference rather
    than being forced to demo.
    """
    explicit = normalize_provider(provider)
    if explicit:
        return explicit
    return normalize_provider(os.getenv("LLM_PROVIDER"))


def _infer_provider_from_credentials(role: str) -> str:
    """
    Picks a provider from whatever credentials are present, for setups that
    supply keys without naming a provider.

    Ordered most-specific first: a role-scoped key paired with a role-scoped
    model is the strongest signal, then shared per-provider keys.
    """
    role_key = _first_env(f"{role.upper()}_API_KEY")
    role_model = _first_env(f"{role.upper()}_MODEL")
    if role_key and role_model:
        # A role key + model with no provider named is ambiguous between the
        # OpenAI-compatible gateways; OpenRouter is the documented default.
        return "openrouter"

    for candidate in ("openrouter", "gemini"):
        spec = _PROVIDER_SPECS[candidate]
        if not _first_env(*spec.key_vars):
            continue
        if spec.model_required and not _first_env(*spec.model_vars):
            continue
        return candidate
    return ""


def resolve_role(
    role: str,
    base_provider: str = "",
    provider_override: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    demo_forced: bool = False,
) -> RoleResolution:
    """
    Resolves one role's provider, key, and model independently of the other role.

    Resolution order for the provider: explicit ``provider_override`` argument,
    then ``{ROLE}_PROVIDER``, then ``base_provider`` (``LLM_PROVIDER``), then
    inference from available credentials, then demo.

    Args:
        role: ``"investigator"`` or ``"verifier"``; also the env var prefix.
        base_provider: Fallback provider when the role names none.
        provider_override: Caller-supplied provider, wins over environment.
        api_key: Caller-supplied key, wins over environment.
        model: Caller-supplied model, wins over environment.
        demo_forced: Short-circuits to demo (explicit request from the caller).

    Returns:
        A ``RoleResolution``. Never raises for missing credentials -- it reports
        ``degraded=True`` with a reason so callers can warn and continue.
    """
    prefix = role.upper()

    if demo_forced:
        return RoleResolution(
            role=role, provider=DEMO, api_key="", model=DEMO, requested_provider=DEMO
        )

    requested = normalize_provider(provider_override) or normalize_provider(
        os.getenv(f"{prefix}_PROVIDER")
    )
    inferred_from_credentials = False
    if not requested:
        requested = normalize_provider(base_provider)
    if not requested:
        requested = _infer_provider_from_credentials(role)
        inferred_from_credentials = bool(requested)
    if not requested:
        # Nothing configured anywhere. Demo is the correct answer, and it is not
        # a degradation because nothing was asked for.
        return RoleResolution(
            role=role, provider=DEMO, api_key="", model=DEMO, requested_provider=DEMO
        )

    if requested == DEMO:
        return RoleResolution(
            role=role, provider=DEMO, api_key="", model=DEMO, requested_provider=DEMO
        )

    if requested not in _PROVIDER_SPECS:
        return RoleResolution(
            role=role,
            provider=DEMO,
            api_key="",
            model=DEMO,
            requested_provider=requested,
            degraded=True,
            degraded_reason=(
                f"{prefix}_PROVIDER/LLM_PROVIDER is set to unsupported provider "
                f"'{requested}'. Valid options are {', '.join(VALID_PROVIDERS)}."
            ),
        )

    spec = _PROVIDER_SPECS[requested]

    resolved_key = (api_key or "").strip()
    if not resolved_key:
        resolved_key = _first_env(f"{prefix}_API_KEY", *spec.key_vars)

    resolved_model = (model or "").strip()
    if not resolved_model:
        resolved_model = _first_env(f"{prefix}_MODEL", *spec.model_vars)
    if not resolved_model and not spec.model_required:
        resolved_model = spec.default_model

    if not resolved_key:
        key_vars = ", ".join((f"{prefix}_API_KEY",) + spec.key_vars)
        return RoleResolution(
            role=role,
            provider=DEMO,
            api_key="",
            model=DEMO,
            requested_provider=requested,
            degraded=True,
            degraded_reason=(
                f"{role.capitalize()} requested provider '{requested}' but no API key "
                f"is configured. Set one of: {key_vars}."
            ),
        )

    if not resolved_model:
        model_vars = ", ".join((f"{prefix}_MODEL",) + spec.model_vars)
        return RoleResolution(
            role=role,
            provider=DEMO,
            api_key="",
            model=DEMO,
            requested_provider=requested,
            degraded=True,
            degraded_reason=(
                f"{role.capitalize()} requested provider '{requested}' but no model is "
                f"configured and it has no default. Set one of: {model_vars}."
            ),
        )

    if inferred_from_credentials:
        logger.info(
            "%s provider not set; inferred '%s' from available credentials. "
            "Set %s_PROVIDER or LLM_PROVIDER to make this explicit.",
            role.capitalize(),
            requested,
            prefix,
        )

    return RoleResolution(
        role=role,
        provider=requested,
        api_key=resolved_key,
        model=resolved_model,
        requested_provider=requested,
    )


def resolve_providers(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    investigator_provider: Optional[str] = None,
    verifier_provider: Optional[str] = None,
    investigator_model: Optional[str] = None,
    verifier_model: Optional[str] = None,
    warn: bool = True,
) -> ProviderResolution:
    """
    Resolves Investigator and Verifier configuration in one place.

    Args:
        provider: Base provider override (e.g. an API form field). ``"demo"``
            forces demo mode for both roles.
        api_key: Base key applied to a role only when that role resolves to the
            same provider as ``provider``, so a key for one provider is never
            handed to a different one.
        investigator_provider: Explicit Investigator provider override.
        verifier_provider: Explicit Verifier provider override.
        investigator_model: Explicit Investigator model override.
        verifier_model: Explicit Verifier model override.
        warn: Emit a WARNING for each role that degraded to demo. Callers doing
            a silent preflight can disable it to avoid duplicate log lines.

    Returns:
        A ``ProviderResolution`` describing both roles.
    """
    import sys
    if "pytest" not in sys.modules:
        try:
            from dotenv import load_dotenv
            load_dotenv(override=True)
        except Exception:
            pass

    explicit_base = normalize_provider(provider)
    base = resolve_base_provider(provider)

    # Demo is a hard kill switch, not merely a fallback: an explicit request for
    # it overrides role-level providers entirely. Without this, role overrides
    # left in the environment would quietly re-enable live API calls for a caller
    # that asked for offline operation.
    demo_forced = is_demo_mode_forced() or explicit_base == DEMO or base == DEMO

    roles = {}
    for role, role_override, role_model in (
        ("investigator", investigator_provider, investigator_model),
        ("verifier", verifier_provider, verifier_model),
    ):
        # Provisionally resolve without the shared key to learn which provider
        # the role lands on; only pass the shared key through when it belongs to
        # that provider.
        provisional = resolve_role(
            role=role,
            base_provider=base,
            provider_override=role_override,
            model=role_model,
            demo_forced=demo_forced,
        )
        shared_key = api_key if (api_key and provisional.requested_provider == explicit_base) else None
        roles[role] = (
            provisional
            if not shared_key
            else resolve_role(
                role=role,
                base_provider=base,
                provider_override=role_override,
                api_key=shared_key,
                model=role_model,
                demo_forced=demo_forced,
            )
        )

    resolution = ProviderResolution(
        investigator=roles["investigator"],
        verifier=roles["verifier"],
        base_provider=base or (DEMO if demo_forced else ""),
        demo_explicit=demo_forced,
    )

    if warn:
        warn_on_degradation(resolution)
    return resolution


def warn_on_degradation(resolution: ProviderResolution) -> None:
    """
    Logs a WARNING for every role that silently fell back to the demo engine.

    Deliberately loud: a degraded run still produces AUTO_RESOLVED decisions, so
    an operator who believes a real model reviewed them has no other signal.
    """
    for role in resolution.roles:
        if role.degraded:
            logger.warning(
                "LLM provider degraded to DEMO for %s: %s Decisions will come from the "
                "offline rule-based emulator, not a real model.",
                role.role.capitalize(),
                role.degraded_reason,
            )


def format_resolution_banner(resolution: ProviderResolution) -> str:
    """Renders the startup configuration banner for CLI and server logs."""
    lines = [
        "=" * 40,
        "Multi-Agent Configuration",
    ]
    for role in resolution.roles:
        lines.append(f"{role.role.capitalize()}:")
        lines.append(f"  Provider: {role.provider}")
        lines.append(f"  Model: {role.model}")
        if role.degraded:
            lines.append(f"  [!] DEGRADED from '{role.requested_provider}': {role.degraded_reason}")
    if resolution.is_demo and resolution.demo_explicit:
        lines.append("Mode: DEMO (explicitly requested)")
    elif resolution.is_demo:
        lines.append("Mode: DEMO (no usable provider credentials)")
    lines.append("=" * 40)
    return "\n".join(lines)


def role_credentials_present(
    role: str,
    provider_override: Optional[str] = None,
    base_provider: str = "",
) -> bool:
    """
    Preflight check: can this role be constructed against a real provider?

    Kept as a thin wrapper over ``resolve_role`` so the API preflight and the
    controllers can never disagree about what counts as configured.
    """
    resolved = resolve_role(
        role=role, base_provider=base_provider, provider_override=provider_override
    )
    return not resolved.degraded


def build_role_clients(resolution: ProviderResolution, llm_client_factory: Any) -> Tuple[Any, Any]:
    """
    Instantiates the Investigator and Verifier clients from a resolution.

    Takes the factory as an argument to avoid importing src.agent.controller here
    (it imports this module).
    """
    clients = []
    for role in resolution.roles:
        clients.append(
            llm_client_factory(
                provider=role.provider,
                api_key=role.api_key or None,
                model=role.model,
            )
        )
    return clients[0], clients[1]
