"""
TwitchVodClient — the single entry-point of the library.

Example usage::

    from twitch_vod import TwitchVodClient, TwitchConfig

    cfg = TwitchConfig()   # reads TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET from env
    with TwitchVodClient(cfg) as client:
        vod = client.get_latest_vod("xqcow")
        video_path = client.download_video(vod.id)
        messages  = client.download_chat(vod.id, vod.duration)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from twitch_vod.api.helix_client import TwitchHelixClient
from twitch_vod.config import TwitchConfig
from twitch_vod.downloader.chat import ChatDownloader
from twitch_vod.downloader.video import VideoDownloader
from twitch_vod.models.chat import ChatMessage
from twitch_vod.models.vod import VODInfo
from twitch_vod.utils.logger import get_logger

log = get_logger(__name__)


class TwitchVodClient:
    """
    High-level facade for fetching Twitch VOD metadata, video, and chat.

    Composes three independent components:

    * :class:`~api.helix_client.TwitchHelixClient` — Helix REST API
    * :class:`~downloader.video.VideoDownloader`   — yt-dlp wrapper
    * :class:`~downloader.chat.ChatDownloader`     — GQL chat scraper
    """

    def __init__(self, config: Optional[TwitchConfig] = None) -> None:
        self._config = config or TwitchConfig()
        self._helix = TwitchHelixClient(
            client_id=self._config.client_id,
            client_secret=self._config.client_secret,
            timeout=self._config.api_timeout,
            max_retries=self._config.api_retries,
        )
        self._video = VideoDownloader(self._config)
        self._chat = ChatDownloader(self._config)

        log.debug(
            "TwitchVodClient initialised",
            quality=self._config.download_quality,
            output_dir=str(self._config.output_dir),
        )

    # ------------------------------------------------------------------ #
    # Metadata
    # ------------------------------------------------------------------ #

    def get_latest_vod(self, channel: str) -> VODInfo:
        """Return metadata for the most recent archived stream of *channel*."""
        log.info("Fetching latest VOD", channel=channel)
        vod = self._helix.get_latest_vod(channel)
        log.info(
            "Latest VOD found",
            vod_id=vod.id,
            title=vod.title[:60],
            duration_s=vod.duration,
        )
        return vod

    def get_vod_metadata(self, vod_id: str) -> VODInfo:
        """Return metadata for a specific VOD by its numeric ID."""
        log.info("Fetching VOD metadata", vod_id=vod_id)
        return self._helix.get_vod_metadata(vod_id)

    # ------------------------------------------------------------------ #
    # Downloads
    # ------------------------------------------------------------------ #

    def download_video(self, vod_id: str, quality: Optional[str] = None) -> Path:
        """
        Download the video for *vod_id* and return the local MP4 path.

        The file is cached; calling this method again with the same ID is a
        no-op if the output file already exists and is non-trivially sized.
        """
        return self._video.download(vod_id, quality=quality)

    def download_chat(
        self, vod_id: str, vod_duration: float = 0
    ) -> list[ChatMessage]:
        """
        Download chat messages for *vod_id* and return them sorted by timestamp.

        The result is persisted as ``<output_dir>/<vod_id>_chat.json``.
        Subsequent calls load from that file instead of hitting the network.

        Args:
            vod_id: Twitch VOD ID.
            vod_duration: Optional VOD duration in seconds (improves safety stop).
        """
        return self._chat.download(vod_id, vod_duration=vod_duration)

    # ------------------------------------------------------------------ #
    # Convenience
    # ------------------------------------------------------------------ #

    def fetch_all(
        self,
        channel: str,
        quality: Optional[str] = None,
    ) -> tuple[VODInfo, Path, list[ChatMessage]]:
        """
        One-shot helper: resolve latest VOD, download video + chat.

        Returns:
            (VODInfo, video_path, chat_messages)
        """
        vod = self.get_latest_vod(channel)
        video_path = self.download_video(vod.id, quality=quality)
        messages = self.download_chat(vod.id, vod_duration=vod.duration)
        return vod, video_path, messages

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        self._helix.close()

    def __enter__(self) -> "TwitchVodClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()