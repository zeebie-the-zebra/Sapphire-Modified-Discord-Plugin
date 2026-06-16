"""Debug trace for 'why didn't the bot respond?' gate decisions."""

import time

from plugins.leona_discord.lib import store as sqlite_store


class MessageTrace:
    def __init__(self, account: str, guild_id: str, channel_id: str,
                 channel_name: str, message_id: str, username: str, mentioned: bool):
        self.meta = {
            "ts": time.time(),
            "account": account,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "message_id": message_id,
            "username": username,
            "mentioned": mentioned,
            "gates": [],
            "outcome": "unknown",
        }

    def gate(self, name: str, passed: bool, detail: str = ""):
        self.meta["gates"].append({
            "gate": name,
            "passed": passed,
            "detail": detail,
        })

    def finish(self, outcome: str):
        self.meta["outcome"] = outcome
        try:
            sqlite_store.save_trace(self.meta)
        except Exception:
            pass
