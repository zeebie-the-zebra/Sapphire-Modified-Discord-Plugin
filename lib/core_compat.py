"""Compatibility shims for Sapphire core APIs used by the Discord daemon.

persona-agents monkey-patches ExecutionContext.run() without an ``images`` kwarg.
Core's continuity executor now calls ``ctx.run(msg, images=...)`` for daemon
event images. We wrap the active run() and, for non-delegate tasks, call
``_run_inner`` directly so images always reach the vision pipeline.
"""

import inspect
import logging

logger = logging.getLogger(__name__)


def ensure_execution_context_images_support():
    """Make ExecutionContext.run accept plugin event images (idempotent)."""
    try:
        from core.continuity.execution_context import ExecutionContext, current_task_persona
    except Exception as e:
        logger.warning(f"[DISCORD] ExecutionContext import failed: {e}")
        return

    current = ExecutionContext.run
    if getattr(current, "__name__", "") == "_discord_images_run":
        return

    try:
        if "images" in inspect.signature(current).parameters:
            return
    except (TypeError, ValueError):
        pass

    persona_run = current

    def _discord_images_run(self, user_input, history_messages=None, images=None):
        # persona-agents delegates use their own patched loop — leave unchanged.
        if getattr(self, "_persona_agent", False):
            return persona_run(self, user_input, history_messages)

        # Discord daemon tasks: bypass persona's patch and use core's image path.
        from core.chat.chat import filter_to_thinking_only, _inject_tool_images

        _persona_token = current_task_persona.set(self.task_settings.get("prompt"))
        try:
            return self._run_inner(
                user_input,
                history_messages,
                filter_to_thinking_only,
                _inject_tool_images,
                images,
            )
        finally:
            current_task_persona.reset(_persona_token)

    _discord_images_run.__name__ = "_discord_images_run"
    ExecutionContext.run = _discord_images_run
    logger.info("[DISCORD] ExecutionContext.run upgraded for event image support")
