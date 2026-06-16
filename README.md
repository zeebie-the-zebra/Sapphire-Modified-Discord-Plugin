# Leona Discord Plugin

Bot integration for Discord — receives messages via webhook daemon and sends replies back to channels.

## Setup

1. Create a bot at [discord.com/developers](https://discord.com/developers)
2. Enable **Message Content Intent** under Bot settings
3. Add the bot to your server using an OAuth2 invite link (scopes: `bot`, `applications.commands`)
4. Enter the bot token and account name in the plugin settings UI

## Required Dependencies

### vaderSentiment (required for reactions)

```bash
pip install vaderSentiment
```

VADER is a lightweight rule-based sentiment analyser. It is the **default and recommended** backend for silent reactions — no extra dependencies, no model downloads.

### DistilBERT (optional — better sentiment accuracy on Discord text)

```bash
pip install transformers torch
```

DistilBERT (`cardiffnlp/twitter-roberta-base-sentiment-latest`) is trained on social media text and handles Discord slang, sarcasm, and emoji better than VADER. Requires ~500 MB download on first use. Enable it in the plugin settings UI under **Sentiment Backend**.

## Features

### Message Batching

Messages are batched per channel to prevent rapid multi-message trains from creating separate LLM conversations. The batch delay is configurable (1–300 seconds, default 8s) in the Global Settings UI.

### Typing Indicator

Discord's typing indicator is shown during the batch wait and while awaiting AI responses via background threads — no rate limit issues.

### Long Response Splitting

AI responses exceeding Discord's 2000-character limit are automatically split:
- Tries to split at newlines first
- Falls back to sentence-ending punctuation (`.`, `!`, `?`)
- Falls back to hard cut at 2000 chars if no boundary found

### Per-Server Overrides

All settings (response chances, cooldown, reactions, image understanding) can be overridden per server in the UI.

### Image Understanding

When a Discord user sends an image, the bot can describe it using a vision-capable model and include that description in the prompt sent to the base (non-vision) model. Configure:

- **Vision Model Provider** — Sapphire LLM provider (e.g. `claude`, `openai`, `fireworks`)
- **Vision Model Name** — exact model key (e.g. `claude-sonnet-4-6`, `gpt-4o`, `qwen3-vl-235b-a22b-thinking`)
- **Vision Model Max Tokens** — how many tokens to allocate for the description (1–2000, default 500)

The base model must not natively support images for this to be useful.

### Silent Reactions

The bot can add emoji reactions to messages it doesn't reply to. Configure:
- Reaction chance (0–100%)
- Whether to react to the triggering message only or any channel message
- Sentiment backend (VADER or DistilBERT)
- Custom allowed emoji (standard Unicode emoji are always allowed)

### Persistent memory (self-contained)

All Discord memory lives inside this plugin — **no MemPalace plugin or other Sapphire plugins required**.

- **SQLite store** at `user/plugin_data/leona_discord/discord_memory.sqlite`
- **Channel cache**: up to 100 messages per channel (mentions, search corpus, survives restarts)
- **Long-term search**: up to 10,000 messages per channel retained for auto-recall
- **LLM injection**: only the last **25** messages by default (configurable 5–100), each line capped at **280** chars; images become `(+N image)` instead of URLs
- **Older context**: keyword search pulls up to 5 relevant messages *not* already in the recent transcript (~300 token budget)
- **Seamless injection**: relevant past context is prepended to the LLM prompt automatically at batch time — the model never needs to call tools for memory
- **Debug traces**: gate-by-gate log of why the bot replied or stayed silent (Settings UI → Response Debug Traces)

### Personality & presence (Tier 3)

- **Presets**: Lurker, Helper, Chatterbox, Moderator — one-click behaviour profiles
- **Reply modes**: default, mentions-only, reactions-only, never (global, per-server, or per-channel)
- **Keyword triggers** and **always-respond role IDs**
- **User/bot allowlists & denylists**
- **Separate DM settings** (reply chance, reaction chance, cooldown)
- **Quiet hours (UTC)** and **activity decay** when channels are busy
- **Morning greeting** — hourly cron; **LLM writes a fresh message** each day from your instructions (with static fallback if the LLM fails)
- **Reaction cooldown** separate from reply cooldown; blocked emoji on negative sentiment (no 👍 on sad posts)

### Discord-native capabilities (Tier 4)

- **Slash commands**: `/ask`, `/summarize`, `/remember` — synced on bot connect (requires Schedule task for /ask and /summarize)
- **Rich messages**: auto-replies quote the triggering message; `discord_send_message` supports embeds + reply-to
- **File uploads**: `discord_upload_file` tool for attachments with optional caption
- **Pinned memory**: `/remember` saves to self-contained SQLite (injected in recall, no MemPalace)
- **Safety layer**: permission checks, per-user rate limits, content blocklist — all gate-logged in debug traces

### Cooldown

After responding, the bot ignores non-@mention messages for a configurable time (0–600s). Scope can be per-channel or all channels.

### Name Match

When enabled, the bot always responds if its name appears anywhere in a message (soft @mention). Case-sensitive matching is optional.

## Configuration

All configuration is done via the plugin settings UI at `/settings`. Global defaults apply to all servers; per-server overrides can be set for each guild.

## File Structure

```
leona_discord/
├── daemon.py              # Lifecycle entry point; re-exports public API
├── lib/
│   ├── batching.py        # Message batching and event emission
│   ├── connection.py      # Bot connect/disconnect with rate-limit safeguards
│   ├── context_cache.py   # Reply context and reaction deduplication
│   ├── cooldowns.py       # Probabilistic reply cooldown tracking
│   ├── history.py         # Channel history cache + SQLite sync
│   ├── store.py           # SQLite: messages, search, debug traces
│   ├── memory.py          # Auto-recall for seamless prompt injection
│   ├── trace.py           # Gate decision tracing
│   ├── images.py          # Image collection and vision-model description
│   ├── messages.py        # Message splitting utilities
│   ├── mentions.py        # @name and custom emoji resolution
│   ├── reactions.py       # Sentiment-based silent reactions
│   ├── send.py            # Discord send helper
│   ├── settings.py        # Settings merge and live reads
│   ├── presets.py         # Personality preset definitions
│   ├── gates.py           # Reply/reaction gate evaluation
│   ├── presence.py        # Quiet hours
│   ├── activity.py        # Channel activity decay
│   ├── safety.py          # Permissions, rate limits, blocklist
│   ├── events.py          # Daemon event build/emit (slash + shared)
│   ├── embeds.py          # Discord embed helpers
│   ├── state.py           # Shared daemon state
│   └── typing_indicator.py
├── handlers/
│   ├── on_message.py      # Discord message event handler
│   ├── slash_commands.py  # /ask /summarize /remember
│   └── reply_handler.py   # LLM response routing back to channels
├── emojis.py              # Unicode emoji list for reactions
├── plugin.json
├── routes/
│   ├── accounts.py
│   └── settings.py
├── schedule/
│   └── morning_greeting.py
├── tools/
│   └── discord_tools.py
└── web/
    └── index.js
```