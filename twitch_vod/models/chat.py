from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ChatMessage:
    """A single Twitch chat message."""

    timestamp: float          # seconds from stream start
    author: str
    content: str
    emotes: list[dict] = field(default_factory=list)  # [{"name": "KEKW", "id": "abc123"}]
    color: Optional[str] = None
    is_subscriber: bool = False
    is_moderator: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_gql_node(cls, node: dict) -> Optional["ChatMessage"]:
        """Build a ChatMessage from a raw GQL comment node.

        Returns None if the message has no text content (e.g. sub alerts).
        """
        commenter = node.get("commenter") or {}
        message_data = node.get("message", {})
        fragments = message_data.get("fragments", [])

        content_parts: list[str] = []
        emotes: list[dict] = []

        for frag in fragments:
            text = frag.get("text", "")
            content_parts.append(text)
            if frag.get("emote"):
                emotes.append(
                    {
                        "name": text.strip(),
                        "id": frag["emote"].get("emoteID", ""),
                    }
                )

        content = "".join(content_parts).strip()
        if not content:
            return None

        badge_ids = [b.get("setID", "") for b in message_data.get("userBadges", [])]

        return cls(
            timestamp=float(node.get("contentOffsetSeconds", 0)),
            author=commenter.get("displayName", "unknown"),
            content=content,
            emotes=emotes,
            color=message_data.get("userColor"),
            is_subscriber="subscriber" in badge_ids,
            is_moderator="moderator" in badge_ids,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "ChatMessage":
        return cls(
            timestamp=data["timestamp"],
            author=data["author"],
            content=data["content"],
            emotes=data.get("emotes", []),
            color=data.get("color"),
            is_subscriber=data.get("is_subscriber", False),
            is_moderator=data.get("is_moderator", False),
        )