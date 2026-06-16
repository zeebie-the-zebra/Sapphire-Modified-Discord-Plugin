# Leona Discord — Configuration Guide

This document explains how every major feature in the **Leona Discord** plugin (`plugins/leona_discord`) works and how the settings UI maps to runtime behavior.

Open settings in Sapphire at **Settings → Leona Discord** (or `/settings` with the plugin tab selected).

---

## Table of contents

1. [Quick setup](#quick-setup)
2. [How settings are layered](#how-settings-are-layered)
3. [Bot accounts](#bot-accounts)
4. [Global Settings tabs](#global-settings-tabs)
5. [Per-server overrides](#per-server-overrides)
6. [Reply gating (when the bot speaks)](#reply-gating-when-the-bot-speaks)
7. [Human-like behavior](#human-like-behavior)
8. [Memory](#memory)
9. [Reactions](#reactions)
10. [Image understanding](#image-understanding)
11. [GIF follow-ups](#gif-follow-ups)
12. [Presence, quiet hours & activity decay](#presence-quiet-hours--activity-decay)
13. [Morning greeting](#morning-greeting)
14. [Quiet channel outreach](#quiet-channel-outreach)
15. [Direct messages](#direct-messages)
16. [Slash commands](#slash-commands)
17. [Safety](#safety)
18. [Debug traces](#debug-traces)
19. [Schedule tasks & connectivity](#schedule-tasks--connectivity)
20. [LLM inline tags](#llm-inline-tags)
21. [Discord tools (for the LLM)](#discord-tools-for-the-llm)

---

## Quick setup

1. Create a bot at [discord.com/developers](https://discord.com/developers).
2. Enable **Message Content Intent** under Bot → Privileged Gateway Intents.
3. Invite the bot with scopes `bot` and `applications.commands`.
4. In Leona Discord settings, add a **bot account** (name + token) and click **Test connection**.
5. Enable the plugin daemon and configure **Global Settings**.
6. Create a Sapphire **Schedule** task with:
   - Trigger: **Discord Message** (from this plugin)
   - Task option: **Auto-reply in channel** enabled
   - Filter: match the servers/channels you want

Without an auto-reply Schedule task, the bot can still connect, react, run slash commands, and send scheduled greetings — but **won't post LLM replies** to normal messages.

**Recommended Python packages:**

| Package | Purpose |
|---------|---------|
| `vaderSentiment` | Default reaction sentiment backend |
| `transformers` + `torch` | Optional DistilBERT backend (better on Discord slang) |

---

## How settings are layered

Effective behavior for each message is built in this order (later layers win):

```
Defaults → Global personality preset → Global settings
        → Per-server preset (if set) → Per-server overrides
        → Per-channel override (by ID or channel name)
        → DM overrides (when message is a DM)
        → Quiet hours modifier
        → Activity decay modifier (per channel)
```

**Important:** `@mentions` and **always-respond role** triggers bypass most random-chance and cooldown logic. They do **not** bypass `reply_mode: never`, user denylists, or safety checks.

Per-server override forms only cover **message behavior** (chances, reactions, reply mode, access lists). Image understanding, GIF settings, append-to-message, memory limits, and proactive features are **global only**.

---

## Bot accounts

Each account is a named Discord bot token. The daemon connects one WebSocket client per account.

| Setting | Behavior |
|---------|----------|
| **Always Online** (General tab) | **On (default):** all configured accounts connect when the daemon starts. **Off:** accounts only connect if an active Schedule daemon task references that account. |

Use separate accounts if you run multiple bots; settings and history are keyed by `account:channel_id`.

---

## Global Settings tabs

Global Settings are organized into tabs. Values apply everywhere unless a per-server override exists.

### General

| Setting | What it does |
|---------|--------------|
| **Batch Delay** (1–300 s, default 8) | After a message arrives, the bot waits this long for follow-up messages in the same channel, then processes them as **one batch**. Reduces reply spam when users send several lines quickly. Jitter of ±3 s is added automatically. |
| **Always Online** | See [Bot accounts](#bot-accounts). |
| **Slash Commands** | Register `/ask`, `/summarize`, `/remember` when the bot connects. |

### Replies

Core personality and reply behavior.

| Setting | What it does |
|---------|--------------|
| **Personality Preset** | One-click profiles: **Lurker**, **Helper**, **Chatterbox**, **Moderator**, or **Custom**. Presets set underlying chances and modes; you can fine-tune after picking one. |
| **Reply Mode** | `default` — use chances below. `mentions_only` — only @mentions, name match, keywords, roles. `reactions_only` — never text-reply. `never` — no replies or reactions. |
| **Keyword Triggers** | Comma/space-separated words; messages containing them count as directed at the bot (like a soft @mention). |
| **Always-Respond Role IDs** | Members with these roles (or messages that @mention the role) always queue a reply. |
| **User Denylist / Allowlist** | Discord user IDs. Denylist blocks; allowlist restricts (empty = everyone allowed). |
| **Ignore Bots** | Skip other bots' messages unless their ID is on the bot allowlist. |
| **Bot / Human Response Chance** | 0–100% probability for unsolicited messages (not @mention / keyword / name / role). |
| **Cooldown** | After replying, ignore non-trigger messages for N seconds (0 = off). |
| **Cooldown Scope** | `per_channel` or all channels in the server. |
| **Name Match** | Respond when the bot's display name appears in message text. |
| **Case-Sensitive Name Match** | Off by default. |

**Preset summary:**

| Preset | Human chance | Reactions | Notes |
|--------|-------------|-----------|-------|
| Lurker | 5% | 70%, react to any | Rare replies, frequent reactions |
| Helper | 0% (mentions only) | 25% | Support-style |
| Chatterbox | 40% | 45% | Frequent engagement |
| Moderator | 0% (keywords) | 15% | Keywords: help, mod, report, admin |

### Reactions & Media

| Setting | What it does |
|---------|--------------|
| **Reactions** | Allow silent emoji reactions without a text reply. |
| **Reaction Chance** | Even when the bot *decides* to react, this roll keeps it unpredictable. |
| **Reaction Cooldown** | Separate from reply cooldown. |
| **React to Triggering Message** | React to the message that triggered processing. |
| **React to Any Message** | Bot may react to other recent channel messages (lurker behavior). |
| **Sentiment Backend** | **VADER** (lightweight) or **DistilBERT** (better on slang; needs `transformers`). |
| **Allowed Custom Emoji** | Server emoji only; all Unicode emoji are always allowed. |
| **Message Edits** | Enables ~4% automatic post-send typo/thought edits and LLM `[edit:…]` tags. |
| **Image Understanding** | Describe images via a vision model for text-only base models. |
| **GIF Replies** | Automatic GIF follow-up after text replies (see [GIF follow-ups](#gif-follow-ups)). |

### Memory

| Setting | What it does |
|---------|--------------|
| **Discord Memory** | Master toggle for SQLite memory injection. |
| **LLM Max History** | Max conversation messages sent to the LLM globally (0 = unlimited; token trim only). Synced to Sapphire `user/settings.json`. |
| **Reply Context Limit** | Token budget for the Discord Bot Reply Schedule task (0 = use global `CONTEXT_LIMIT`). Synced to the linked Schedule task. |
| **Recent Chat Lines** | How many prior channel lines inject into each prompt (5–100, default 25). |
| **Max Chars per Line** | Truncate each history line (80–1000, default 280). |
| **Memory Token Budget** | Max tokens of *older* relevant messages not already in recent chat (default 300). |
| **Memory Match Threshold** | Semantic match strictness 0.0–1.0 (default 0.35). |

### Presence

See [Presence, quiet hours & activity decay](#presence-quiet-hours--activity-decay), [Morning greeting](#morning-greeting), [Quiet channel outreach](#quiet-channel-outreach), [Direct messages](#direct-messages), and [Safety](#safety).

### Advanced

| Setting | What it does |
|---------|--------------|
| **Append to User Message** | Static text appended to every user message sent to the base model (max 2000 chars). Useful for style reminders. |

### Debug

| Setting | What it does |
|---------|--------------|
| **Server-side Debug Logging** | Write gate-by-gate decision traces to SQLite for each incoming message. |
| **Response Debug Traces** | Viewer for recent traces — shows exactly why the bot replied, reacted only, or stayed silent. |

---

## Per-server overrides

Under **Per-Server Overrides**, expand a guild to fine-tune behavior. Values shown are **effective** settings (global + any existing override).

- Adjust fields and **Save Override**, or **Reset** to remove the server entry entirely.
- **Channel Override:** set `reply_mode` for a specific channel by ID or name (e.g. `memes`).

`@mentions` always bypass chance rolls and cooldowns regardless of overrides.

---

## Reply gating (when the bot speaks)

For each incoming message the bot evaluates gates in order (visible in debug traces):

1. **Safety** — permissions, rate limits, content blocklist
2. **User access** — denylist, allowlist, ignore bots
3. **Reply mode** — never / reactions_only / mentions_only / default
4. **Triggers** — @mention, role, name match, keyword
5. **Cooldown** — if not a hard trigger
6. **Chance roll** — human_response_chance or bot_response_chance
7. **Read-only react** — ~5% of organic messages may get only a reaction, no reply

**Hard triggers** (usually queue a reply if mode allows): direct @mention of the bot, always-respond roles, name match, keyword match.

**Soft triggers:** random chance paths, images (only in default mode with chance > 0).

---

## Human-like behavior

These run automatically; most have no separate UI toggle.

### Timing

| Behavior | Default rate / value |
|----------|---------------------|
| Human pause after LLM finishes | 0.5–3 s before typing starts |
| Contextual typing WPM | Short text faster; long paragraphs & code slower |
| Inter-chunk pause | 0.5–1.5 s between split messages |
| Batch delay jitter | ±3 s on top of configured batch delay |
| Post-typing read pause | 0.8–2.5 s when user was typing during batch |
| Delayed reply | ~7.5% of non-urgent messages wait extra 30–60 s |
| Reaction delay | 1–5 s before adding emoji |
| Reaction removal | ~4% removed after 30–60 s |

Questions (`?`) and `@mentions` use the faster urgency path.

### Message style

| Behavior | Description |
|----------|-------------|
| **`[break]` markers** | LLM can split into 2–3 messages at natural boundaries. |
| **Quote-replies** | Contextual — higher in busy channels, lower in DMs, skipped for jokes/media. |
| **Post-send edits** | ~4% typo fix or casual afterthought (2–5 s later). |
| **`[edit:…]` tag** | LLM-initiated edit (requires Message Edits enabled). |
| **Casual emoji suffix** | ~12.5% on short positive replies without emoji. |
| **Bullet lists** | ~30% of the time each bullet is its own message; otherwise one combined message. |
| **Long message split** | Paragraphs, bullets, emoji clusters, then Discord 2000-char limit. |

### Engagement (automatic)

| Behavior | Description |
|----------|-------------|
| **Topic interest** | Channels track keywords; replied topics get ~28% higher chance, ignored topics lower. |
| **Thread continuation** | Replies to the bot's messages boost chance (floor ~65%). |
| **Engagement weight** | Per-channel 1–100 scale for reply chances (advanced JSON override). |
| **Message length awareness** | If recent bot replies average >150 chars, ~35% of batches get a brevity hint. |
| **Engagement window** | After the bot replies, the channel stays "warm" for follow-ups. |

---

## Memory

All memory is **self-contained** in this plugin — no external required.

**Storage:** `user/plugin_data/leona_discord/discord_memory.sqlite`

| Layer | Purpose |
|-------|---------|
| **Channel cache** | Up to 100 recent messages per channel (mentions, formatting, survives restarts). |
| **Long-term store** | Up to 10,000 messages per channel for search/recall. |
| **Pinned memory** | `/remember` slash command saves notes recalled in future prompts. |

**Injection flow:** At batch time, recent lines + semantically matched older lines are prepended to the LLM prompt automatically. The model does not need to call tools for recall.

**Bot identity:** Reply prompts include a hint that lines from the bot's display name are the bot's own prior messages (first person, not third).

---

## Reactions

When the bot doesn't send a text reply, it may still react if reactions are enabled.

- Sentiment (VADER or DistilBERT) picks emoji tier: positive → 👍❤️, negative → sympathetic, etc.
- **Blocked emoji on negative sentiment** — no 👍 on sad posts.
- **Variety:** avoids repeating the same emoji twice in a row; channel history weights common emoji.
- **Read-only react path:** ~5% of organic messages get a reaction without entering the reply queue.

During **quiet hours** (reactions_only mode), reactions stay on; in **fully silent** mode they are off.

---

## Image understanding

When a user sends an image or GIF:

- **Enabled:** a vision-capable model describes the image; description is prepended to the user message for the text base model.
- **Disabled:** the Discord CDN URL is included in the prompt so a vision-capable base model could fetch it (Sapphire's pipeline is text-only to the base model).

Configure provider, model name, and max tokens under **Reactions & Media → Image Understanding**.

---

## GIF follow-ups

After a successful **text auto-reply**, the bot may send a GIF as a second message.

| Setting | Default | Purpose |
|---------|---------|---------|
| Enabled | Off | Master toggle |
| Reply chance | 15% | Roll after text reply |
| Cooldown | 120 s | Per-channel GIF cooldown |
| Use LLM for query | On | Micro-LLM picks 2–5 word search terms |
| Provider / model | — | Optional dedicated query model |
| Content filter | medium | Klipy/Tenor filter level |

- **`[gif:search terms]`** in LLM output triggers a follow-up GIF (stripped before send).
- **`discord_send_gif` tool** — LLM can explicitly search and post.
- User-requested GIFs bypass the chance roll.

---

## Presence, quiet hours & activity decay

### Quiet hours (UTC)

**Off by default.** When enabled, defines a UTC time window (default **22:00 → 08:00**) and a mode.

The bot is **not offline** during quiet hours — it stays connected. Discord presence switches to **idle** (yellow moon) instead of online.

| Behavior | Reactions only (default) | Fully silent |
|----------|------------------------|--------------|
| Random replies | Off | Off |
| Name match / keywords | Off | Off |
| Emoji reactions | **On** | Off |
| @mentions | **Still replies** | **Still replies** |
| Role triggers | **Still replies** | **Still replies** |
| Slash commands | **Still work** | **Still work** |
| Morning greeting | Skipped | Skipped |
| Quiet outreach | Skipped | Skipped |

Quiet hours are a **"don't butt into the conversation"** schedule, not a full shutdown. Someone @mentioning the bot at 3 AM UTC can still get a reply.

The window uses **UTC** and wraps overnight (22→8 means 22:00 through 07:59 UTC).

### Activity decay

**Off by default.** Separate from quiet hours — not a sleep schedule.

When a channel has **≥ threshold messages in the last 5 minutes** (default: 10 messages):

- `human_response_chance` and `bot_response_chance` are multiplied (default **×0.5**).

Example: 15% human chance → 7% in a busy channel.

Only affects random-chance rolls — not @mentions, reactions, or scheduled messages.

---

## Morning greeting

Scheduled proactive good-morning messages to selected channels.

| Setting | Default | Purpose |
|---------|---------|---------|
| Enabled | Off | Master toggle |
| UTC hour | 9 | Posted once per day when hourly cron hits this hour |
| AI-Generated Greeting | On | LLM writes fresh text from instructions |
| Greeting Instructions | (see UI) | Prompt to the LLM — **not** posted verbatim |
| Fallback Message | "Good morning, everyone! ☀️" | Used if LLM fails |
| Model provider / name | — | Optional dedicated model |
| Greeting Channels | — | Picker or `account:guild_id:channel_id` lines |

**Schedule:** `morning_greeting` cron `0 * * * *` (every hour; posts only at configured UTC hour).

**Test:** **Send test greeting** bypasses enabled toggle and UTC hour (uses current form values).

**Self-greeting fix:** The LLM is told it is posting *as* the bot. Bot history lines appear as `You:` in context. Accidental `Morning, Remmi` patterns are stripped before send.

**Quiet hours:** Greetings are skipped during quiet hours.

**Outreach coordination:** A successful greeting records outreach cooldown on that channel. Outreach skips greeting-target channels for 2 hours before the greeting UTC hour.

**Sleep schedule:** When enabled, wake hour also drains buffered overnight @mentions (see below).

---

## Sleep schedule

Full sleep/wake cycle — stronger than Quiet Hours.

| Setting | Default | Purpose |
|---------|---------|---------|
| Sleep Schedule | Off | Master toggle |
| Sleep UTC Hour | 22 | Goodnight at a **random minute** within this hour |
| Buffered @Mention Replies | 3 | Max replies after wake (newest first) |
| Use Greeting Channels | On | Same channels as Morning Greeting |

### Flow

1. **Sleep hour:** `sleep_goodnight` cron (every 15 min) picks a random minute 0–59 per channel per night. After that minute, the bot posts **goodnight** and marks the channel **asleep**.
2. **While asleep:** No replies, reactions, or outreach. **Direct @mentions only** are buffered in SQLite.
3. **Wake hour** (Morning Greeting UTC hour): Good morning posts → channel wakes → up to **N** newest buffered @mentions get delayed LLM replies (25–75 s apart). Older buffered mentions are skipped.

**Presence:** Idle with activity `sleeping` while any configured channel is asleep.

Enable **Morning Greeting** (or Sleep Schedule alone) so wake hour runs.

---

## Quiet channel outreach

Proactive conversation starters when channels go quiet.

| Setting | Default | Purpose |
|---------|---------|---------|
| Enabled | Off | Master toggle |
| Quiet after | 240 min | No human messages this long |
| Cooldown | 8 h | Min time between outreach in same channel |
| Skip chance | 25% | Random skip even when eligible |
| Active hours | 10–21 UTC | Outreach only in this window |
| AI-generated | On | LLM writes opener from instructions |
| Typing indicator | On | Brief typing before send |
| Outreach Channels | — | Same picker format as greetings |

**Schedule:** `quiet_outreach` cron `*/15 * * * *` (every 15 minutes).

**Requirements to fire:**

- Channel has history (at least one past human message in SQLite)
- Last human message older than quiet threshold
- Not in outreach cooldown
- Not in quiet hours
- Not in greeting window (for greeting-target channels)
- Passes skip-chance roll

Uses the same bot-identity and `You:` history labeling as morning greetings.

---

## Direct messages

Separate section under **Presence** tab:

| Setting | Default |
|---------|---------|
| DM Human Reply Chance | 25% |
| DM Reaction Chance | 40% |
| DM Cooldown | 60 s |

DM settings merge on top of global settings when `is_dm` is true. Quiet hours still zero random reply chances but @mentions in DMs still work.

---

## Slash commands

Requires **Slash Commands** enabled (General tab). Synced on bot connect.

| Command | Behavior |
|---------|----------|
| `/ask <prompt>` | Emits a Discord Message event to the Schedule pipeline (needs auto-reply task). |
| `/summarize [count]` | Summarizes last 5–50 cached channel messages via LLM. |
| `/remember [note]` | Saves pinned memory to SQLite (empty = uses your last message). |

`/ask` and `/summarize` need a Schedule task with auto-reply enabled to post results back to the channel.

---

## Safety

Under **Presence → Safety** (global):

| Setting | Default | Purpose |
|---------|---------|---------|
| Check channel permissions | On | Skip if bot lacks Send Messages |
| Rate limit gap | 2 s | Min seconds between messages from same user in same channel |
| Rate limit burst | 8 | Max messages per window |
| Rate limit window | 60 s | Burst window |
| Content blocklist | — | Comma/newline terms; case-insensitive substring match |

Failed safety checks appear in debug traces.

---

## Debug traces

Enable **Server-side Debug Logging** (Debug tab).

Each incoming message can log a trace with gate names: `reply_mode`, `mentioned`, `name_match`, `cooldown`, `human_response_chance`, `safety`, etc.

Use this when the bot "should have replied" but didn't — the trace shows which gate stopped it.

**Memory stats** in the traces panel show SQLite message count.

---

## Schedule tasks & connectivity

### Discord Message auto-reply task

Minimum setup for conversational replies:

1. Trigger: **Discord Message** (Leona Discord)
2. Enable **Auto-reply in channel**
3. Optional filters: guild, channel, mentioned, content_contains, etc.
4. Assign tools if the LLM should use Discord tools

The reply handler only sends to Discord when `auto_reply` is true on the matched task.

### Continuity scheduler

These plugin crons run via Sapphire's continuity scheduler (bot must be online):

| Cron | Handler | Purpose |
|------|---------|---------|
| `0 * * * *` | `morning_greeting.py` | Hourly check for greeting UTC hour |
| `*/15 * * * *` | `quiet_outreach.py` | Quiet-channel outreach sweep |
| `*/15 * * * *` | `sleep_goodnight.py` | Goodnight + enter sleep state |

### Always Online vs Schedule-gated

| Always Online | Active Schedule task for account | Connects? |
|---------------|----------------------------------|-----------|
| On | — | Yes |
| Off | Yes | Yes |
| Off | No | No |

---

## LLM inline tags

The reply LLM can embed tags in its output. Tags are stripped before posting.

| Tag | Effect |
|-----|--------|
| `[break]` | Split into separate messages at this boundary |
| `[react:emoji]` | React to the triggering message (policy-checked) |
| `[gif:query]` | GIF follow-up after text reply |
| `[edit:corrected text]` | Send initial text, then edit to corrected version (2–5 s later) |

Think tags (`…`) are stripped everywhere.

---

## Discord tools (for the LLM)

Exposed via `tools/discord_tools.py` when included in a Schedule task toolset:

| Tool | Purpose |
|------|---------|
| `discord_send_message` | Send text, optional embed, optional reply-to |
| `discord_send_gif` | Search and post a GIF |
| `discord_upload_file` | Upload attachment with optional caption |

If a tool already sent a message for an event, the auto-reply handler skips duplicate sends.

---

## Tips

- **Start with Helper preset** on a test channel, then loosen chances.
- Use **debug traces** when tuning gates — they show the exact failure reason.
- **Quiet hours** = lurk mode, not offline. Use **Reply Mode → Never** for hard silence (except @mentions still work unless you also deny via other gates).
- **LLM Max History** and **Reply Context Limit** affect token usage globally — lower them on busy servers (try 32 history, 32000 context for Discord toolsets).
- **Send test greeting** is the fastest way to verify proactive LLM + channel picker without waiting for UTC hour.

---

## Related files

| File | Topic |
|------|-------|
| `README.md` | Setup summary & file structure |
| `CHANGELOG.md` | Version history and feature notes |
| `upgrade.md` | Planned / design notes |
| `EMOJIS.md` | Unicode emoji reference for reactions |
