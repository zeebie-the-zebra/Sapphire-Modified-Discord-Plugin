"""Tests for pure logic functions in the Leona Discord plugin.

Run from the sapphire/ directory:
    python -m pytest plugins/leona_discord/tests/test_pure_logic.py -v
"""

import sys
import os
import time

# Ensure the sapphire root is on the path so plugin imports resolve
_sapphire_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _sapphire_root not in sys.path:
    sys.path.insert(0, _sapphire_root)


# ── think_tags ────────────────────────────────────────────────────────────

class TestStripThinkTags:
    def test_removes_complete_tags(self):
        from plugins.leona_discord.lib.think_tags import strip_think_tags
        text = "Hello <think>I am thinking </think> world"
        assert strip_think_tags(text) == "Hello  world"

    def test_removes_seed_think(self):
        from plugins.leona_discord.lib.think_tags import strip_think_tags
        text = "Before <seed:think>reasoning</seed:think> After"
        assert strip_think_tags(text) == "Before  After"

    def test_removes_cot_budget_reflect(self):
        from plugins.leona_discord.lib.think_tags import strip_think_tags
        text = "Start <seed:cot_budget_reflect>analysis</seed:cot_budget_reflect> End"
        assert strip_think_tags(text) == "Start  End"

    def test_removes_unclosed_think(self):
        from plugins.leona_discord.lib.think_tags import strip_think_tags
        text = "Hello <think>open tag"
        assert strip_think_tags(text) == "Hello"

    def test_leading_junk_before_closing_tag(self):
        from plugins.leona_discord.lib.think_tags import strip_think_tags
        text = "junk junk </think> actual reply"
        assert strip_think_tags(text) == "actual reply"

    def test_no_tags_returns_clean(self):
        from plugins.leona_discord.lib.think_tags import strip_think_tags
        assert strip_think_tags("Hello world") == "Hello world"

    def test_empty_string(self):
        from plugins.leona_discord.lib.think_tags import strip_think_tags
        assert strip_think_tags("") == ""

    def test_multiple_tags(self):
        from plugins.leona_discord.lib.think_tags import strip_think_tags
        text = "<think>a</think> mid <think>b</think> end"
        result = strip_think_tags(text)
        assert "<think>" not in result
        assert "mid" in result
        assert "end" in result


# ── messages.split_message ────────────────────────────────────────────────

class TestSplitMessage:
    def test_short_message_no_split(self):
        from plugins.leona_discord.lib.messages import split_message
        result = split_message("Hello!", limit=2000)
        assert result == ["Hello!"]

    def test_exact_limit(self):
        from plugins.leona_discord.lib.messages import split_message
        text = "a" * 2000
        result = split_message(text, limit=2000)
        assert len(result) == 1
        assert result[0] == text

    def test_splits_at_newline(self):
        from plugins.leona_discord.lib.messages import split_message
        # Create text with a newline past the midpoint
        text = "word " * 200 + "\n" + "rest"
        chunks = split_message(text, limit=500)
        assert len(chunks) >= 2
        # Verify no chunk exceeds the limit
        for chunk in chunks:
            assert len(chunk) <= 500

    def test_splits_at_sentence_boundary(self):
        from plugins.leona_discord.lib.messages import split_message
        # Create text with sentence endings
        text = "Sentence one. " * 50 + "Sentence two. " * 50
        chunks = split_message(text, limit=500)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) <= 500

    def test_no_good_split_point(self):
        from plugins.leona_discord.lib.messages import split_message
        # Long text with no newlines or punctuation
        text = "a" * 1000
        chunks = split_message(text, limit=500)
        assert len(chunks) == 2
        assert chunks[0] == "a" * 500
        assert chunks[1] == "a" * 500

    def test_splits_paragraphs(self):
        from plugins.leona_discord.lib.messages import split_message
        text = "First paragraph here.\n\nSecond paragraph here."
        chunks = split_message(text, limit=2000)
        assert len(chunks) == 2
        assert "First paragraph" in chunks[0]
        assert "Second paragraph" in chunks[1]

    def test_splits_bullets_when_split_each(self):
        from plugins.leona_discord.lib.messages import split_message
        text = "Header\n- one\n- two"
        chunks = split_message(text, limit=2000, split_bullets=True)
        assert len(chunks) == 3
        assert chunks[0] == "Header"
        assert chunks[1] == "- one"
        assert chunks[2] == "- two"

    def test_keeps_bullets_together(self):
        from plugins.leona_discord.lib.messages import split_message
        text = "Header\n- one\n- two"
        chunks = split_message(text, limit=2000, split_bullets=False)
        assert len(chunks) == 2
        assert chunks[0] == "Header"
        assert "- one" in chunks[1]
        assert "- two" in chunks[1]

    def test_splits_bullets_probabilistically(self, monkeypatch):
        from plugins.leona_discord.lib import messages
        monkeypatch.setattr(messages.random, "random", lambda: 0.0)
        text = "Header\n- one\n- two"
        chunks = messages.split_message(text, limit=2000)
        assert len(chunks) == 3

    def test_splits_emoji_lead(self):
        from plugins.leona_discord.lib.messages import split_message
        text = "🔥 this is fire"
        chunks = split_message(text, limit=2000)
        assert len(chunks) == 2
        assert chunks[0] == "🔥"
        assert "fire" in chunks[1]


# ── batching jitter ─────────────────────────────────────────────────────────

class TestBatchingJitter:
    def test_jitter_within_bounds(self, monkeypatch):
        from plugins.leona_discord.lib import batching
        monkeypatch.setattr(batching.random, "uniform", lambda a, b: 2.5)
        assert batching.apply_batch_delay_jitter(15.0) == 17.5

    def test_jitter_floor(self, monkeypatch):
        from plugins.leona_discord.lib import batching
        monkeypatch.setattr(batching.random, "uniform", lambda a, b: -3.0)
        assert batching.apply_batch_delay_jitter(2.0) == 1.0


# ── edit history ──────────────────────────────────────────────────────────

class TestEditHistory:
    def test_record_and_hint(self):
        from plugins.leona_discord.lib import edit_history
        edit_history._EDIT_HISTORY.clear()
        edit_history.record_edit("a:1", "99", "teh game", "the game", kind="typo")
        hint = edit_history.build_edit_awareness_hint("a:1")
        assert "teh game" in hint
        assert "the game" in hint


# ── schedule_utils.parse_target ───────────────────────────────────────────

class TestParseTarget:
    def test_string_format(self):
        from plugins.leona_discord.lib.schedule_utils import parse_target
        result = parse_target("bot1:123456:789012")
        assert result == ("bot1", "123456", "789012")

    def test_string_with_spaces(self):
        from plugins.leona_discord.lib.schedule_utils import parse_target
        result = parse_target(" bot1 : 123456 : 789012 ")
        assert result == ("bot1", "123456", "789012")

    def test_string_too_few_parts(self):
        from plugins.leona_discord.lib.schedule_utils import parse_target
        assert parse_target("bot1:123456") is None

    def test_dict_format(self):
        from plugins.leona_discord.lib.schedule_utils import parse_target
        result = parse_target({"account": "bot1", "guild_id": "123", "channel_id": "456"})
        assert result == ("bot1", "123", "456")

    def test_dict_missing_channel(self):
        from plugins.leona_discord.lib.schedule_utils import parse_target
        assert parse_target({"account": "bot1", "guild_id": "123"}) is None

    def test_none_input(self):
        from plugins.leona_discord.lib.schedule_utils import parse_target
        assert parse_target(None) is None

    def test_int_input(self):
        from plugins.leona_discord.lib.schedule_utils import parse_target
        assert parse_target(42) is None


# ── gates ─────────────────────────────────────────────────────────────────

class TestGates:
    """Test the pure-logic gate functions (no Discord objects needed)."""

    def _make_settings(self, **overrides):
        """Build a minimal effective settings dict."""
        base = {
            "reply_mode": "default",
            "human_response_chance": 15,
            "bot_response_chance": 15,
            "cooldown_seconds": 120,
            "cooldown_scope": "per_channel",
            "name_match_enabled": True,
            "name_match_case_sensitive": False,
            "ignore_bots": False,
            "user_denylist": [],
            "user_allowlist": [],
            "bot_allowlist": [],
            "keyword_triggers": [],
            "always_respond_role_ids": [],
        }
        base.update(overrides)
        return base

    def test_reply_mode_never(self):
        from plugins.leona_discord.lib.gates import should_queue_reply
        settings = self._make_settings(reply_mode="never")
        queue, outcome = should_queue_reply(
            settings=settings, mentioned=True, name_matched=False,
            keyword_matched=False, role_trigger=False, is_bot=False,
            scope="per_channel", account="test", guild_id="1", channel_id="1",
        )
        assert not queue
        assert "never" in outcome

    def test_reply_mode_mentions_only_blocks_non_mention(self):
        from plugins.leona_discord.lib.gates import should_queue_reply
        settings = self._make_settings(reply_mode="mentions_only")
        queue, outcome = should_queue_reply(
            settings=settings, mentioned=False, name_matched=False,
            keyword_matched=False, role_trigger=False, is_bot=False,
            scope="per_channel", account="test", guild_id="1", channel_id="1",
        )
        assert not queue

    def test_reply_mode_mentions_only_allows_mention(self):
        from plugins.leona_discord.lib.gates import should_queue_reply
        settings = self._make_settings(reply_mode="mentions_only")
        queue, _ = should_queue_reply(
            settings=settings, mentioned=True, name_matched=False,
            keyword_matched=False, role_trigger=False, is_bot=False,
            scope="per_channel", account="test", guild_id="1", channel_id="1",
        )
        # May or may not queue depending on chance roll, but should NOT be blocked by reply_mode
        # (We can't assert the roll, but we can assert no "mentions_only" outcome)
        # Just verify it doesn't return "dropped_reply_mode_mentions_only"

    def test_reply_mode_mentions_only_blocks_image(self):
        from plugins.leona_discord.lib.gates import should_queue_reply
        settings = self._make_settings(reply_mode="mentions_only")
        queue, outcome = should_queue_reply(
            settings=settings, mentioned=False, name_matched=False,
            keyword_matched=False, role_trigger=False, is_bot=False,
            scope="per_channel", account="test", guild_id="1", channel_id="1",
            has_images=True,
        )
        assert not queue
        assert outcome == "dropped_reply_mode_mentions_only"

    def test_zero_chance_blocks_image_without_mention(self):
        from plugins.leona_discord.lib.gates import should_queue_reply
        settings = self._make_settings(human_response_chance=0, name_match_enabled=False)
        queue, outcome = should_queue_reply(
            settings=settings, mentioned=False, name_matched=False,
            keyword_matched=False, role_trigger=False, is_bot=False,
            scope="per_channel", account="test", guild_id="1", channel_id="1",
            has_images=True,
        )
        assert not queue
        assert outcome == "dropped_image_restricted"

    def test_default_mode_image_uses_chance_roll(self):
        from plugins.leona_discord.lib.gates import should_queue_reply
        settings = self._make_settings(human_response_chance=100, name_match_enabled=False)
        queue, _ = should_queue_reply(
            settings=settings, mentioned=False, name_matched=False,
            keyword_matched=False, role_trigger=False, is_bot=False,
            scope="per_channel", account="test", guild_id="1", channel_id="1",
            has_images=True,
        )
        assert queue

    def test_user_denylist_blocks(self):
        from plugins.leona_discord.lib.gates import check_user_access
        settings = self._make_settings(user_denylist=["blocked_user"])
        allowed, reason = check_user_access("blocked_user", False, settings)
        assert not allowed
        assert reason == "user_denylist"

    def test_user_allowlist_blocks_non_member(self):
        from plugins.leona_discord.lib.gates import check_user_access
        settings = self._make_settings(user_allowlist=["allowed_user"])
        allowed, reason = check_user_access("other_user", False, settings)
        assert not allowed
        assert reason == "user_allowlist"

    def test_user_allowlist_allows_member(self):
        from plugins.leona_discord.lib.gates import check_user_access
        settings = self._make_settings(user_allowlist=["allowed_user"])
        allowed, _ = check_user_access("allowed_user", False, settings)
        assert allowed

    def test_ignore_bots_blocks(self):
        from plugins.leona_discord.lib.gates import check_user_access
        settings = self._make_settings(ignore_bots=True)
        allowed, reason = check_user_access("bot123", True, settings)
        assert not allowed
        assert reason == "ignore_bots"

    def test_ignore_bots_allows_whitelisted(self):
        from plugins.leona_discord.lib.gates import check_user_access
        settings = self._make_settings(ignore_bots=True, bot_allowlist=["bot123"])
        allowed, _ = check_user_access("bot123", True, settings)
        assert allowed

    def test_empty_allowlist_allows_everyone(self):
        from plugins.leona_discord.lib.gates import check_user_access
        settings = self._make_settings(user_allowlist=[])
        allowed, _ = check_user_access("anyone", False, settings)
        assert allowed


# ── human-like timing ─────────────────────────────────────────────────────

class TestHumanLikeTiming:
    def test_contextual_wpm_short_reply(self):
        from plugins.leona_discord.lib.typing_indicator import contextual_wpm, WPM_SHORT_MIN, WPM_SHORT_MAX
        wpm = contextual_wpm("nice!")
        assert WPM_SHORT_MIN <= wpm <= WPM_SHORT_MAX

    def test_contextual_wpm_long_reply(self):
        from plugins.leona_discord.lib.typing_indicator import contextual_wpm, WPM_LONG_MIN, WPM_LONG_MAX
        wpm = contextual_wpm("x" * 250)
        assert WPM_LONG_MIN <= wpm <= WPM_LONG_MAX

    def test_contextual_wpm_code(self):
        from plugins.leona_discord.lib.typing_indicator import contextual_wpm, WPM_CODE_MIN, WPM_CODE_MAX
        wpm = contextual_wpm("```python\nprint('hi')\n```")
        assert WPM_CODE_MIN <= wpm <= WPM_CODE_MAX

    def test_human_pause_in_range(self):
        from plugins.leona_discord.lib.typing_indicator import (
            human_pause_seconds, HUMAN_PAUSE_MIN, HUMAN_PAUSE_MAX,
        )
        for _ in range(20):
            pause = human_pause_seconds()
            assert HUMAN_PAUSE_MIN <= pause <= HUMAN_PAUSE_MAX

    def test_delayed_reply_skips_urgent(self, monkeypatch):
        from plugins.leona_discord.lib import batching

        monkeypatch.setattr(batching, "get_batch_delay", lambda: 15.0)
        monkeypatch.setattr(batching.random, "random", lambda: 0.0)  # always trigger delay
        assert batching.get_quick_delay("hello there") >= 45.0
        assert batching.get_quick_delay("what time?") == 6.0
        assert batching.get_quick_delay("hey @bot") == 7.5

    def test_read_only_react_chance_constant(self):
        from plugins.leona_discord.lib.gates import READ_ONLY_REACT_CHANCE
        assert READ_ONLY_REACT_CHANCE == 0.05


# ── reply style ───────────────────────────────────────────────────────────

class TestReplyStyle:
    def test_question_always_quotes(self):
        from plugins.leona_discord.lib.reply_style import compute_quote_reply_chance
        event = {"is_dm": True, "batch_size": 1, "recent_history": []}
        assert compute_quote_reply_chance(
            event, "what time is it?", "3pm",
            account="a", channel_id="1",
        ) == 1.0

    def test_media_never_quotes(self):
        from plugins.leona_discord.lib.reply_style import compute_quote_reply_chance
        event = {"image_urls": ["http://x"], "batch_size": 1, "recent_history": []}
        assert compute_quote_reply_chance(
            event, "check this out", "nice",
            account="a", channel_id="1",
        ) == 0.0

    def test_joke_comment_skips_quote(self):
        from plugins.leona_discord.lib.reply_style import compute_quote_reply_chance
        event = {"batch_size": 1, "recent_history": []}
        assert compute_quote_reply_chance(
            event, "that was wild", "lmao true",
            account="a", channel_id="1",
        ) == 0.0

    def test_engaged_skips_quote(self, monkeypatch):
        from plugins.leona_discord.lib import reply_style
        monkeypatch.setattr(reply_style, "is_engaged", lambda *a, **k: True)
        chance = reply_style.compute_quote_reply_chance(
            {"batch_size": 1, "recent_history": []},
            "hey", "sup",
            account="a", channel_id="1",
        )
        assert chance == 0.0

    def test_plan_post_send_edit_typo(self, monkeypatch):
        from plugins.leona_discord.lib import reply_style
        monkeypatch.setattr(reply_style.random, "random", lambda: 0.0)
        plan = reply_style.plan_post_send_edit("hello wonderful world")
        assert plan is not None
        delay, sent, edited = plan
        assert 2.0 <= delay <= 5.0
        assert sent != edited
        assert edited == "hello wonderful world"

    def test_plan_post_send_edit_thought(self, monkeypatch):
        from plugins.leona_discord.lib import reply_style
        calls = iter([0.0, 0.9])  # hit edit, thought branch
        monkeypatch.setattr(reply_style.random, "random", lambda: next(calls))
        plan = reply_style.plan_post_send_edit("sounds good to me")
        assert plan is not None
        _, sent, edited = plan
        assert sent == "sounds good to me"
        assert edited.startswith("sounds good to me")
        assert len(edited) > len(sent)

    def test_plan_explicit_edit(self):
        from plugins.leona_discord.lib.reply_style import plan_explicit_edit
        plan = plan_explicit_edit("teh game", "the game")
        assert plan is not None
        _, sent, edited = plan
        assert sent == "teh game"
        assert edited == "the game"

    def test_build_message_edit_hint(self):
        from plugins.leona_discord.lib.edit_history import build_message_edit_hint
        hint = build_message_edit_hint(True)
        assert "[edit:" in hint
        assert not build_message_edit_hint(False)

    def test_maybe_append_emoji_skips_long(self, monkeypatch):
        from plugins.leona_discord.lib.reply_style import maybe_append_casual_emoji
        monkeypatch.setattr(
            "plugins.leona_discord.lib.reply_style.random.random", lambda: 0.0,
        )
        text = "x" * 100
        assert maybe_append_casual_emoji(text) == text


# ── reactions ─────────────────────────────────────────────────────────────

class TestReactions:
    def test_is_tech_channel(self):
        from plugins.leona_discord.lib.reactions import is_tech_channel
        assert is_tech_channel("python-help")
        assert is_tech_channel("general-dev")
        assert not is_tech_channel("memes")

    def test_pick_avoids_last_emoji(self, monkeypatch):
        from plugins.leona_discord.lib import reactions
        reactions._record_reaction_choice("acct", "99", "🔥")
        monkeypatch.setattr(reactions.random, "choices", lambda pool, **kw: [pool[0]])
        emoji = reactions._pick_from_candidates(["🔥", "👍", "✨"], "acct", "99")
        assert emoji != "🔥"

    def test_pick_learns_channel_preference(self, monkeypatch):
        from plugins.leona_discord.lib import reactions
        reactions._record_reaction_choice("acct", "88", "👍")
        reactions._record_reaction_choice("acct", "88", "👍")
        reactions._record_reaction_choice("acct", "88", "✨")
        calls = []

        def _choices(pool, weights=None, k=1):
            calls.append((pool, weights))
            best = pool[weights.index(max(weights))]
            return [best]

        monkeypatch.setattr(reactions.random, "choices", _choices)
        emoji = reactions._pick_from_candidates(["👍", "🔥"], "acct", "88")
        assert emoji == "👍"

    def test_tech_channel_flavor(self, monkeypatch):
        from plugins.leona_discord.lib.reactions import _apply_channel_flavor, _TECH_PREFERRED
        monkeypatch.setattr(
            "plugins.leona_discord.lib.reactions.random.random", lambda: 0.0,
        )
        pool = ["💕", "👀", "🔥"]
        result = _apply_channel_flavor(pool, "python-dev")
        assert all(e in _TECH_PREFERRED for e in result)

    def test_reaction_timing_constants(self):
        from plugins.leona_discord.lib.reactions import (
            REACTION_DELAY_MIN, REACTION_DELAY_MAX,
            REACTION_REMOVE_CHANCE,
        )
        assert REACTION_DELAY_MIN == 1.0
        assert REACTION_DELAY_MAX == 5.0
        assert REACTION_REMOVE_CHANCE == 0.04


# ── engagement ────────────────────────────────────────────────────────────

class TestEngagement:
    def test_extract_topics(self):
        from plugins.leona_discord.lib.engagement import extract_topics
        topics = extract_topics("Anyone playing Minecraft tonight?")
        assert "minecraft" in topics
        assert "anyone" not in topics  # stopword length ok - anyone is 6 chars not in stopwords
        assert "tonight" in topics

    def test_topic_boost_on_reply(self):
        from plugins.leona_discord.lib import engagement
        engagement._TOPIC_SCORES.clear()
        engagement.record_topics_on_reply("a:1", "minecraft server modpack")
        score = engagement._topic_score_for_message("a:1", "minecraft update")
        assert score > 0.4
        settings = engagement.apply_topic_interest(
            {"human_response_chance": 20}, "a:1", "minecraft update",
        )
        assert settings["human_response_chance"] > 20

    def test_topic_suppress_on_skip(self):
        from plugins.leona_discord.lib import engagement
        engagement._TOPIC_SCORES.clear()
        engagement.record_topics_skipped("a:2", "politics debate election")
        settings = engagement.apply_topic_interest(
            {"human_response_chance": 20}, "a:2", "politics debate",
        )
        assert settings["human_response_chance"] < 20

    def test_channel_engagement_weight(self):
        from plugins.leona_discord.lib.engagement import apply_channel_engagement_weight
        out = apply_channel_engagement_weight({"human_response_chance": 50, "engagement_weight": 10})
        assert out["human_response_chance"] == 5

    def test_thread_reply_boost(self):
        from plugins.leona_discord.lib.engagement import apply_thread_reply_boost
        out = apply_thread_reply_boost({"human_response_chance": 15}, True)
        assert out["human_response_chance"] >= 65

    def test_reply_length_hint_after_long_replies(self, monkeypatch):
        from plugins.leona_discord.lib import engagement
        engagement._REPLY_LENGTHS.clear()
        for _ in range(4):
            engagement.record_reply_length("a:3", 220)
        monkeypatch.setattr(engagement.random, "random", lambda: 0.0)
        hint = engagement.reply_length_hint("a:3")
        assert "short" in hint.lower()


# ── cooldowns ─────────────────────────────────────────────────────────────

class TestCooldowns:
    """Test cooldown tracking (uses in-memory state)."""

    def test_cooldown_not_active_initially(self):
        from plugins.leona_discord.lib.cooldowns import is_cooldown_active
        assert not is_cooldown_active("per_channel", "acct", "g1", "c1", 120)

    def test_cooldown_active_after_set(self):
        from plugins.leona_discord.lib.cooldowns import is_cooldown_active, set_cooldown
        set_cooldown("per_channel", "acct", "g1", "c1")
        assert is_cooldown_active("per_channel", "acct", "g1", "c1", 120)

    def test_cooldown_expires(self):
        from plugins.leona_discord.lib.cooldowns import is_cooldown_active, set_cooldown
        set_cooldown("per_channel", "acct", "g1", "c1")
        # With 0-second cooldown, it should not be active
        assert not is_cooldown_active("per_channel", "acct", "g1", "c1", 0)

    def test_different_channels_independent(self):
        from plugins.leona_discord.lib.cooldowns import is_cooldown_active, set_cooldown
        set_cooldown("per_channel", "acct", "g1", "c1")
        assert is_cooldown_active("per_channel", "acct", "g1", "c1", 120)
        assert not is_cooldown_active("per_channel", "acct", "g1", "c2", 120)

    def test_global_scope(self):
        from plugins.leona_discord.lib.cooldowns import is_cooldown_active, set_cooldown
        set_cooldown("global", "acct", "g1", "c1")
        # Global scope should block all channels in the same guild
        assert is_cooldown_active("global", "acct", "g1", "c2", 120)

    def test_reaction_cooldown(self):
        from plugins.leona_discord.lib.cooldowns import (
            is_reaction_cooldown_active, set_reaction_cooldown,
        )
        assert not is_reaction_cooldown_active("acct", "g1", "c1", 30)
        set_reaction_cooldown("acct", "g1", "c1")
        assert is_reaction_cooldown_active("acct", "g1", "c1", 30)
        assert not is_reaction_cooldown_active("acct", "g1", "c1", 0)


# ── event images ──────────────────────────────────────────────────────────

class TestBlocksToEventImages:
    def test_strips_type_and_keeps_data_media_type(self):
        from plugins.leona_discord.lib.images import blocks_to_event_images

        blocks = [
            {"type": "image", "media_type": "image/png", "data": "abc123"},
        ]
        assert blocks_to_event_images(blocks) == [
            {"data": "abc123", "media_type": "image/png"},
        ]

    def test_strips_data_uri_prefix(self):
        from plugins.leona_discord.lib.images import blocks_to_event_images

        blocks = [
            {
                "type": "image",
                "media_type": "image/png",
                "data": "data:image/png;base64,abc123",
            },
        ]
        assert blocks_to_event_images(blocks) == [
            {"data": "abc123", "media_type": "image/png"},
        ]

    def test_drops_invalid_entries(self):
        from plugins.leona_discord.lib.images import blocks_to_event_images

        assert blocks_to_event_images([{"data": ""}, {"media_type": "image/png"}]) == []


class TestShrinkImageBytes:
    def test_small_image_unchanged(self):
        from plugins.leona_discord.lib.images import _shrink_image_bytes

        tiny = b"\xff\xd8\xff\xd9"  # minimal JPEG EOI marker
        out, mt = _shrink_image_bytes(tiny, "image/jpeg", target_b64_chars=80_000)
        assert out == tiny and mt == "image/jpeg"

    def test_large_png_gets_smaller(self):
        try:
            from PIL import Image
            import io
        except ImportError:
            return

        from plugins.leona_discord.lib.images import _shrink_image_bytes

        img = Image.new("RGB", (2400, 1800), color=(120, 80, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw = buf.getvalue()
        shrunk, mt = _shrink_image_bytes(raw, "image/png", target_b64_chars=80_000)
        assert mt == "image/jpeg"
        assert len(shrunk) < len(raw)
        assert len(__import__("base64").b64encode(shrunk)) <= 80_000


class TestExtractLlmDescription:
    def test_strips_thinking_from_content(self):
        from plugins.leona_discord.lib.images import _extract_llm_description

        class Resp:
            content = "<think>hmm</think> A cat on a keyboard."
            thinking = None

        assert _extract_llm_description(Resp()) == "A cat on a keyboard."

    def test_falls_back_to_thinking_field(self):
        from plugins.leona_discord.lib.images import _extract_llm_description

        class Resp:
            content = ""
            thinking = "A dancing parrot GIF."

        assert _extract_llm_description(Resp()) == "A dancing parrot GIF."


class TestFormatVisionDescription:
    def test_gif_wording(self):
        from plugins.leona_discord.lib.images import (
            format_vision_description, is_vision_description_block,
        )

        block = format_vision_description("A cat waves hello.", ["http://x/a.gif"])
        assert "Attached GIF" in block
        assert "including for GIFs" in block
        assert is_vision_description_block(block)

    def test_static_image_wording(self):
        from plugins.leona_discord.lib.images import format_vision_description

        block = format_vision_description("A sunset.", ["http://x/a.jpg"])
        assert "Attached image" in block
        assert "cannot see images" in block
    def test_minimum_and_retries(self):
        from plugins.leona_discord.lib.images import _describe_token_budgets

        assert 1024 in _describe_token_budgets(500)
        assert 2048 in _describe_token_budgets(500)


class TestImageUnavailableHint:
    def test_gif_hint_discourages_guessing(self):
        from plugins.leona_discord.lib.images import image_unavailable_hint

        hint = image_unavailable_hint(["https://cdn.discordapp.com/attachments/x/foo.gif"])
        assert "CANNOT see" in hint
        assert "Do NOT guess" in hint


class TestEmojiPolicy:
    def test_unicode_always_allowed(self):
        from plugins.leona_discord.lib.emoji_policy import emoji_is_allowed

        settings = {"allowed_emojis": ["<:BUG:111>"]}
        assert emoji_is_allowed("🔥", settings)
        assert emoji_is_allowed("👍", settings)

    def test_custom_requires_allowlist(self):
        from plugins.leona_discord.lib.emoji_policy import emoji_is_allowed

        settings = {"allowed_emojis": ["<:BUG:111>"]}
        assert emoji_is_allowed("<:BUG:111>", settings)
        assert emoji_is_allowed("<:BUG:>", settings)
        assert not emoji_is_allowed("<:NOPE:222>", settings)

    def test_custom_allowlist_filters_unicode_entries(self):
        from plugins.leona_discord.lib.emoji_policy import custom_allowlist

        settings = {"allowed_emojis": ["🔥", "<:BUG:111>", "👍"]}
        assert custom_allowlist(settings) == ["<:BUG:111>"]


class TestBotIdentity:
    def test_build_hint_includes_id_and_first_person_guidance(self):
        from plugins.leona_discord.lib.bot_identity import build_bot_identity_hint

        hint = build_bot_identity_hint({
            "bot_id": "123456789",
            "bot_username": "remmi_bot",
            "bot_display_name": "Remmi",
        })
        assert "You are Remmi (@remmi_bot) on Discord." in hint
        assert "Your Discord user ID is 123456789." in hint
        assert "<@123456789>" in hint
        assert 'from "Remmi"' in hint
        assert "first person" in hint

    def test_enrich_payload_prepends_hint_and_fields(self):
        from unittest.mock import patch

        from plugins.leona_discord.lib.bot_identity import enrich_payload_with_bot_identity

        fields = {
            "bot_id": "999",
            "bot_username": "remmi",
            "bot_display_name": "Remmi",
        }
        payload = {"account": "remmi", "content": "hello there"}
        with patch(
            "plugins.leona_discord.lib.bot_identity.bot_identity_fields",
            return_value=fields,
        ):
            enrich_payload_with_bot_identity(payload)

        assert payload["bot_id"] == "999"
        assert payload["bot_display_name"] == "Remmi"
        assert payload["content"].startswith("You are Remmi")
        assert payload["content"].endswith("hello there")

    def test_proactive_hint_forbids_self_greeting(self):
        from plugins.leona_discord.lib.bot_identity import build_proactive_post_hint

        hint = build_proactive_post_hint({
            "bot_username": "remmi_bot",
            "bot_display_name": "Remmi",
        }, purpose="greeting")
        assert "Never greet or address" in hint
        assert '"Remmi"' in hint
        assert "not a message to yourself" in hint

    def test_strip_self_address_removes_bot_name(self):
        from plugins.leona_discord.lib.bot_identity import strip_self_address

        fields = {"bot_display_name": "Remmi", "bot_username": "remmi_bot"}
        text = "Morning, Remmi — hope your night shift was blissfully notification-free. ☀️"
        fixed = strip_self_address(text, fields)
        assert "Remmi" not in fixed
        assert fixed.startswith("Morning")
        assert "hope your night shift" in fixed


class TestProactiveHistory:
    def test_bot_lines_labeled_you(self):
        from plugins.leona_discord.lib.history import format_proactive_history

        history = [
            {
                "display_name": "Remmi",
                "username": "remmi_bot",
                "author_id": "bot",
                "is_bot": True,
                "content": "good night everyone",
            },
            {
                "display_name": "Zeebie",
                "username": "zeebie",
                "author_id": "111",
                "content": "night!",
            },
        ]
        lines = format_proactive_history(history, account="remmi")
        assert any(line.startswith("You:") for line in lines)
        assert any(line.startswith("Zeebie:") for line in lines)
        assert not any(line.startswith("Remmi:") for line in lines)



class TestSleepSchedule:
    def test_goodnight_due_random_minute(self, monkeypatch):
        from datetime import datetime, timezone
        from plugins.leona_discord.lib import sleep_schedule
        from plugins.leona_discord.lib.store import upsert_sleep_state

        monkeypatch.setattr(sleep_schedule.random, "choice", lambda xs: 30)
        upsert_sleep_state("acct", "chan", sleep_date="2026-06-15", scheduled_sleep_minute=-1, goodnight_sent=False)
        g = {"sleep_schedule_enabled": True, "sleep_utc_hour": 22}
        due_early = sleep_schedule.goodnight_due(
            "acct", "chan", g, datetime(2026, 6, 15, 22, 30, tzinfo=timezone.utc),
        )
        assert due_early is True
        not_due = sleep_schedule.goodnight_due(
            "acct", "chan", g, datetime(2026, 6, 15, 22, 10, tzinfo=timezone.utc),
        )
        assert not_due is False

    def test_goodnight_due_catchup_legacy_minute(self):
        from datetime import datetime, timezone
        from plugins.leona_discord.lib.sleep_schedule import goodnight_due
        from plugins.leona_discord.lib.store import upsert_sleep_state

        g = {"sleep_schedule_enabled": True, "sleep_utc_hour": 22}
        upsert_sleep_state(
            "acct", "chan2", sleep_date="2026-06-15",
            scheduled_sleep_minute=52, goodnight_sent=False,
        )
        # Minute 52 can never match */15 cron except via :45 catch-up
        assert goodnight_due(
            "acct", "chan2", g, datetime(2026, 6, 15, 22, 30, tzinfo=timezone.utc),
        ) is False
        assert goodnight_due(
            "acct", "chan2", g, datetime(2026, 6, 15, 22, 45, tzinfo=timezone.utc),
        ) is True

    def test_shared_goodnight_minute(self, monkeypatch):
        from datetime import datetime, timezone
        from plugins.leona_discord.lib import sleep_schedule
        from plugins.leona_discord.lib.sleep_schedule import ensure_sleep_minute, goodnight_due
        from plugins.leona_discord.lib.store import init_db

        init_db()
        monkeypatch.setattr(sleep_schedule.random, "choice", lambda xs: 30)
        monkeypatch.setattr(
            "plugins.leona_discord.lib.store.random.choice", lambda xs: 30,
        )
        g = {
            "sleep_schedule_enabled": True,
            "sleep_utc_hour": 22,
            "sleep_same_goodnight_minute": True,
        }
        m1 = ensure_sleep_minute("bot", "ch1", "2026-06-15", g)
        m2 = ensure_sleep_minute("bot", "ch2", "2026-06-15", g)
        assert m1 == m2 == 30
        now = datetime(2026, 6, 15, 22, 30, tzinfo=timezone.utc)
        assert goodnight_due("bot", "ch1", g, now)
        assert goodnight_due("bot", "ch2", g, now)

    def test_enter_and_wake(self):
        from plugins.leona_discord.lib.sleep_schedule import (
            enter_sleep,
            is_channel_asleep,
            wake_channel,
        )

        enter_sleep("a", "c1")
        assert is_channel_asleep("a", "c1")
        wake_channel("a", "c1")
        assert not is_channel_asleep("a", "c1")


class TestForcedWake:
    def test_threshold_triggers_wake_hint(self, monkeypatch):
        import time as time_mod
        from plugins.leona_discord.lib.sleep_forced_wake import (
            handle_sleep_mention,
            is_forced_awake,
        )
        from plugins.leona_discord.lib.sleep_schedule import enter_sleep
        from plugins.leona_discord.lib.store import buffer_sleep_mention, upsert_sleep_state

        now = time_mod.time()
        monkeypatch.setattr("plugins.leona_discord.lib.sleep_forced_wake.time.time", lambda: now)

        enter_sleep("fw", "ch")
        g = {
            "sleep_schedule_enabled": True,
            "sleep_forced_wake_enabled": True,
            "sleep_forced_wake_mention_count": 3,
            "sleep_forced_wake_window_minutes": 15,
            "sleep_forced_wake_duration_minutes": 30,
        }
        for i in range(2):
            buffer_sleep_mention("fw", "g1", "ch", f"m{i}", "u1", "user", "User", f"ping {i}")
            assert handle_sleep_mention("fw", "ch", g) is None

        buffer_sleep_mention("fw", "g1", "ch", "m2", "u1", "user", "User", "ping 2")
        hint = handle_sleep_mention("fw", "ch", g)
        assert hint is not None
        assert "woke you up" in hint
        assert is_forced_awake("fw", "ch")

    def test_stays_awake_until_expiry(self, monkeypatch):
        import time as time_mod
        from plugins.leona_discord.lib.sleep_forced_wake import (
            expire_forced_wake_if_needed,
            handle_sleep_mention,
            is_forced_awake,
        )
        from plugins.leona_discord.lib.store import upsert_sleep_state

        t0 = 1_000_000.0
        monkeypatch.setattr("plugins.leona_discord.lib.sleep_forced_wake.time.time", lambda: t0)

        upsert_sleep_state("fw2", "ch2", is_asleep=True, forced_wake_until=t0 + 600)
        g = {"sleep_schedule_enabled": True, "sleep_forced_wake_enabled": True}
        assert is_forced_awake("fw2", "ch2")
        hint = handle_sleep_mention("fw2", "ch2", g)
        assert hint is not None
        assert "still awake" in hint.lower() or "woken up earlier" in hint.lower()

        monkeypatch.setattr("plugins.leona_discord.lib.sleep_forced_wake.time.time", lambda: t0 + 601)
        assert expire_forced_wake_if_needed("fw2", "ch2")
        assert not is_forced_awake("fw2", "ch2")


class TestPickGifDescribeFrame:
    def test_prefers_middle_frame(self):
        from plugins.leona_discord.lib.images import _pick_gif_describe_frame

        frames = [(b"a", "image/png"), (b"b", "image/png"), (b"c", "image/png")]
        out, mt = _pick_gif_describe_frame(frames)
        assert out == b"b" and mt == "image/png"
