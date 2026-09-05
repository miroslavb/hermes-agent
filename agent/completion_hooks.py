"""Bounded completion policy for both native and delegated conversation turns."""
import logging

logger = logging.getLogger(__name__)


def completion_continue_message(agent, *, turn_id="", user_message="", final_response="", attempt=0):
    """One optional continuation, including turns with no file mutations.

    Advisory, local plugin policy; a missing or failed hook adds no extra call.
    The host still owns interrupts, iteration budgets and durable transcripts.
    """
    if attempt >= 1 or getattr(agent, "_interrupt_requested", False):
        return None
    try:
        from hermes_cli.lifecycle import invoke_hook, has_hook
        if not has_hook("pre_turn_complete"):
            return None
        results = invoke_hook(
            "pre_turn_complete", session_id=getattr(agent, "session_id", ""),
            turn_id=turn_id, user_message=user_message,
            final_response=final_response, attempt=attempt,
            changed_paths=sorted(getattr(agent, "_turn_file_mutation_paths", set()) or []),
            platform=getattr(agent, "platform", "") or "",
            model=getattr(agent, "model", ""),
        )
        for result in results:
            if isinstance(result, dict) and result.get("action") == "continue":
                message = result.get("message")
                if isinstance(message, str) and message.strip():
                    return message[:8000]
    except Exception:
        logger.warning("pre_turn_complete hook failed", exc_info=True)
    return None
