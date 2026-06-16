"""Message gate evaluation — who gets a reply, who gets a reaction."""

import random

from plugins.leona_discord.lib.cooldowns import is_cooldown_active, is_reaction_cooldown_active, set_cooldown

# Organic messages: react but skip the reply (~"saw it, didn't answer")
READ_ONLY_REACT_CHANCE = 0.05


def _keyword_matched(content: str, keywords: list) -> bool:
    if not keywords or not content:
        return False
    lower = content.lower()
    return any(k in lower for k in keywords if k)


def _name_matched(content: str, bot_names: set, case_sensitive: bool) -> bool:
    if not content or not bot_names:
        return False
    if case_sensitive:
        return any(n in content for n in bot_names)
    lower = content.lower()
    return any(n.lower() in lower for n in bot_names)


def _role_trigger(message, always_respond_role_ids: list) -> bool:
    if not always_respond_role_ids or not message.guild:
        return False
    ids = set(always_respond_role_ids)
    for role in getattr(message, "role_mentions", []) or []:
        if str(role.id) in ids:
            return True
    member = getattr(message, "author", None)
    if member and hasattr(member, "roles"):
        for role in member.roles:
            if str(role.id) in ids:
                return True
    return False


def check_user_access(author_id: str, is_bot: bool, settings: dict) -> tuple:
    """Return (allowed, reason). Mentions bypass is handled separately."""
    deny = set(settings.get("user_denylist") or [])
    if author_id in deny:
        return False, "user_denylist"

    allow = settings.get("user_allowlist") or []
    if allow and author_id not in set(allow):
        return False, "user_allowlist"

    if is_bot:
        if settings.get("ignore_bots", False):
            bot_allow = set(settings.get("bot_allowlist") or [])
            if author_id not in bot_allow:
                return False, "ignore_bots"
    return True, ""


def should_queue_reply(
    *,
    settings: dict,
    mentioned: bool,
    name_matched: bool,
    keyword_matched: bool,
    role_trigger: bool,
    is_bot: bool,
    scope: str,
    account: str,
    guild_id: str,
    channel_id: str,
    has_images: bool = False,
    trace=None,
) -> tuple:
    """Return (queue: bool, outcome_if_false: str)."""
    reply_mode = settings.get("reply_mode", "default")

    if reply_mode == "never":
        if trace:
            trace.gate("reply_mode", False, "never")
        return False, "dropped_reply_mode_never"

    if reply_mode == "reactions_only":
        if trace:
            trace.gate("reply_mode", False, "reactions_only")
        return False, "dropped_reply_mode_reactions_only"

    force = mentioned or role_trigger
    # Name/keyword only — images must not bypass mention-only or zero-chance overrides.
    soft = name_matched or keyword_matched

    if reply_mode == "mentions_only" and not force and not soft:
        if trace:
            trace.gate("reply_mode", False, "mentions_only")
        return False, "dropped_reply_mode_mentions_only"

    if mentioned and is_bot:
        return _roll_chance(
            settings.get("bot_response_chance", 15),
            "bot_mention_chance",
            "dropped_bot_mention_zero",
            "dropped_bot_mention_chance",
            trace,
        )

    if not mentioned and not soft and not role_trigger:
        if is_bot:
            return _roll_chance(
                settings.get("bot_response_chance", 15),
                "bot_message_chance",
                "dropped_bot_zero",
                "dropped_bot_chance",
                trace,
            )

        if not name_matched and not keyword_matched:
            if trace:
                trace.gate("name_match", False)
                trace.gate("keyword_match", False)

            human_chance = max(0, min(100, int(settings.get("human_response_chance", 15))))
            # Attachments only roll the random-chance path in default mode with chance > 0.
            if has_images and (reply_mode != "default" or human_chance == 0):
                if trace:
                    trace.gate("has_images", False, "images do not bypass reply restrictions")
                return False, "dropped_image_restricted"

            cooldown_secs = float(settings.get("cooldown_seconds", 120))
            if is_cooldown_active(scope, account, guild_id, channel_id, cooldown_secs):
                if trace:
                    trace.gate("cooldown", False, f"{cooldown_secs}s active")
                return False, "dropped_cooldown"
            if trace:
                trace.gate("cooldown", True)
            if has_images and trace:
                trace.gate("has_images", True, "image/GIF attachment present")
            return _roll_chance(
                human_chance,
                "human_response_chance",
                "dropped_human_zero",
                "dropped_human_chance",
                trace,
            )

    if trace:
        if name_matched:
            trace.gate("name_match", True)
        if keyword_matched:
            trace.gate("keyword_match", True)
        if role_trigger:
            trace.gate("role_trigger", True)
        if has_images:
            trace.gate("has_images", True, "image/GIF attachment present")
        if mentioned:
            trace.gate("mentioned", True, "direct @mention or role mention")

    return True, ""


def _roll_chance(chance, gate_name, zero_outcome, fail_outcome, trace) -> tuple:
    chance = max(0, min(100, int(chance)))
    if chance == 0:
        if trace:
            trace.gate(gate_name, False, "chance=0")
        return False, zero_outcome
    if chance < 100 and random.random() >= (chance / 100.0):
        if trace:
            trace.gate(gate_name, False, f"roll failed ({chance}%)")
        return False, fail_outcome
    if trace:
        trace.gate(gate_name, True)
    return True, ""


def evaluate_triggers(message, client, settings: dict) -> dict:
    """Compute mention/name/keyword/role flags for a Discord message."""
    mentioned = client.user in message.mentions
    if not mentioned and message.guild and message.role_mentions:
        bot_member = message.guild.get_member(client.user.id)
        if bot_member:
            mentioned = any(role in bot_member.roles for role in message.role_mentions)

    bot_names = {client.user.display_name, client.user.name}
    content = message.clean_content or ""
    name_matched = False
    if settings.get("name_match_enabled", True):
        name_matched = _name_matched(
            content,
            bot_names,
            settings.get("name_match_case_sensitive", False),
        )
    keyword_matched = _keyword_matched(content, settings.get("keyword_triggers") or [])
    role_trigger = _role_trigger(message, settings.get("always_respond_role_ids") or [])

    return {
        "mentioned": mentioned,
        "name_matched": name_matched,
        "keyword_matched": keyword_matched,
        "role_trigger": role_trigger,
    }


def mark_reply_cooldown(settings: dict, account: str, guild_id: str, channel_id: str):
    if settings.get("cooldown_seconds", 0) <= 0:
        return
    scope = settings.get("cooldown_scope", "per_channel")
    set_cooldown(scope, account, guild_id, channel_id)


def should_read_only_react() -> bool:
    """Roll whether to react without queueing a text reply."""
    return random.random() < READ_ONLY_REACT_CHANCE


def reaction_allowed(settings: dict, account: str, guild_id: str, channel_id: str) -> bool:
    if not settings.get("reactions_enabled", False):
        return False
    if settings.get("reply_mode") == "never" and settings.get("quiet_hours_mode") == "silent":
        return False
    cooldown = float(settings.get("reaction_cooldown_seconds", 30))
    if is_reaction_cooldown_active(account, guild_id, channel_id, cooldown):
        return False
    return True
