"""Sync Discord auto-reply LLM context settings with Sapphire core."""

import logging

logger = logging.getLogger(__name__)

PREFERRED_AUTOREPLY_TASK_ID = "discord-remmi-autoreply"


def find_autoreply_task(scheduler):
    """Return the Schedule daemon task that handles discord_message auto-replies."""
    if not scheduler:
        return None
    preferred = scheduler.get_task(PREFERRED_AUTOREPLY_TASK_ID)
    if preferred and _is_discord_autoreply_task(preferred):
        return preferred
    for task in scheduler.list_tasks():
        if _is_discord_autoreply_task(task):
            return task
    return None


def _is_discord_autoreply_task(task: dict) -> bool:
    if not isinstance(task, dict):
        return False
    if task.get("type") != "daemon":
        return False
    trigger = task.get("trigger_config") or {}
    if trigger.get("source") != "discord_message":
        return False
    return bool(task.get("auto_reply") or trigger.get("auto_reply"))


def read_reply_context_settings():
    """Read live LLM_MAX_HISTORY and Discord Bot Reply task context_limit."""
    from core.settings_manager import settings

    llm_max_history = int(settings.get("LLM_MAX_HISTORY", 0) or 0)

    reply_context_limit = 0
    reply_task_id = ""
    reply_task_name = ""
    reply_task_linked = False

    try:
        from core.api_fastapi import get_system

        system = get_system()
        scheduler = getattr(system, "continuity_scheduler", None)
        task = find_autoreply_task(scheduler)
        if task:
            reply_task_linked = True
            reply_task_id = str(task.get("id") or "")
            reply_task_name = str(task.get("name") or "")
            reply_context_limit = int(task.get("context_limit") or 0)
    except Exception as e:
        logger.debug(f"[LEONA-DISCORD] Could not read autoreply task context_limit: {e}")

    return {
        "llm_max_history": llm_max_history,
        "reply_context_limit": reply_context_limit,
        "reply_task_linked": reply_task_linked,
        "reply_task_id": reply_task_id,
        "reply_task_name": reply_task_name,
    }


def apply_reply_context_settings(llm_max_history=None, reply_context_limit=None):
    """
    Persist LLM_MAX_HISTORY globally and context_limit on the Discord autoreply task.

    Returns (ok: bool, warnings: list[str]).
    """
    warnings = []

    if llm_max_history is not None:
        try:
            val = max(0, min(500, int(llm_max_history)))
        except (TypeError, ValueError):
            return False, ["LLM max history must be a number (0–500)."]
        from core.settings_manager import settings

        settings.set("LLM_MAX_HISTORY", val, persist=True)
        logger.info(f"[LEONA-DISCORD] Set LLM_MAX_HISTORY={val}")

    if reply_context_limit is not None:
        try:
            val = max(0, min(200000, int(reply_context_limit)))
        except (TypeError, ValueError):
            return False, ["Reply context limit must be a number (0–200000)."]
        try:
            from core.api_fastapi import get_system

            system = get_system()
            scheduler = getattr(system, "continuity_scheduler", None)
            task = find_autoreply_task(scheduler)
            if not task:
                warnings.append(
                    "No Discord auto-reply Schedule task found — context limit saved here "
                    "but not applied. Create or enable a discord_message daemon task with auto-reply."
                )
            else:
                scheduler.update_task(task["id"], {"context_limit": val})
                logger.info(
                    f"[LEONA-DISCORD] Set context_limit={val} on task "
                    f"{task.get('name')!r} ({task.get('id')})"
                )
        except Exception as e:
            logger.error(f"[LEONA-DISCORD] Failed to update autoreply context_limit: {e}")
            return False, [f"Could not update Schedule task context limit: {e}"]

    return True, warnings
