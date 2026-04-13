#!/usr/bin/env python3
"""
RLM REPL Tool -- Run Recursive Language Model completions from Hermes agent.

Wraps the RLM library (rlms fork) so the agent can invoke RLM completions
as a tool call. RLM uses a REPL-based iterative approach where the model
writes and executes code, enabling recursive sub-calls for complex tasks.

Requires:
  - The rlms package (installed from /root/.hermes/hermes-agent/rlm-fork)
  - NOUS_API_KEY or OPENROUTER_API_KEY environment variable
"""

import json
import logging
import os
import time
from pathlib import Path

from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)


# =============================================================================
# API key resolution
# =============================================================================

def _resolve_nous_api_key() -> str | None:
    """Read the Nous agent key from auth.json (minted by portal OAuth)."""
    auth_path = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "auth.json"
    if not auth_path.exists():
        return None
    try:
        with open(auth_path) as f:
            auth = json.load(f)
        return auth.get("providers", {}).get("nous", {}).get("agent_key")
    except (json.JSONDecodeError, OSError):
        return None


def _resolve_api_key(base_url: str | None) -> str | None:
    """Resolve the API key for the given endpoint."""
    if base_url is None or "nousresearch" in str(base_url):
        # Nous portal auth
        key = _resolve_nous_api_key()
        if key:
            return key
        # Fallback to env var
        return os.environ.get("NOUS_API_KEY")
    elif "openrouter" in str(base_url):
        return os.environ.get("OPENROUTER_API_KEY")
    return None


# =============================================================================
# RLM configuration defaults
# =============================================================================

_DEFAULT_MODEL = "xiaomi/mimo-v2-pro"
_DEFAULT_BACKEND = "hermes"
_DEFAULT_BASE_URL = None  # None = Nous inference API (HermesClient default)
_DEFAULT_MAX_DEPTH = 2
_DEFAULT_MAX_ITERATIONS = 15
_DEFAULT_MAX_TIMEOUT = 300  # seconds
_DEFAULT_ENVIRONMENT = "local"


# =============================================================================
# Availability check
# =============================================================================

def check_rlm_requirements() -> bool:
    """RLM tool requires the rlms package and an API key."""
    try:
        from rlm import RLM  # noqa: F401
    except ImportError:
        return False
    # Check for Nous agent key in auth.json
    if _resolve_nous_api_key():
        return True
    # Check env vars
    if os.environ.get("NOUS_API_KEY") or os.environ.get("OPENROUTER_API_KEY"):
        return True
    return False


# =============================================================================
# Tool handler
# =============================================================================

def rlm_repl_tool(args: dict, **kwargs) -> str:
    """
    Run an RLM completion on the given prompt.

    Args (from the tool call):
        prompt: The task/question for RLM to solve (required).
        model: Model name (default: xiaomi/mimo-v2-pro).
        base_url: "nous", "openrouter", or a full URL (default: nous).
        max_depth: Maximum recursion depth (default: 2).
        max_iterations: Maximum REPL iterations (default: 15).
        max_timeout: Timeout in seconds (default: 300).
        max_budget: Max cost in USD (optional).
        environment: RLM environment type (default: "local").

    Returns:
        JSON string with the RLM response and metadata.
    """
    prompt = args.get("prompt")
    if not prompt or not str(prompt).strip():
        return tool_error("prompt is required and must not be empty")

    model = args.get("model", _DEFAULT_MODEL)
    base_url = args.get("base_url", _DEFAULT_BASE_URL)
    max_depth = args.get("max_depth", _DEFAULT_MAX_DEPTH)
    max_iterations = args.get("max_iterations", _DEFAULT_MAX_ITERATIONS)
    max_timeout = args.get("max_timeout", _DEFAULT_MAX_TIMEOUT)
    max_budget = args.get("max_budget")
    environment = args.get("environment", _DEFAULT_ENVIRONMENT)

    try:
        from rlm import RLM
    except ImportError:
        return tool_error(
            "RLM package not installed. Install with: pip install -e /root/.hermes/hermes-agent/rlm-fork"
        )

    # Build backend kwargs
    backend_kwargs = {"model_name": model}
    if base_url:
        backend_kwargs["base_url"] = base_url

    # Resolve API key from auth.json or env vars
    api_key = _resolve_api_key(base_url)
    if api_key:
        backend_kwargs["api_key"] = api_key

    try:
        rlm_instance = RLM(
            backend=_DEFAULT_BACKEND,
            backend_kwargs=backend_kwargs,
            environment=environment,
            max_depth=max_depth,
            max_iterations=max_iterations,
            max_timeout=max_timeout,
            max_budget=max_budget,
            verbose=False,
        )

        start_time = time.perf_counter()
        result = rlm_instance.completion(str(prompt))
        elapsed = time.perf_counter() - start_time

        # Build response
        response_data = {
            "response": result.response,
            "model": model,
            "execution_time": round(elapsed, 2),
            "iterations": (
                result.metadata.total_iterations if result.metadata else None
            ),
        }

        # Include usage summary if available
        if result.usage_summary:
            usage = result.usage_summary
            response_data["usage"] = {
                "total_cost": usage.total_cost,
                "total_input_tokens": usage.total_input_tokens,
                "total_output_tokens": usage.total_output_tokens,
            }

        return tool_result(response_data)

    except Exception as e:
        logger.exception("RLM completion failed")
        return tool_error(f"RLM completion failed: {type(e).__name__}: {e}")


# =============================================================================
# OpenAI Function-Calling Schema
# =============================================================================

RLM_REPL_SCHEMA = {
    "name": "rlm_repl",
    "description": (
        "Run a Recursive Language Model (RLM) completion. RLM uses an iterative "
        "REPL approach where the model writes and executes Python code, and can "
        "make recursive sub-calls to break complex problems into smaller parts. "
        "Use this for complex reasoning, multi-step computation, or tasks that "
        "benefit from code execution and iterative refinement.\n\n"
        "Examples: mathematical proofs, algorithm implementation, data analysis, "
        "multi-step reasoning tasks, recursive problem decomposition."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The task or question for RLM to solve. Be specific and detailed.",
            },
            "model": {
                "type": "string",
                "description": f"Model to use (default: {_DEFAULT_MODEL}).",
                "default": _DEFAULT_MODEL,
            },
            "base_url": {
                "type": "string",
                "description": (
                    "API endpoint: 'nous' (default), 'openrouter', or a full URL."
                ),
                "default": "nous",
            },
            "max_depth": {
                "type": "integer",
                "description": (
                    f"Max recursion depth for sub-calls (default: {_DEFAULT_MAX_DEPTH}). "
                    "Higher values allow more nested decomposition but cost more."
                ),
                "default": _DEFAULT_MAX_DEPTH,
            },
            "max_iterations": {
                "type": "integer",
                "description": (
                    f"Max REPL iterations (default: {_DEFAULT_MAX_ITERATIONS})."
                ),
                "default": _DEFAULT_MAX_ITERATIONS,
            },
            "max_timeout": {
                "type": "number",
                "description": (
                    f"Timeout in seconds (default: {_DEFAULT_MAX_TIMEOUT})."
                ),
                "default": _DEFAULT_MAX_TIMEOUT,
            },
            "max_budget": {
                "type": "number",
                "description": "Maximum cost in USD (optional, no limit if omitted).",
            },
            "environment": {
                "type": "string",
                "description": (
                    f"RLM environment type (default: '{_DEFAULT_ENVIRONMENT}')."
                ),
                "default": _DEFAULT_ENVIRONMENT,
            },
        },
        "required": ["prompt"],
    },
}


# =============================================================================
# Registry
# =============================================================================

registry.register(
    name="rlm_repl",
    toolset="rlm_repl",
    schema=RLM_REPL_SCHEMA,
    handler=lambda args, **kw: rlm_repl_tool(args, **kw),
    check_fn=check_rlm_requirements,
    emoji="🔄",
    description="Run Recursive Language Model completions with code execution and recursive sub-calls",
)
