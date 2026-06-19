"""Manual forced-wake test from settings UI."""

import logging
import time
import uuid

from plugins.leona_discord.lib.schedule_utils import parse_target, resolve_names

logger = logging.getLogger(__name__)

_TEST_MENTION = "(Settings UI test @mention — why did you wake me?)"


def run_forced_wake_test(raw: dict, *, test: bool = False) -> str:
    """Queue a synthetic @mention reply while channels are in forced-wake mode.

    When test=True, bypasses sleep/forced-wake enabled toggles (for the settings UI).
    Requires an active Discord Bot Reply Schedule task with auto-reply enabled.
    """
    from plugins.leona_discord.lib.events import build_event_payload, emit_event
    from plugins.leona_discord.lib.history import append_message
    from plugins.leona_discord.lib.sleep_forced_wake import (
        build_forced_wake_hint,
        enter_forced_wake,
        wrap_forced_wake_content,
    )
    from plugins.leona_discord.lib.sleep_schedule import enter_sleep
    from plugins.leona_discord.lib import state

    raw = raw or {}
    g = raw.get("global", {}) or {}

    if not test and not g.get("sleep_forced_wake_enabled", False):
        return "Skipped (forced wake disabled)"

    if g.get("sleep_use_greeting_targets", True):
        target_entries = g.get("greeting_targets") or []
    else:
        target_entries = g.get("sleep_targets") or []

    targets = []
    for entry in target_entries:
        parsed = parse_target(entry)
        if parsed:
            targets.append(parsed)

    if not targets:
        return "Skipped (no sleep/greeting channels selected)"

    queued = 0
    errors = []

    for account, guild_id, channel_id in targets:
        try:
            guild_name, channel_name = resolve_names(account, guild_id, channel_id)
            enter_sleep(account, channel_id)
            enter_forced_wake(account, channel_id, g)

            wake_hint = build_forced_wake_hint(just_woke=True)
            wrapped = wrap_forced_wake_content(_TEST_MENTION, wake_hint)
            message_id = f"test-forced-wake-{int(time.time())}-{uuid.uuid4().hex[:8]}"

            channel_key = state.channel_key(account, channel_id)
            append_message(
                channel_key,
                {
                    "message_id": message_id,
                    "content": wrapped,
                    "clean_content": wrapped,
                    "username": "settings_test",
                    "display_name": "Settings Test",
                    "author_id": "0",
                    "mentioned": "True",
                    "image_urls": [],
                },
                guild_id=guild_id,
            )

            payload = build_event_payload(
                account=account,
                guild_id=guild_id,
                guild_name=guild_name,
                channel_id=channel_id,
                channel_name=channel_name,
                message_id=message_id,
                author_id="0",
                username="settings_test",
                display_name="Settings Test",
                content=wrapped,
                mentioned=True,
                image_urls=[],
                reply_to_message_id="",
            )
            payload["sleep_forced_wake"] = True
            payload["trigger_content"] = _TEST_MENTION

            if emit_event(payload):
                queued += 1
                logger.info(
                    f"[LEONA-DISCORD] Forced-wake test queued for "
                    f"#{channel_name or channel_id}"
                )
            else:
                errors.append(f"{account}:{channel_id}:no_task")
        except Exception as e:
            errors.append(str(e))

    if queued <= 0:
        summary = "Skipped (no task accepted — enable Discord Bot Reply with auto-reply)"
    else:
        summary = f"Queued forced-wake test reply for {queued} channel(s)"
    if errors:
        summary += f"; issues: {', '.join(errors[:5])}"
    logger.info(f"[LEONA-DISCORD] Forced-wake test: {summary}")
    return summary
