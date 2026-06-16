"""Discord embed builders."""


def build_embed(title: str = "", description: str = "", color: int = 0x7289DA,
                fields: list = None, footer: str = ""):
    import discord
    embed = discord.Embed(
        title=(title or None),
        description=(description or None),
        color=color,
    )
    for f in fields or []:
        if isinstance(f, dict) and f.get("name"):
            embed.add_field(
                name=str(f["name"])[:256],
                value=str(f.get("value", ""))[:1024],
                inline=bool(f.get("inline", False)),
            )
    if footer:
        embed.set_footer(text=str(footer)[:2048])
    return embed


def parse_color(value) -> int:
    if value is None:
        return 0x7289DA
    if isinstance(value, int):
        return max(0, min(0xFFFFFF, value))
    s = str(value).strip().lower()
    if s.startswith("#"):
        s = s[1:]
    if s.startswith("0x"):
        s = s[2:]
    try:
        return int(s, 16) & 0xFFFFFF
    except ValueError:
        return 0x7289DA
