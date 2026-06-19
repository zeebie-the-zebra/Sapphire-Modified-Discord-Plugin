# plugins/leona_discord/tools/discord_tools.py — Discord tools for the LLM
#
# Account is read from scope_discord ContextVar (set via sidebar dropdown).
# Channel can be specified by name (e.g. "general-bot-chat") or ID.
# In daemon context, channel defaults to the one that triggered the event.

import asyncio
import logging
import threading
from contextvars import ContextVar
from datetime import datetime, timezone

from plugins.leona_discord.lib.messages import split_message as _split_long_message

logger = logging.getLogger(__name__)

ENABLED = True
EMOJI = "🎮"

# Set by executor when processing a daemon event — auto-reply target
_reply_channel_id  = ContextVar('discord_reply_channel_id',  default=None)
_reply_message_id  = ContextVar('discord_reply_message_id',  default=None)
_reply_guild_id    = ContextVar('discord_reply_guild_id',     default=None)
# Legacy flag — send-count is the primary double-post guard in reply_handler
_message_sent      = ContextVar('discord_message_sent',       default=False)

_tool_sent_events: set = set()
_tool_sent_text: dict = {}
_tool_sent_events_lock = threading.Lock()
_TOOL_SENT_MAX = 500

_gif_sent_events: set = set()
_gif_sent_events_lock = threading.Lock()


def mark_tool_sent(message_id: str, text: str = ""):
    """Record that a tool already sent a message for this event."""
    mid = str(message_id)
    with _tool_sent_events_lock:
        if len(_tool_sent_events) >= _TOOL_SENT_MAX:
            to_evict = list(_tool_sent_events)[:_TOOL_SENT_MAX // 2]
            for k in to_evict:
                _tool_sent_events.discard(k)
                _tool_sent_text.pop(k, None)
        _tool_sent_events.add(mid)
        if text:
            _tool_sent_text[mid] = text[:4000]


def pop_tool_sent_text(message_id: str) -> str:
    """Return and clear text sent by discord_send_message for this event."""
    with _tool_sent_events_lock:
        return _tool_sent_text.pop(str(message_id), "")


def was_tool_sent(message_id: str) -> bool:
    """Check if a tool already sent a message for this event."""
    with _tool_sent_events_lock:
        return str(message_id) in _tool_sent_events


def clear_tool_sent(message_id: str):
    """Remove the marker after the reply handler has processed this event."""
    mid = str(message_id)
    with _tool_sent_events_lock:
        _tool_sent_events.discard(mid)
        _tool_sent_text.pop(mid, None)


def _task_auto_reply_enabled() -> bool:
    """True when the active daemon task will auto-reply to the trigger channel."""
    try:
        from core.continuity.executor import current_event_task
        task = current_event_task.get() or {}
    except ImportError:
        return False
    trigger = task.get("trigger_config") or {}
    return bool(task.get("auto_reply") or trigger.get("auto_reply"))


def _is_trigger_channel(channel) -> bool:
    event = _get_daemon_event()
    trigger_ch = str(event.get("channel_id") or _reply_channel_id.get() or "").strip()
    return bool(trigger_ch and str(getattr(channel, "id", "")) == trigger_ch)


def mark_gif_sent(message_id: str):
    """Record that discord_send_gif already sent for this event."""
    with _gif_sent_events_lock:
        if len(_gif_sent_events) >= _TOOL_SENT_MAX:
            to_evict = list(_gif_sent_events)[:_TOOL_SENT_MAX // 2]
            for k in to_evict:
                _gif_sent_events.discard(k)
        _gif_sent_events.add(str(message_id))


def was_gif_sent(message_id: str) -> bool:
    with _gif_sent_events_lock:
        return str(message_id) in _gif_sent_events


def clear_gif_sent(message_id: str):
    with _gif_sent_events_lock:
        _gif_sent_events.discard(str(message_id))

# Track the channel last read by discord_read_messages so discord_add_reaction
# can use the correct channel when reacting to a message_id from that read.
# This avoids using the triggering event's channel (ContextVar) when the LLM
# read messages from a different channel and wants to react to one of them.
_last_read_channel_id = None

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "discord_get_servers",
            "description": "List Discord servers (guilds) the bot is in, with their channels.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "discord_read_messages",
            "description": "Read recent messages from a Discord channel. Each message includes a [msg:ID] reference you can use with discord_add_reaction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Channel name or ID. Omit to use the triggering channel."},
                    "count": {"type": "integer", "description": "Number of messages to fetch (default 20, max 50)", "default": 20}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "discord_send_message",
            "description": "Send a message to a Discord channel. Supports optional embed and reply-to. If no channel specified, replies to the triggering channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Channel name or ID. Omit for triggering channel."},
                    "text": {"type": "string", "description": "The message text to send."},
                    "reply_to_message_id": {"type": "string", "description": "Optional message ID to reply to (quotes in Discord)."},
                    "embed_title": {"type": "string", "description": "Optional embed title."},
                    "embed_description": {"type": "string", "description": "Optional embed body (supports markdown)."},
                    "embed_color": {"type": "string", "description": "Optional embed color as hex (#7289DA)."},
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "discord_upload_file",
            "description": "Upload a file to a Discord channel with an optional caption.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to the file on disk."},
                    "channel": {"type": "string", "description": "Channel name or ID. Omit for triggering channel."},
                    "caption": {"type": "string", "description": "Optional message text sent with the file."},
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "discord_send_gif",
            "description": (
                "Search and send an animated GIF to a Discord channel. "
                "Use this when the user asks for a GIF or you want to reply with one. "
                "Do not use web_search/get_website for GIF URLs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Short GIF search terms (e.g. 'leonardo dicaprio clapping', 'celebration').",
                    },
                    "channel": {
                        "type": "string",
                        "description": "Channel name or ID. Omit for triggering channel.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discord_add_reaction",
            "description": "Add an emoji reaction to a Discord message. Use sparingly. If message_id is omitted, it reacts to the triggering message. To react to other messages, get their ID from discord_read_messages first. Unicode emoji always work; server custom emoji must be on the allowed list in plugin settings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "emoji": {
                        "type": "string",
                        "description": "The emoji to react with. Unicode emoji (🔥👍) always work. For server custom emoji use the exact code from settings (e.g. <:BUG:123456>) or short form <:BUG:> — name is resolved automatically."
                    },
                    "message_id": {
                        "type": "string",
                        "description": "Optional message ID. Omit for the current message."
                    }
                },
                "required": ["emoji"]
            }
        }
    }
]

AVAILABLE_FUNCTIONS = {t["function"]["name"] for t in TOOLS}


def _get_account():
    """Resolve bot account from scope, daemon event, or single connected client."""
    from core.chat.function_manager import scope_discord

    acct = scope_discord.get()
    if acct and acct not in ("none", "default", ""):
        return acct

    event = _get_daemon_event()
    event_acct = (event.get("account") or "").strip()
    if event_acct:
        return event_acct

    try:
        from plugins.leona_discord.daemon import list_connected
        connected = list_connected()
        if len(connected) == 1:
            return connected[0]
    except Exception:
        pass

    return None


def _check_ready():
    account = _get_account()
    if not account:
        event = _get_daemon_event()
        if event.get("account"):
            return (
                "Discord scope is disabled for this task (discord_scope is 'none'), "
                "and the daemon event account could not be resolved."
            )
        return "Discord is disabled for this chat. Select an account in the sidebar."
    from plugins.leona_discord.daemon import get_client, get_loop
    client = get_client(account)
    loop = get_loop()
    if not client or not loop:
        return f"Discord bot '{account}' is not connected."
    return (client, loop)


def _header():
    from core.tool_context import context_header
    return context_header()


def _time_ago(dt):
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    mins = int(diff.total_seconds() / 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins}m ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _get_daemon_event() -> dict:
    """Reply routing context for daemon-triggered tool calls."""
    try:
        from core.continuity.executor import current_event_data
        data = current_event_data.get() or {}
        if isinstance(data, dict) and data.get("channel_id"):
            return data
    except ImportError:
        pass

    channel_id = _reply_channel_id.get()
    account = _get_account()
    if account and channel_id:
        try:
            from plugins.leona_discord.daemon import get_pending_payload
            payload = get_pending_payload(account, str(channel_id))
            if payload:
                return payload
        except Exception:
            pass
    return {}


def _resolve_channel(client, loop, channel_ref):
    """Resolve a channel name or ID to a discord channel object."""
    event = _get_daemon_event()

    if not channel_ref:
        fallback_id = _reply_channel_id.get() or event.get("channel_id")
        if not fallback_id:
            return None, "No channel specified and no triggering channel available."
        channel_ref = str(fallback_id)

    channel_ref = channel_ref.strip().lstrip('#')

    if channel_ref.isdigit():
        async def _by_id():
            ch = client.get_channel(int(channel_ref))
            if not ch:
                ch = await client.fetch_channel(int(channel_ref))
            return ch
        future = asyncio.run_coroutine_threadsafe(_by_id(), loop)
        return future.result(timeout=10), None

    target = channel_ref.lower()
    preferred_guild = str(event.get("guild_id") or _reply_guild_id.get() or "").strip()
    if preferred_guild:
        try:
            guild = client.get_guild(int(preferred_guild))
            if guild:
                for ch in guild.text_channels:
                    if ch.name.lower() == target:
                        return ch, None
        except (TypeError, ValueError):
            pass

    for guild in client.guilds:
        for ch in guild.text_channels:
            if ch.name.lower() == target:
                return ch, None

    return None, f"Channel '{channel_ref}' not found. Use discord_get_servers to see available channels."


def _get_servers(client, loop):
    async def _fetch():
        servers = []
        for guild in client.guilds:
            channels = []
            for ch in guild.text_channels:
                channels.append({"name": ch.name, "id": str(ch.id)})
            servers.append({
                "name": guild.name,
                "id": str(guild.id),
                "channels": channels,
                "members": guild.member_count,
            })
        return servers

    future = asyncio.run_coroutine_threadsafe(_fetch(), loop)
    servers = future.result(timeout=10)

    if not servers:
        return _header() + "Not in any servers.", True

    lines = [_header()]
    for s in servers:
        lines.append(f"{s['name']} ({s['members']} members)")
        for ch in s["channels"]:
            lines.append(f"  #{ch['name']}")
        lines.append("")

    return "\n".join(lines), True


def _read_messages(client, loop, channel_ref=None, count=20):
    """Read recent messages. Each line includes [msg:ID] for use with discord_add_reaction."""
    count = min(max(count, 1), 50)

    channel, err = _resolve_channel(client, loop, channel_ref)
    if err:
        return err, False

    # Track the channel so subsequent discord_add_reaction calls can react to
    # messages from this read operation using the correct channel.
    global _last_read_channel_id
    _last_read_channel_id = str(channel.id)

    async def _fetch():
        messages = []
        async for msg in channel.history(limit=count):
            messages.append({
                "id": str(msg.id),
                "author": msg.author.display_name,
                "content": msg.content or "(no text)",
                "time": msg.created_at,
                "attachments": len(msg.attachments),
            })
        return list(reversed(messages))

    future = asyncio.run_coroutine_threadsafe(_fetch(), loop)
    messages = future.result(timeout=15)

    if not messages:
        return _header() + f"#{channel.name}: No messages.", True

    lines = [_header() + f"#{channel.name} — {len(messages)} messages:\n"]
    for m in messages:
        ago = _time_ago(m["time"])
        attach = f" [{m['attachments']} file(s)]" if m["attachments"] else ""
        lines.append(f"  [msg:{m['id']}] {m['author']} ({ago}): {m['content']}{attach}")

    return "\n".join(lines), True


def _apply_mention_map(text: str, channel_id: str) -> str:
    """Replace @name with <@user_id> using the stored mention map for the channel.

    Looks up the map from daemon so it works whether the LLM called
    discord_send_message directly or the auto-reply path fired.

    Falls back to the guild member cache for names not found in history, so
    pings work even for members who haven't spoken recently in the channel.
    """
    if not channel_id or not text:
        return text
    try:
        import re
        from plugins.leona_discord.daemon import get_mention_map, _clients
        mmap = dict(get_mention_map(str(channel_id).strip()))  # local copy — we may mutate it

        # Pre-fetch the guild once so the fallback closure doesn't repeat the lookup
        _guild_ref = None
        account = _get_account()
        if account:
            client_ref = _clients.get(account)
            if client_ref and client_ref.is_ready():
                # Find the guild that contains this channel
                ch_id_int = int(channel_id.strip())
                for guild in client_ref.guilds:
                    if guild.get_channel(ch_id_int):
                        _guild_ref = guild
                        break

        def _replace(match):
            raw_name  = match.group(1)
            name_lower = raw_name.lower().rstrip()
            # 1. Fast path — seen in channel history
            uid = mmap.get(name_lower)
            if uid:
                return f"<@{uid}>"
            # 2. Fallback — guild member cache
            if _guild_ref:
                member = _guild_ref.get_member_named(raw_name.rstrip())
                if member:
                    mmap[name_lower] = str(member.id)  # warm for subsequent hits
                    return f"<@{member.id}>"
            return match.group(0)

        return re.sub(r'@([A-Za-z0-9_.]+(?:\s[A-Za-z0-9_.]+)?)(?=\s|$|[^A-Za-z0-9_. ])', _replace, text)
    except Exception:
        return text


def _send_message(client, loop, channel_ref=None, text="", reply_to_message_id=None,
                  embed_title="", embed_description="", embed_color=""):
    """Send a message. Splits automatically at 2000 chars."""
    has_embed = bool((embed_title or "").strip() or (embed_description or "").strip())
    if (not text or not text.strip()) and not has_embed:
        return "Message text or embed is required.", False

    channel, err = _resolve_channel(client, loop, channel_ref)
    if err:
        return err, False

    if _task_auto_reply_enabled() and _is_trigger_channel(channel):
        logger.info(
            "[DISCORD] discord_send_message blocked — auto-reply handles #%s",
            getattr(channel, "name", channel.id),
        )
        return (
            "Skipped: auto-reply is enabled for this channel. Do not call "
            "discord_send_message for the triggering channel — write your reply "
            "as plain text and it will be sent automatically. Use inline tags "
            "[edit:corrected text], [react:emoji], or [gif:search query] in "
            "your text reply instead.",
            True,
        )

    lookup_id = str(getattr(channel, "id", "") or channel_ref or _reply_channel_id.get() or "")
    from plugins.leona_discord.lib.inline_tags import sanitize_discord_text
    text = sanitize_discord_text(text or "")
    text = _apply_mention_map(text, lookup_id)

    chunks = _split_long_message(text) if text and text.strip() else [""]

    reply_id = reply_to_message_id or _reply_message_id.get()
    embed_dict = None
    if has_embed:
        from plugins.leona_discord.lib.embeds import parse_color
        embed_dict = {
            "title": embed_title or "",
            "description": embed_description or "",
            "color": parse_color(embed_color or "7289DA"),
        }

    async def _send_all():
        from plugins.leona_discord.lib.embeds import build_embed
        for i, chunk_text in enumerate(chunks):
            chunk = chunk_text if chunk_text.strip() else None
            embed_obj = None
            if embed_dict and i == 0:
                embed_obj = build_embed(**embed_dict)
            reference = None
            if reply_id and i == 0:
                import discord
                reference = discord.MessageReference(
                    message_id=int(reply_id),
                    channel_id=channel.id,
                    fail_if_not_exists=False,
                )
            if not chunk and not embed_obj:
                continue
            await channel.send(content=chunk, embed=embed_obj, reference=reference)
        return channel.name

    future = asyncio.run_coroutine_threadsafe(_send_all(), loop)
    channel_name = future.result(timeout=10 * max(len(chunks), 1))
    event = _get_daemon_event()
    msg_id = str(event.get("message_id", ""))
    if msg_id:
        mark_tool_sent(msg_id, "\n\n".join(c for c in chunks if c.strip()))
    _message_sent.set(True)

    if len(chunks) == 1:
        return f"Message sent to #{channel_name}.", True
    return f"Message sent to #{channel_name} ({len(chunks)} parts).", True


def _upload_file(client, loop, file_path: str, channel_ref=None, caption=""):
    from pathlib import Path
    path = Path(file_path or "")
    if not path.is_file():
        return f"File not found: {file_path}", False

    channel, err = _resolve_channel(client, loop, channel_ref)
    if err:
        return err, False

    caption = _apply_mention_map(caption or "", str(channel.id))

    async def _do():
        import discord
        await channel.send(content=caption or None, file=discord.File(str(path)))
        return channel.name

    future = asyncio.run_coroutine_threadsafe(_do(), loop)
    channel_name = future.result(timeout=30)
    event = _get_daemon_event()
    msg_id = str(event.get("message_id", ""))
    if msg_id:
        mark_tool_sent(msg_id)
    _message_sent.set(True)
    return f"File uploaded to #{channel_name}.", True


def _send_gif(client, loop, query: str, channel_ref=None):
    channel, err = _resolve_channel(client, loop, channel_ref)
    if err:
        return err, False

    account = _get_account()
    event = _get_daemon_event()
    guild_id = str(_reply_guild_id.get() or event.get("guild_id") or "")
    if not guild_id and channel.guild:
        guild_id = str(channel.guild.id)

    from plugins.leona_discord.lib.gifs import send_gif_query

    msg, ok = send_gif_query(
        account,
        str(channel.id),
        (query or "").strip(),
        guild_id,
        force=True,
        explicit=True,
    )
    ch_name = getattr(channel, "name", channel.id)
    if ok:
        msg_id = str(event.get("message_id", ""))
        if msg_id:
            mark_gif_sent(msg_id)
        logger.info(
            f"[DISCORD] discord_send_gif sent to #{ch_name} "
            f"(id={channel.id}, guild={guild_id}, q={query!r})"
        )
    else:
        logger.info(
            f"[DISCORD] discord_send_gif failed in #{ch_name} "
            f"(id={channel.id}, guild={guild_id}, q={query!r}): {msg}"
        )
    return msg, ok


def _add_reaction(client, loop, emoji: str, message_id: str = None):
    """Add an emoji reaction to a Discord message, respecting plugin settings."""
    import random

    if not emoji or not emoji.strip():
        return "Emoji is required.", False

    raw_emoji = emoji.strip()
    from plugins.leona_discord.lib.emoji_policy import is_custom_discord_emoji
    emoji = raw_emoji if is_custom_discord_emoji(raw_emoji) else raw_emoji.strip(':')

    # Try ContextVar first (set by executor on Discord event), then fall back to
    # the daemon's cached event payload (stored at batch emit time).
    guild_id = str(_reply_guild_id.get() or "")
    channel_id = _reply_channel_id.get()
    trigger_msg_id = _reply_message_id.get()

    # When an explicit message_id is provided (from discord_read_messages), prefer
    # the channel used in that read operation over the triggering event's channel.
    # The ContextVar may hold the triggering event's channel, not the read channel.
    if message_id and _last_read_channel_id:
        channel_id = _last_read_channel_id

    if not guild_id:
        # ContextVar propagation from executor failed (different module instance).
        # Use the daemon's cached event payload as fallback — it has full context.
        # Pass channel_id when available: payloads are now keyed by channel_key so
        # this avoids the race where two channels flush under the same account and
        # the second payload overwrites the first.
        account = _get_account()
        if account:
            from plugins.leona_discord.daemon import get_pending_payload
            channel_id_hint = str(channel_id) if channel_id else ""
            payload = get_pending_payload(account, channel_id_hint)
            guild_id = payload.get("guild_id", "") or guild_id
            if not channel_id:
                channel_id = payload.get("channel_id", "")
            if not trigger_msg_id:
                trigger_msg_id = payload.get("message_id", "")

    logger.info(f"[DISCORD] discord_add_reaction called | emoji='{emoji}' | msg_id={message_id} | guild_id={guild_id}")

    try:
        from plugins.leona_discord.daemon import _get_effective_settings
        settings = _get_effective_settings(guild_id)
        logger.info(f"[DISCORD] Reaction settings loaded | enabled={settings.get('reactions_enabled')} | chance={settings.get('reaction_chance')} | allowed={settings.get('allowed_emojis')}")
    except Exception as e:
        logger.error(f"[DISCORD] Failed to load reaction settings: {e}", exc_info=True)
        settings = {}

    # Master toggle
    if not settings.get("reactions_enabled", False):
        return "Reactions are disabled in plugin settings.", False

    # Allowed emoji check — Unicode always OK; custom must be on server allowlist.
    from plugins.leona_discord.lib.emoji_policy import emoji_is_allowed, resolve_reaction_emoji
    if not emoji_is_allowed(raw_emoji, settings, guild_id):
        custom_allowed = [
            e for e in (settings.get("allowed_emojis") or [])
            if isinstance(e, str) and e.startswith("<")
        ]
        hint = " ".join(custom_allowed[:12]) if custom_allowed else "(no custom emoji configured)"
        return f"Emoji '{raw_emoji}' not allowed. Allowed custom: {hint}", False
    emoji = resolve_reaction_emoji(raw_emoji, guild_id)

    # Chance roll (100% = always fire)
    chance = max(0, min(100, int(settings.get("reaction_chance", 50))))
    if chance == 0:
        return "Reaction skipped (chance is 0%).", True
    if chance < 100 and random.random() >= (chance / 100.0):
        return "Reaction skipped (chance roll).", True

    # Permission check (trigger vs any)
    targeting_trigger = not message_id
    if targeting_trigger and not settings.get("react_to_trigger", True):
        return "Reacting to the triggering message is disabled in settings.", False
    if not targeting_trigger and not settings.get("react_to_any", False):
        return "Reacting to arbitrary messages is disabled in settings.", False

    # ── Deduplication gate ──
    _effective_msg_for_dedup = message_id or str(trigger_msg_id or "")
    if _effective_msg_for_dedup and channel_id:
        _account_for_dedup = _get_account() or ""
        from plugins.leona_discord.daemon import mark_reacted
        if not mark_reacted(_account_for_dedup, str(channel_id), _effective_msg_for_dedup, emoji):
            logger.info(f"[DISCORD] Reaction deduplicated — {emoji} already added to {_effective_msg_for_dedup}")
            return f"Reaction already added (deduplicated).", True

    if not channel_id:
        channel_id = _reply_channel_id.get()
    if not channel_id:
        return "No channel context available.", False

    async def _do_react():
        import discord
        channel = client.get_channel(int(channel_id))
        if not channel:
            channel = await client.fetch_channel(int(channel_id))

        if message_id:
            try:
                msg = await channel.fetch_message(int(message_id))
            except discord.errors.NotFound:
                msg = None
                if guild_id:
                    guild = client.get_guild(int(guild_id))
                    if guild:
                        for tc in guild.text_channels:
                            try:
                                msg = await tc.fetch_message(int(message_id))
                                channel = tc
                                break
                            except discord.errors.NotFound:
                                continue
                if not msg:
                    raise RuntimeError(f"Message {message_id} not found in guild {guild_id}")
        else:
            effective_msg_id = trigger_msg_id or _reply_message_id.get()
            if effective_msg_id:
                msg = await channel.fetch_message(int(effective_msg_id))
            else:
                async for m in channel.history(limit=1):
                    msg = m
                    break
                else:
                    raise RuntimeError("No message found to react to")

        resolved_emoji = emoji
        await msg.add_reaction(resolved_emoji)
        return msg.id

    try:
        future = asyncio.run_coroutine_threadsafe(_do_react(), loop)
        msg_id = future.result(timeout=10)
        logger.info(f"[DISCORD] ✅ Reacted {emoji} to message {msg_id}")
        return f"Reacted {emoji} to message.", True
    except Exception as e:
        import discord
        if isinstance(e, discord.errors.NotFound):
            logger.warning(f"[DISCORD] Reaction skipped: message {message_id or 'target'} not found (may have been deleted)")
            return f"Reaction skipped: message not found.", True
        logger.error(f"[DISCORD] Reaction failed: {e}", exc_info=True)
        return f"Failed to add reaction: {e}", False


def execute(function_name, arguments, config=None):
    """Dispatch tool calls. Returns (result_string, success_bool)."""
    ready = _check_ready()
    if isinstance(ready, str):
        return ready, False
    client, loop = ready

    try:
        if function_name == "discord_get_servers":
            return _get_servers(client, loop)
        elif function_name == "discord_read_messages":
            return _read_messages(
                client, loop,
                arguments.get("channel", arguments.get("channel_id", "")),
                arguments.get("count", 20)
            )
        elif function_name == "discord_send_message":
            return _send_message(
                client, loop,
                arguments.get("channel", arguments.get("channel_id", "")),
                arguments.get("text", ""),
                arguments.get("reply_to_message_id"),
                arguments.get("embed_title", ""),
                arguments.get("embed_description", ""),
                arguments.get("embed_color", ""),
            )
        elif function_name == "discord_upload_file":
            return _upload_file(
                client, loop,
                arguments.get("file_path", ""),
                arguments.get("channel", arguments.get("channel_id", "")),
                arguments.get("caption", ""),
            )
        elif function_name == "discord_send_gif":
            return _send_gif(
                client, loop,
                arguments.get("query", ""),
                arguments.get("channel", arguments.get("channel_id", "")),
            )
        elif function_name == "discord_add_reaction":
            return _add_reaction(
                client, loop,
                arguments.get("emoji", ""),
                arguments.get("message_id", None)
            )
        else:
            return f"Unknown function: {function_name}", False
    except Exception as e:
        logger.error(f"[DISCORD] Tool error: {e}", exc_info=True)
        return f"Discord error: {e}", False

