# Changelog

All notable changes to the **Leona Discord** plugin (`plugins/leona_discord`).

The stock `plugins/discord` plugin was **not modified** — Leona is a separate, personality-oriented fork.

---

## Human-like response timing (v1.4.0)

### Sleep schedule

- **Goodnight → dormant → wake → buffered @mentions** (`lib/sleep_schedule.py`, `schedule/sleep_goodnight.py`, `lib/sleep_buffer.py`)
- Random goodnight minute within sleep UTC hour; morning greeting wakes channel; max N newest overnight @mentions replied (default 3)

### Tabbed Global Settings UI

- Global Settings are split into tabs (General, Replies, Reactions & Media, Memory, Presence, Advanced, Debug) instead of one long scroll
- Response Debug Traces viewer moved into the Debug tab

### Variable response delay

- After the LLM finishes generating, the reply handler adds a random **0.5–3s human pause** before showing the typing indicator and sending (`lib/typing_indicator.py`, `handlers/reply_handler.py`)

### Contextual typing speed

- Typing duration now adapts to reply content instead of a flat 65 WPM:
  - **Short replies** (&lt;50 chars): 80–100 WPM
  - **Long paragraphs** (&gt;200 chars): 45–55 WPM
  - **Code / technical content**: 30–40 WPM (fenced blocks, inline backticks, or dense punctuation)
  - Default band remains ~65 WPM with ±20% jitter

### Read-only reactions

- ~**5%** of organic messages (human-chance path, not @mentions / name / keyword / role triggers) may get a **silent reaction without a text reply** — simulates reading a message and choosing not to answer (`lib/gates.py`, `handlers/on_message.py`, `lib/reactions.py` `force=` on `try_silent_react`)

### Delayed replies

- ~**7.5%** of non-urgent messages get an extra **30–60s** batch delay before the bot responds — simulates “thinking about it” (`lib/batching.py`)
- Questions (`?`) and `@` mentions still use the faster urgency path

### Message sending patterns

- **Contextual quote-replies** (`lib/reply_style.py`): DMs use lower quote chance (10–20%); busy batches (&gt;5 msgs) use 65%; rapid back-and-forth after a bot reply skips quoting; ongoing threads boost chance; questions always quote; jokes/comments and media reactions send standalone
- **Post-send edits**: ~**4%** of single-chunk replies are sent with a subtle typo or plain text, then edited after **2–5s** to fix the typo or append a casual thought (`lib/send.py` `edit_message`, `handlers/reply_handler.py`)
- **LLM-requested edits**: the model can append `[edit:corrected text]` to occasionally fix a typo or expand a thought after sending; the tag is stripped and a prompt hint is injected at batch time (`message_edits_enabled`, default on; toggle in Global Settings → Message Edits)
- **Casual emoji suffix**: ~**12.5%** of short (≤80 char) positive replies get a trailing emoji when the LLM did not already include one

### Reaction behavior

- **Reaction delay**: silent and inline reactions wait **1–5s** after the message arrives before adding the emoji (`lib/reactions.py` `add_reaction_humanized`)
- **Read-only reactions** (react without reply): already handled via ~**5%** organic read-only path (`lib/gates.py` `should_read_only_react`) — decoupled from the normal reply queue
- **Reaction variety**: per-channel memory avoids repeating the same emoji twice in a row; frequently used emoji in a channel are weighted higher; tech/dev channel names prefer 👀 🧐 💡 over heart-style emoji
- **Reaction removal**: ~**4%** of reactions are removed after **30–60s** — simulates changing your mind

### Engagement patterns

- **Topic interest tracking** (`lib/engagement.py`): per-channel keyword scores rise when the bot replies on a topic and fall when it ignores one; matching topics get ~**28%** higher reply chance, avoided topics ~**28%** lower
- **Thread continuation**: direct replies to the bot's messages boost `human_response_chance` to at least **65%** (×1.45 multiplier, cap 95%) — explicit on top of the engagement window
- **Selective lurking**: optional per-channel `engagement_weight` (1–100, default 100) scales human/bot reply chances — e.g. weight **10** on a lurker channel turns 15% into ~1.5%; set in server channel overrides JSON or global settings
- **Message length awareness**: tracks recent bot reply lengths per channel; when the average exceeds ~150 chars, ~**35%** of batches inject a brevity hint nudging a short one-liner

### Technical improvements

- **Batch delay jitter**: every batch wait gets **±3s** random jitter on top of the configured delay (`apply_batch_delay_jitter` in `lib/batching.py`)
- **Post-typing read pause**: when `on_typing` extended a batch, an extra **0.8–2.5s** pause runs before flush — simulates reading what the user typed
- **Richer message splitting** (`lib/messages.py`): splits at paragraph breaks, bullet/numbered list lines, and leading emoji clusters before applying Discord length limits
- **Bullet list delivery**: ~**30%** of the time each bullet is sent as its own message; otherwise the full list stays in one message (`BULLET_SPLIT_EACH_CHANCE`)
- **Edit history** (`lib/edit_history.py`): post-send edits are tracked per channel and surfaced in LLM style hints so the bot can naturally use "wait" / "i mean" correction patterns

### Settings UI

- **Message Edits** toggle in Global Settings (per-server personality fields) — enables LLM `[edit:…]` hints and automatic post-send edits
- **Server-side Debug Logging** toggle (renamed from Debug Traces) — controls whether incoming messages write gate-decision traces to SQLite; view results in Response Debug Traces

---

## Tier 5 — Proactive presence & media (v1.3.0)

### LLM morning greetings

- Morning greeting text can be **AI-generated** each day instead of a static template (`lib/greeting_llm.py`)
- Greeting/outreach LLM context labels the bot's own history lines as **You:** and forbids self-greetings by name (`lib/bot_identity.py`, `lib/history.py`)
- Settings: **AI-Generated Greeting**, **Greeting Instructions** (LLM prompt, not posted verbatim), **Fallback Message**, optional greeting model provider/name/max tokens
- Schedule still runs hourly and posts only at the configured **UTC hour** (`schedule/morning_greeting.py`)
- Uses recent channel history for variety; falls back to static text if the LLM is unavailable

### Greeting channel picker

- **Send test greeting** button in settings — posts immediately to selected channels (bypasses UTC hour; uses current form values)
- New API: `POST /api/plugin/leona_discord/greeting/test`
- Replaced manual `account:guild_id:channel_id` textarea with a **Discord channel picker** in Global Settings
- **Refresh from Discord** loads all text channels from connected bots (grouped by account · server)
- Selected channels shown as removable chips; raw target lines still available under **Advanced**
- New API: `GET /api/plugin/leona_discord/greeting/targets`

### Quiet channel outreach

- Proactive **conversation starters** when configured channels go quiet (`schedule/quiet_outreach.py`)
- Sapphire schedule: **every 15 minutes** (`quiet_outreach` cron)
- Defaults: quiet after **240 min**, cooldown **8 h**, skip chance **25%**, active hours **10–21 UTC**
- Detects quiet via last **human** message in SQLite; skips channels with no history
- Respects global **Quiet Hours**; optional **typing indicator** delay before send
- LLM-generated openers with instructions + fallback (`lib/outreach_llm.py` pattern shared with greetings)
- Channel picker UI (same targets API as morning greeting)
- Outreach timestamps stored in `outreach_log` SQLite table (`lib/store.py`)

### Automatic GIF / meme follow-ups

- After a successful **text auto-reply**, the bot may send a GIF as a second message — no LLM tags required (`lib/gifs.py`, hooked from `handlers/reply_handler.py`)
- **Micro-LLM** picks a 2–5 word search query (`lib/gif_query_llm.py`); returns `NONE` when a GIF would feel forced
- **Sentiment fallback** (VADER/DistilBERT tier → query map) when the micro-LLM is off or returns empty — same philosophy as silent reactions
- Settings: enable toggle, reply chance %, cooldown, content filter, optional query model provider/name
- Per-channel GIF cooldown tracked separately from reply/reaction cooldowns (`lib/cooldowns.py`)
- **Greeting ↔ outreach coordination** (`lib/proactive_guard.py`): successful morning greetings record the outreach cooldown; outreach skips greeting-target channels for 2 hours before the greeting UTC hour
- **`discord_send_gif` tool** — LLM can explicitly search and post a GIF (use instead of `web_search` / `get_website`)
- **`[gif:search terms]` inline tag** — optional follow-up GIF after text reply (stripped before send, like `[react:emoji]`)
- When the user asks for a GIF, automatic follow-up **bypasses the chance roll** (`user_requested_gif`)
- Prompt hint injected into daemon events when GIF replies are enabled (`build_gif_hint`)
- Fixed settings merge: `get_gif_settings()` reads top-level saved keys (`gif_api_key`, `gif_replies_enabled`, etc.)
- **`discord_send_gif` tool** no longer blocked by the automatic-follow-up toggle (only needs API key); daemon event context used for channel/guild routing when ContextVars unset
- **`discord_send_gif` / Discord tools** resolve bot account from daemon event payload when `discord_scope` is `none` (common on scheduled Discord reply tasks)
- **`discord_send_gif` no longer suppresses the text auto-reply** — only `discord_send_message` / upload increment the send-count guard
- **Reply LLM context in plugin UI** — edit `LLM Max History` (global) and `Reply Context Limit` (Discord Bot Reply Schedule task) under Global Settings; syncs to `user/settings.json` and `user/continuity/tasks.json` on save
- Channel name resolution prefers the triggering server's guild (avoids wrong-channel GIF sends when names collide)
- Improved logging when GIF follow-up is skipped or fails (was silent before)

### GIF search providers (Tenor → Klipy / Giphy)

- Google **Tenor API** is deprecated (no new keys from Jan 2026; shutdown **Jun 30, 2026**)
- New unified search layer: **`lib/gif_search.py`**
  - **Klipy** (default) — Tenor-compatible `api.klipy.com/v2/search`; sign up at [partner.klipy.com](https://partner.klipy.com)
  - **Giphy** — `api.giphy.com/v1/gifs/search`; key from [developers.giphy.com](https://developers.giphy.com)
  - **Tenor (legacy)** — existing Google keys until shutdown
- Settings: **GIF Provider** dropdown, **GIF API Key** (replaces Tenor-only field)
- Legacy `tenor_api_key` values **migrate automatically** to `gif_api_key` on read

### Settings UI fixes

- **Image Understanding** (vision model) panel was never rendered — missing `#dc-image-settings` mount point in the settings template; now visible with provider dropdown, model name, and max tokens
- Separate **`#dc-gif-settings`** mount for GIF / meme reply controls
- Global settings load merges top-level saved values (greetings, outreach, GIF keys) into form fields correctly

### New / updated modules

| Module | Purpose |
|--------|---------|
| `lib/greeting_llm.py` | LLM-generated morning greeting text |
| `lib/outreach_llm.py` | LLM-generated quiet-channel outreach text |
| `schedule/quiet_outreach.py` | Periodic quiet-channel sweep |
| `lib/gif_search.py` | Klipy / Giphy / legacy Tenor GIF search |
| `lib/gif_query_llm.py` | Micro-LLM Tenor/GIF search query picker |
| `lib/gifs.py` | Automatic GIF follow-up orchestration |

### Schedule additions

| Job | Cron | Handler |
|-----|------|---------|
| `quiet_outreach` | `*/15 * * * *` | `schedule/quiet_outreach.py` |

---

## Tier 4 — Discord-native capabilities (v1.2.0)

### Slash commands

- Added `/ask`, `/summarize`, and `/remember` via `handlers/slash_commands.py`
- Commands register on bot connect and sync globally (`CommandTree.sync()`)
- **`/ask`** — emits a `discord_message` daemon event with the user's prompt (requires an active Schedule task)
- **`/summarize`** — builds a transcript from channel history and sends a summarize prompt to the LLM (5–50 messages)
- **`/remember`** — saves text to self-contained SQLite pinned memory (works immediately, no Schedule task)
- Global toggle: **Slash Commands** in plugin settings

### Rich messages

- Auto-replies now **quote the triggering message** via Discord `message.reference`
- `reply_to_message_id` included on all daemon event payloads
- Extended **`discord_send_message`** tool:
  - `reply_to_message_id`
  - `embed_title`, `embed_description`, `embed_color`
- New **`discord_upload_file`** tool — upload a file with optional caption
- Shared send stack: `lib/send.py`, `lib/embeds.py`

### Moderation & safety

- New `lib/safety.py` gate layer (runs before batching / LLM):
  - **Permission check** — skip channels where the bot lacks Send Messages
  - **Per-user rate limit** — configurable min gap + burst cap per time window
  - **Content blocklist** — comma-separated terms; matches dropped before LLM
- Failures recorded in debug traces under the `safety` gate
- Settings UI: **Safety & Moderation** card (permissions, rate limits, blocklist)

### Pinned memory

- New `pinned_memories` SQLite table in `lib/store.py`
- `/remember` and pinned entries injected in auto-recall as `[Pinned memories — saved via /remember]`
- Memory stats API includes `pinned_count`

### New / updated modules

| Module | Purpose |
|--------|---------|
| `lib/events.py` | Build and emit `discord_message` events (slash + shared path) |
| `lib/embeds.py` | Embed construction and color parsing |
| `lib/safety.py` | Permissions, rate limits, content filter |
| `handlers/slash_commands.py` | Slash command handlers |

---

## Tier 3 — Personality & presence controls (v1.1.0)

### Personality presets

- Presets: **Lurker**, **Helper**, **Chatterbox**, **Moderator** (`lib/presets.py`)
- Preset dropdown in settings; fills underlying sliders on selection
- **`custom`** preset when values are hand-tuned

### Reply modes & access control

- **Reply mode** per global / server / channel: `default`, `mentions_only`, `reactions_only`, `never`
- **Keyword triggers** — soft @mention via configured words (e.g. `help`, `mod`)
- **Always-respond role IDs** — role mention or member with role always queues a reply
- **User denylist / allowlist** and **bot allowlist** with optional **ignore all bots**
- Per-server **channel overrides** (channel ID or name + reply mode) in server settings UI

### Direct messages

- Separate **DM settings**: human reply chance, reaction chance, cooldown
- Merged in `get_effective_settings()` when `is_dm=True`

### Scheduled presence

- **Quiet hours (UTC)** — suppress random replies; modes: reactions-only or fully silent (`lib/presence.py`)
- **Activity decay** — lower reply chance when a channel exceeds N messages in 5 minutes (`lib/activity.py`)
- **Morning greeting** — hourly Sapphire schedule posts to configured `account:guild_id:channel_id` targets (`schedule/morning_greeting.py`)

### Richer reactions

- **Reaction cooldown** separate from reply cooldown (default 30s)
- **Sentiment emoji rules** — blocks inappropriate emoji on negative messages (e.g. no 👍 on sad posts); configurable via `reaction_blocked_rules`

### Gate refactor

- Central gate evaluation in `lib/gates.py` (`should_queue_reply`, `evaluate_triggers`, `check_user_access`)
- `handlers/on_message.py` refactored to use gates + trace logging

### Settings & UI

- Extended global and per-server settings API (`routes/settings.py`)
- New settings sections: Presence & Access, Direct Messages, Morning Greeting, Channel Override
- `GET /api/plugin/leona_discord/channels` — list text channels for a guild

---

## Tier 2 — Conversation quality

### Self-contained persistent memory

- **No MemPalace or other Sapphire plugins required** — all memory lives inside `leona_discord`
- SQLite store at `user/plugin_data/leona_discord/discord_memory.sqlite`
- **`lib/store.py`** — messages, keyword search, debug traces, retention (10k messages/channel)
- **`lib/history.py`** — hot in-memory cache (100 messages/channel) synced to SQLite on write; survives restarts
- **`lib/memory.py`** — seamless auto-recall injected at batch flush (no tool calls)
- **`lib/paths.py`** — plugin data directory helpers

### Seamless prompt injection

- At batch time: recent transcript + keyword search + pinned context prepended to LLM payload
- Memory block injected in `lib/batching.py` before `emit_daemon_event("discord_message", …)`
- Executor receives `recent_history` as **Recent chat** (same path as before, now backed by SQLite)

### Context overhead caps

- **100 messages** remain in cache/DB for mentions and search — not all sent to the LLM
- **LLM injection defaults**: 25 lines × 280 chars/line (configurable `history_inject_limit`, `history_line_max_chars`)
- Images in history shown as `(+N image)` instead of full URLs
- Older memory recall: up to 5 hits, ~300 token budget; excludes IDs already in injected transcript
- Settings UI fields for inject limit, line max chars, memory token budget

### Debug traces

- **`lib/trace.py`** — gate-by-gate “why didn’t I respond?” logging to SQLite
- **`routes/traces.py`** — `GET /traces`, `GET /memory/stats`
- Settings UI: **Response Debug Traces** panel
- Global toggle: `debug_trace_enabled`

### Settings additions

- `memory_enabled`, `memory_max_tokens`, `memory_search_threshold`
- `history_inject_limit`, `history_line_max_chars`
- `always_online`, `debug_trace_enabled` (global)

---

## Tier 1 — Foundation & reliability

### Architecture split

Monolithic `daemon.py` (~1,700 lines) split into focused modules:

```
leona_discord/
├── daemon.py              # Thin lifecycle entry (~115 lines)
├── lib/                   # Shared logic
├── handlers/              # Discord event handlers
├── routes/                # HTTP settings & accounts API
└── web/                   # Settings UI
```

| Module | Purpose |
|--------|---------|
| `lib/batching.py` | Per-channel message batching and event emission |
| `lib/connection.py` | Connect/disconnect with rate-limit safeguards |
| `lib/context_cache.py` | Reply context, pending payloads, reaction dedupe |
| `lib/cooldowns.py` | Probabilistic reply cooldown tracking |
| `lib/history.py` | Channel history (initial in-memory; Tier 2 adds SQLite) |
| `lib/images.py` | Image collection and vision-model description |
| `lib/mentions.py` | @name and custom emoji resolution |
| `lib/messages.py` | Long message splitting |
| `lib/reactions.py` | Sentiment-based silent reactions |
| `lib/send.py` | Discord send helper |
| `lib/settings.py` | Settings merge and live reads |
| `lib/state.py` | Shared daemon state |
| `lib/typing_indicator.py` | Typing indicator during waits |
| `handlers/on_message.py` | Message event handler |
| `handlers/reply_handler.py` | LLM response routing back to channels |

Public API re-exported from `daemon.py` for backward compatibility (`get_client`, `get_loop`, `_connect_single`, etc.).

### Reliability improvements

| Feature | Behavior |
|---------|----------|
| **Send-count guard** | `discord_send_message` increments per-account counter; reply handler skips if tool already sent |
| **`auto_reply` respect** | Reply handler honors per-task `auto_reply`; defaults **on** when unset |
| **Connect cooldown & stagger** | Reconnect cooldown; 5s stagger between multi-account connects |
| **429 retry** | Up to 3 connect attempts with backoff on rate limit |
| **Always online toggle** | Connect all accounts on startup, or only when a Schedule daemon task is active |
| **Event-not-accepted cleanup** | Clears pending reply state when no task accepts the batch |

### Production cleanup

- Removed debug prints from `tools/discord_tools.py`
- `on_message` logging moved to DEBUG level
- Reaction dedupe and settings loading cleaned up in tools layer

### Settings & UI (Tier 1 baseline)

- Per-server overrides for response chances, cooldown, reactions, image understanding
- **Always Online** toggle in Global Settings
- Host **Save Changes** button wired via `_saveAllSettings()` (was previously a no-op)
- Unified settings registry in `web/index.js`

---

## Version summary

| Version | Tier | Focus |
|---------|------|--------|
| — | Tier 1 | Modular architecture, reliability, cleanup |
| — | Tier 2 | SQLite memory, seamless recall, debug traces, context caps |
| 1.1.0 | Tier 3 | Presets, reply modes, presence, safety-adjacent gates |
| 1.2.0 | Tier 4 | Slash commands, rich messages, moderation layer |
| 1.3.0 | Tier 5 | LLM greetings, quiet outreach, GIF replies, vision UI fix |
| 1.4.0 | — | Human-like timing, sending patterns, reaction/engagement behavior, technical improvements |

---

## Dependencies & setup notes

- **Required for reactions**: `pip install vaderSentiment`
- **Optional (better sentiment)**: `pip install transformers torch`
- **Slash commands**: enable `applications.commands` OAuth scope when inviting the bot
- **Memory data**: `user/plugin_data/leona_discord/discord_memory.sqlite`
- **Schedule tasks**: `/ask`, `/summarize`, and normal channel replies require an active `discord_message` daemon task for the bot account
- **Morning greeting & quiet outreach**: require bot online (**Always Online** or active Schedule task) plus Sapphire continuity scheduler
- **GIF replies**: Klipy API key (recommended) or Giphy key; optional fast/cheap LLM for query selection; `requests` used for provider HTTP calls
- **Tenor**: legacy GIF provider only — migrate to Klipy or Giphy before **June 30, 2026**
