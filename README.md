# Leona Discord Plugin

Personality-oriented Discord integration for Sapphire — long-running bot daemon, human-like reply timing, self-contained memory, and optional per-user relationship profiling. **Current version: 1.5.3**

This is a fork of the stock `plugins/discord` plugin. The stock plugin is **not modified**.

For detailed settings documentation, see [`configuration_guide.md`](configuration_guide.md). For profiling internals, see [`user_profiling_design.md`](user_profiling_design.md). For release history, see [`CHANGELOG.md`](CHANGELOG.md).

## Setup

1. Create a bot at [discord.com/developers](https://discord.com/developers)
2. Enable **Message Content Intent** under Bot → Privileged Gateway Intents
3. Add the bot to your server using an OAuth2 invite link (scopes: `bot`, `applications.commands`)
4. Enter the bot token and account name in the plugin settings UI (**Settings → Leona Discord**)

The bot uses its configured **display name** in slash-command descriptions and proactive messages (not a hardcoded name).

## Required Dependencies

### vaderSentiment (required for reactions)

```bash
pip install vaderSentiment
```

VADER is the **default and recommended** backend for silent reactions — lightweight, no model downloads.

### DistilBERT (optional — better sentiment on Discord text)

```bash
pip install transformers torch
```

DistilBERT (`cardiffnlp/twitter-roberta-base-sentiment-latest`) handles slang, sarcasm, and emoji better than VADER. Requires ~500 MB on first use. Enable under **Reactions & Media → Sentiment Backend**.

## Features

### Message batching & replies

- Messages are batched per channel (configurable delay, default 8s) to avoid multi-message LLM trains
- Typing indicator during batch wait and LLM generation
- Long responses split at newlines, sentence boundaries, or 2000-char hard limit
- Contextual quote-replies, optional post-send edits, GIF follow-ups, and inline `[react:…]` / `[edit:…]` / `[gif:…]` tags from the LLM (parsed and stripped in `lib/inline_tags.py`; malformed tags without a closing `]` are handled gracefully)
- Variable human pause (0.5–3s) and contextual typing speed after generation
- **`discord_send_message` guard** — when auto-reply is on, the tool cannot post to the triggering channel (prevents the model from bypassing the reply handler and leaking raw tags); use inline tags or plain text instead

### Message edits & auto typos

- **LLM `[edit:…]` tags** — model sends a draft, then the reply is edited after a short pause (works on the last line of multiline replies; malformed `[edit:…` without `]` is still honoured)
- **Inline `[react:…]`** — reacts to the user's trigger message (respects reaction settings; dedup fixed so failed reactions can retry)
- **Auto Typos** (optional, off by default) — when the user's message has no `?`, a configurable chance replaces one common word with a realistic misspelling (`teh`, `definately`, transpositions, etc.), sends that version, then auto-corrects after a delay. **711-word list** in `lib/typo_wordlist.py`. Configure under **Reactions & Media → Message Edits**: enable toggle, **Auto Typo Chance** slider (0–100%), fix delay min/max. LLM `[edit:…]` always takes priority over auto typos.
- Legacy ~4% random post-send typo/thought edits still run when auto typos do not fire (`lib/reply_style.py`)

### Per-server overrides

All major settings (reply chances, cooldown, reactions, profiling, image understanding, etc.) can be overridden per guild in the UI. @mentions always bypass filters.

### Image understanding

Vision model describes images so a non-vision base model can respond. Configure provider, model name, and max tokens under **Reactions & Media**.

### Silent reactions

Emoji reactions on messages the bot does not reply to. Configure chance, scope, sentiment backend (VADER or DistilBERT), and custom allowed emoji.

### Persistent channel memory (self-contained)

All Discord memory lives inside this plugin — **no MemPalace or other Sapphire plugins required**.

- **SQLite store** at `user/plugin_data/leona_discord/discord_memory.sqlite`
- **Channel cache**: up to 100 messages per channel (survives restarts)
- **Long-term search**: up to 10,000 messages per channel for auto-recall
- **LLM injection**: recent transcript + keyword search for older relevant lines (~300 token budget)
- **Debug traces**: gate-by-gate log of reply / react-only / silent decisions (**Debug** tab)

### User profiling (v1.5+)

Optional relationship memory — who someone is to the bot and how the bot should act toward them.

- **One profile per Discord user** across all servers and DMs (keyed by `author_id`, not per-guild)
- **Passive ingest** — message counts, disposition scores (familiarity, warmth, trust, playfulness, patience, interest), topic hints
- **Prompt injection** — `[People context — internal]` block prepended before replies alongside channel memory
- **LLM distiller** — background job extracts facts and L1/L2 summaries from buffered interactions (cross-guild message history)
- **Reply modulation** — optional scaling of organic reply chance from interest/familiarity
- **Profiles tab** — inspect disposition, summaries, facts; reset a user; run distill manually
- **Slash commands** — `/remember` saves a high-confidence fact; `/forget-me` wipes the caller's global profile

Disabled by default. Enable under **Memory → User Profiling**. Legacy per-guild profile rows merge automatically on startup.

### Personality & presence

- **Presets**: Lurker, Helper, Chatterbox, Moderator
- **Reply modes**: default, mentions-only, reactions-only, never (global, per-server, or per-channel)
- **Keyword triggers**, **always-respond role IDs**, allowlists/denylists
- **Separate DM settings**, **quiet hours (UTC)**, **activity decay**
- **Morning greeting** — hourly cron; LLM-written daily message from instructions
- **Sleep schedule** — goodnight → dormant → wake; buffered overnight @mentions; optional forced wake on repeated pings
- **Quiet outreach** — proactive starters when channels go quiet

### Discord-native capabilities

- **Slash commands**: `/ask`, `/summarize`, `/remember`, `/forget-me` — synced on bot connect (`/ask` and `/summarize` need a Schedule task wired to the Discord message event)
- **Rich messages**: quote-replies, embeds via `discord_send_message` (other channels / auto-reply off only when targeting the event channel)
- **File uploads**: `discord_upload_file` tool
- **Pinned memory**: `/remember` also writes to pinned SQLite recall
- **Safety**: permission checks, per-user rate limits, content blocklist — all gate-logged

### Cooldown & name match

After responding, non-@mention messages can be ignored for a configurable period (0–600s), per-channel or global. **Name match** treats the bot's display name as a soft @mention.

### Debug traces

- **Gate traces** — gate-by-gate log of reply / react-only / silent decisions (Debug tab)
- **LLM Debug Messaging** — popup viewer for formatted prompts, injected memory/profile context, recent history, task instructions, and LLM responses (last ~40 exchanges; toggle in Debug tab). Warns when Discord received text via `discord_send_message` instead of the auto-reply path (shows what was actually sent vs the final LLM response)

## Configuration

All configuration is in the plugin settings UI. Global defaults apply everywhere unless a per-server override is set.

**Global Settings tabs:** General · Replies · Reactions & Media · Memory · Profiles · Presence · Advanced · Debug (gate traces + **LLM Debug Messaging** popup)

See [`configuration_guide.md`](configuration_guide.md) for a full walkthrough of every setting.

## Schedule tasks

Registered in `plugin.json` and run by Sapphire's scheduler:

| Task | Cron | Purpose |
|------|------|---------|
| `morning_greeting` | hourly | Post configured morning greetings |
| `quiet_outreach` | every 15 min | Proactive messages in quiet channels |
| `sleep_goodnight` | every 15 min | Goodnight, sleep state, wake handling |
| `profile_distill` | every minute | Profile distillation queue + disposition decay (when profiling enabled) |

## File structure

```
leona_discord/
├── daemon.py                  # Lifecycle entry point
├── handlers/
│   ├── on_message.py          # Discord message handler
│   ├── reply_handler.py       # LLM response routing, inline tags, auto typos
│   └── slash_commands.py      # /ask /summarize /remember /forget-me
├── lib/
│   ├── auto_typo.py           # Auto typo planning (chance, delay, question skip)
│   ├── typo_wordlist.py       # 700+ correct→typo word mappings
│   ├── inline_tags.py         # [edit]/[react]/[gif] parse & strip
│   ├── batching.py            # Message batching + profile/memory injection
│   ├── bot_identity.py        # Bot display name for prompts and slash text
│   ├── connection.py          # Bot connect/disconnect
│   ├── gates.py               # Reply/reaction gate evaluation
│   ├── history.py             # Channel history + proactive formatting
│   ├── memory.py              # Auto-recall for prompt injection
│   ├── profile.py             # Profiling ingest, recall, engagement
│   ├── profile_store.py       # SQLite: profiles, facts, buffers, pending
│   ├── profile_distill_llm.py # LLM fact/summary extraction
│   ├── llm_debug.py           # Prompt/response capture for debug UI
│   ├── settings.py            # Settings merge and live reads
│   ├── sleep_schedule.py      # Sleep/wake state
│   ├── store.py               # SQLite: messages, search, traces
│   └── …                      # reactions, images, safety, typing, etc.
├── routes/
│   ├── accounts.py
│   ├── profiles.py            # Profile list / reset / distill-now API
│   ├── settings.py
│   └── traces.py
├── schedule/
│   ├── morning_greeting.py
│   ├── quiet_outreach.py
│   ├── sleep_goodnight.py
│   └── profile_distill.py
├── tools/
│   └── discord_tools.py
├── web/
│   └── index.js               # Tabbed settings UI
├── configuration_guide.md     # Detailed settings reference
├── user_profiling_design.md   # Profiling design + implementation notes
├── CHANGELOG.md
└── plugin.json
```
