"""
Configuration for TwitchVodLib.

Priority (high → low):
    1. Explicit keyword arguments to TwitchConfig()
    2. Environment variables (TWITCH_*)
    3. Hard-coded defaults

Example .env file:
    TWITCH_CLIENT_ID=abc123
    TWITCH_CLIENT_SECRET=secret
    TWITCH_DOWNLOAD_QUALITY=720p
    TWITCH_OUTPUT_DIR=output/raw
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TwitchConfig:
    # Required credentials
    client_id: str = field(default_factory=lambda: os.environ["TWITCH_CLIENT_ID"])
    client_secret: str = field(default_factory=lambda: os.environ["TWITCH_CLIENT_SECRET"])

    # Optional auth
    user_access_token: str = field(
        default_factory=lambda: os.environ.get("TWITCH_USER_ACCESS_TOKEN", "")
    )
    cookies_file: Optional[str] = field(
        default_factory=lambda: os.environ.get("TWITCH_COOKIES_FILE")
    )

    # Download settings
    download_quality: str = field(
        default_factory=lambda: os.environ.get("TWITCH_DOWNLOAD_QUALITY", "best")
    )
    output_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("TWITCH_OUTPUT_DIR", "output/raw"))
    )

    # HTTP settings
    api_timeout: float = field(
        default_factory=lambda: float(os.environ.get("TWITCH_API_TIMEOUT", "30"))
    )
    api_retries: int = field(
        default_factory=lambda: int(os.environ.get("TWITCH_API_RETRIES", "3"))
    )

    # Chat download settings
    chat_max_pages: int = field(
        default_factory=lambda: int(os.environ.get("TWITCH_CHAT_MAX_PAGES", "10000"))
    )
    chat_rate_limit_min: float = field(
        default_factory=lambda: float(os.environ.get("TWITCH_CHAT_RATE_LIMIT_MIN", "0.05"))
    )
    chat_rate_limit_max: float = field(
        default_factory=lambda: float(os.environ.get("TWITCH_CHAT_RATE_LIMIT_MAX", "0.5"))
    )

    def __post_init__(self) -> None:
        if not self.client_id:
            raise ValueError("TWITCH_CLIENT_ID is required")
        if not self.client_secret:
            raise ValueError("TWITCH_CLIENT_SECRET is required")
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_dict(cls, data: dict) -> "TwitchConfig":
        """Build config from a plain dict (e.g. loaded from YAML/TOML)."""
        twitch = data.get("twitch", data)
        return cls(
            client_id=twitch["client_id"],
            client_secret=twitch["client_secret"],
            user_access_token=twitch.get("user_access_token", ""),
            cookies_file=twitch.get("cookies_file"),
            download_quality=twitch.get("download_quality", "best"),
            output_dir=Path(twitch.get("output_dir", "output/raw")),
            api_timeout=float(twitch.get("api_timeout", 30)),
            api_retries=int(twitch.get("api_retries", 3)),
            chat_max_pages=int(twitch.get("chat_max_pages", 10000)),
            chat_rate_limit_min=float(twitch.get("chat_rate_limit_min", 0.05)),
            chat_rate_limit_max=float(twitch.get("chat_rate_limit_max", 0.5)),
        )