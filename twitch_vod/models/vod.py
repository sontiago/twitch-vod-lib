from __future__ import annotations

import re
from dataclasses import dataclass, asdict


@dataclass
class VODInfo:
    """Metadata for a Twitch VOD."""

    id: str
    title: str
    user_name: str
    user_id: str
    created_at: str
    duration: float          # total seconds
    view_count: int
    url: str
    thumbnail_url: str
    language: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_api_response(cls, raw: dict) -> "VODInfo":
        """Build a VODInfo from a raw Twitch Helix API video object."""
        vod_id = raw["id"]
        return cls(
            id=vod_id,
            title=raw.get("title", "Untitled Stream"),
            user_name=raw.get("user_name", ""),
            user_id=raw.get("user_id", ""),
            created_at=raw.get("created_at", ""),
            duration=_parse_twitch_duration(raw.get("duration", "0s")),
            view_count=int(raw.get("view_count", 0)),
            url=raw.get("url", f"https://www.twitch.tv/videos/{vod_id}"),
            thumbnail_url=raw.get("thumbnail_url", "").replace(
                "%{width}x%{height}", "1280x720"
            ),
            language=raw.get("language", "en"),
        )


def _parse_twitch_duration(duration: str) -> float:
    """Parse Twitch duration string into total seconds.

    Examples:
        "6h14m27s" -> 22467.0
        "45m"      -> 2700.0
        "30s"      -> 30.0
    """
    total = 0.0
    for value, unit in re.findall(r"(\d+)([hms])", duration):
        v = int(value)
        if unit == "h":
            total += v * 3600
        elif unit == "m":
            total += v * 60
        elif unit == "s":
            total += v
    return total