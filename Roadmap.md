What you already have (strong base)
Leona is already unusually “human” for a Discord bot plugin:

Timing layer — batch jitter, read delay, contextual typing WPM, human pause, delayed replies, reaction delay/removal
Style layer — quote-replies, [break] splits, bullet delivery lottery, post-send edits, casual emoji suffix
Engagement layer — topic interest, thread continuation, lurk weights, brevity hints
Presence layer — quiet hours, activity decay, sleep/goodnight/forced wake, morning greeting, quiet outreach
Social layer — reactions with sentiment, read-only react path, GIF follow-ups
Memory — self-contained SQLite recall + /remember
That’s a solid Stage 6+ foundation. Most worthwhile next steps are gaps in Discord surface area, cross-message continuity, and persona depth — not more random delays.

Human-like improvements (high value)
1. Per-user relationship memory
Memory is channel-centric. Humans remember people.

Track per (account, guild, user_id): last interaction, reply count, nickname, “warmth” score
Inject hints like: “You’ve chatted with Zeebie a lot this week — casual tone is fine” vs “First time hearing from this person”
Natural fit: lib/memory.py, lib/engagement.py, lib/store.py
2. Mood that persists across sessions (not just time-of-day)
style_hint.py uses UTC hour buckets; sleep/forced-wake adds schedule personality. Missing: emotional carryover.

Integrate with your emotional_state plugin (or a lightweight Leona-local version): energy/warmth/playfulness affecting reply chance, length, and reaction emoji
Sleep forced-wake already has “grumpy” hints — mood could modulate that automatically
Wire via prompt injection in lib/batching.py (same hook as style hints)
3. “Seen but typing…” abandonment
Real people sometimes start replying, then don’t.

~2–4% chance: show typing for 2–5s, then stop without sending (organic messages only)
Makes the bot feel less like a guaranteed reply machine
Hook: lib/typing_indicator.py + lib/gates.py
4. Message edit & delete awareness
message_edits_enabled covers bot edits. Users editing/deleting messages is very Discord-native.

Listen for on_message_edit / on_message_delete
Store in SQLite; inject: “User edited their message to: …” or “User deleted a message they sent 30s ago”
Occasionally react to edits (“👀”) without replying
5. Reply-to-the-wrong-message (rare)
Humans sometimes reply to an older message in a fast channel.

Low chance (~3%) in busy channels: quote-reply to a message 2–5 lines back in history instead of the trigger
Extends lib/reply_style.py quote logic you already have
6. Channel-specific personas (beyond presets)
Presets are global. Real communities have #help, #memes, #dev.

Expand per-channel overrides beyond reply_mode: tone preset, max length, reaction aggressiveness, GIF chance
UI already has channel override JSON — expose sliders in the per-server panel
7. Smarter “lurking” in active threads
You boost thread replies to the bot, but not lurking in human threads.

If 3+ humans are back-and-forth in a thread without @mention, small chance to drop a one-liner or react
Different from outreach — reactive, not proactive broadcast
8. Local time in style hints
Schedule hours are local in the UI, but build_style_hint() still uses UTC for “morning/evening” tone.

Pass browser timezone or infer from server/guild setting
Small change, noticeable for Melbourne users at 1 AM
9. Voice of the server
Learn common phrases, in-jokes, or frequent emoji from channel history (statistical, not LLM)
Inject: “This channel often uses 💀 and short messages”
Complements topic interest in lib/engagement.py
10. Imperfect memory (optional realism)
Always-perfect recall feels bot-like.

~5% chance to omit a memory hit, or phrase recall uncertainly: “I think you mentioned X before…”
Toggle in Memory settings for “human recall” mode
Ability extensions (Discord & Sapphire)
Discord features not yet handled
Feature	Why it matters
Threads
Create/rename/archive threads; reply in thread without @mention when bot was last speaker
Stickers
Describe or react; many servers communicate via stickers not text
Polls
Vote or comment on poll results
Embeds / link previews
Summarize linked content when user posts URL-only
Voice channels
Join VC, play soundboard clip, or “I’m in voice if you need me” status
Stage / events
Scheduled server events as outreach triggers
Reactions to bot messages
User reacts ✅ to bot message → treat as acknowledgment, don’t re-explain
on_reaction_add
React-only conversations (“👍 means yes”) without new messages
Tools today: discord_send_message, discord_send_gif, discord_upload_file, discord_read_messages, discord_add_reaction. Adding discord_create_thread, discord_pin_message, discord_fetch_message would unlock a lot.

Proactive features (extend Stage 5)
Idea	Description
Birthday / anniversary
SQLite dates per user; casual congrats message
“Checking in” on absent regulars
If a frequent chatter goes quiet 3+ days, soft DM or channel ping (opt-in)
Event-driven outreach
React to server boost, new member, milestone — not just quiet channels
Weekly recap
/summarize on a schedule for configured channels
Goodnight variety
Sleep already has LLM goodnight — add “still awake?” follow-up during forced wake window
Memory & intelligence
Idea	Description
Semantic search
Keyword search works; embeddings would improve “remember when we talked about X”
User notes API
/remember is global-ish; /remember @user … or per-user notes
Cross-channel recall
“You said this in #dev yesterday” (with privacy toggle)
MemPalace bridge
Optional hook if user runs both plugins — you already document self-contained memory
Safety & moderation (Stage 4 extension)
Idea	Description
Soft mod mode
Warn on blocklist near-misses instead of silent drop
Escalation
After N blocked messages from user, DM mods or post to mod channel
Spam burst detection
Complement rate limit with “this feels like spam” gate
UI / ops
Idea	Description
Live “bot mood” dashboard
Show asleep/forced-awake channels, outreach cooldowns, engagement weights
Per-channel trace filter
Debug traces are powerful but noisy at scale
Test sleep / test forced wake
Like “Send test greeting” — simulate without waiting for 1 AM
Infrastructure gaps worth fixing first
These aren’t flashy but unblock realism:

core_patch_required.md — multimodal image blocks in executor; without upstream merge, vision path is fragile
README still says “Tier 3/4” — minor doc drift vs CHANGELOG “Stage” naming
engagement_weight only in JSON — power feature hidden from UI; exposing it would help tuning
No on_message_edit handler — big gap for Discord-native behavior
Presence cycling is generic — could show “sleeping”, “in #general”, or custom status during forced wake
Suggested priority (if you pick a few)
Quick wins (1–2 sessions each)

Local timezone in style_hint.py
Message edit listener + prompt injection
Test buttons for sleep / forced wake
Expose engagement weight in per-server UI
Medium (high human feel)
5. Per-user relationship memory
6. emotional_state integration (or built-in mood)
7. Typing-then-abandon behavior
8. Reaction-to-bot acknowledgment path

Larger (capability)
9. Thread + sticker support
10. Semantic memory / embeddings
11. New slash commands (/poll, /thread, /note @user)
12. Voice channel presence (even status-only)

Integration with your other plugins
You already have adjacent plugins in the repo that Leona could optionally compose with:

emotional_state — mood → reply length, reaction choice, sleep grumpiness
associative-reach — relationship injection across sessions
mempalace — deeper long-term memory for power users who want it
Sapphire-priority-triage — classify urgent @mentions during sleep before buffering
Composition via hooks (like other Sapphire plugins) keeps Leona self-contained by default but richer when stacked.

If you want to implement next, the highest ROI for “more human” with your current sleep schedule setup would be: per-user memory + message-edit awareness + emotional_state hook + local-time style hints. Say which direction you prefer (more human vs more Discord features) and we can spec one of them properly.
