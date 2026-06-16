"""Personality presets — map friendly names to underlying behaviour settings."""

PERSONALITY_PRESETS = {
    "lurker": {
        "human_response_chance": 5,
        "bot_response_chance": 0,
        "reaction_chance": 70,
        "cooldown_seconds": 300,
        "name_match_enabled": False,
        "react_to_any": True,
    },
    "helper": {
        "human_response_chance": 0,
        "bot_response_chance": 0,
        "reaction_chance": 25,
        "cooldown_seconds": 60,
        "name_match_enabled": False,
        "reply_mode": "mentions_only",
        "react_to_trigger": True,
        "react_to_any": False,
    },
    "chatterbox": {
        "human_response_chance": 40,
        "bot_response_chance": 10,
        "reaction_chance": 45,
        "cooldown_seconds": 30,
        "name_match_enabled": True,
        "react_to_any": False,
    },
    "moderator": {
        "human_response_chance": 0,
        "bot_response_chance": 0,
        "reaction_chance": 15,
        "cooldown_seconds": 90,
        "name_match_enabled": True,
        "keyword_triggers": ["help", "mod", "report", "admin"],
        "react_to_trigger": True,
        "react_to_any": False,
    },
}

VALID_PRESETS = frozenset(PERSONALITY_PRESETS.keys()) | {"custom"}


def preset_values(name: str) -> dict:
    if name in PERSONALITY_PRESETS:
        return dict(PERSONALITY_PRESETS[name])
    return {}
