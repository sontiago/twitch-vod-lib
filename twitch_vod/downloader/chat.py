"""
Chat downloader: fetches and persists VOD chat via Twitch GQL.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

from twitch_vod.api.gql_client import TwitchGQLClient
from twitch_vod.config import TwitchConfig
from twitch_vod.models.chat import ChatMessage
from twitch_vod.utils.logger import get_logger

log = get_logger(__name__)


class ChatDownloader:
    """
    Downloads and caches Twitch VOD chat messages.

    Pagination strategy
    -------------------
    Twitch GQL paginates chat by ``contentOffsetSeconds``.  Each page is
    fetched starting from the last timestamp seen on the previous page.
    Because multiple messages can share the same timestamp, deduplication
    is done by unique message ID rather than timestamp.

    If a page yields no new messages (all already seen), the offset is
    advanced by +1 s to avoid an infinite loop.

    The loop terminates when:
    * ``hasNextPage`` is False (natural end of chat)
    * offset exceeds ``vod_duration + 60`` s (safety: past end of stream)
    * page count exceeds ``config.chat_max_pages`` (hard safety cap)
    * A GQL request fails and cannot be retried
    """

    def __init__(self, config: TwitchConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def download(self, vod_id: str, vod_duration: float = 0) -> list[ChatMessage]:
        """
        Return all chat messages for *vod_id*, loading from cache if available.

        Args:
            vod_id: Twitch VOD ID.
            vod_duration: VOD length in seconds (used as a safety stop guard).
                          Pass 0 to disable the duration-based stop.

        Returns:
            List of ChatMessage sorted by timestamp.
        """
        cache_path = self._config.output_dir / f"{vod_id}_chat.json"

        if cache_path.exists():
            log.info("Loading chat from cache", vod_id=vod_id, path=str(cache_path))
            return self._load(cache_path)

        log.info("Downloading chat", vod_id=vod_id)
        start = time.monotonic()

        messages = self._fetch_all(vod_id, vod_duration)
        self._save(messages, cache_path)

        elapsed = time.monotonic() - start
        log.info(
            "Chat download complete",
            vod_id=vod_id,
            messages=len(messages),
            elapsed_s=round(elapsed),
        )
        return messages

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _fetch_all(self, vod_id: str, vod_duration: float) -> list[ChatMessage]:
        cfg = self._config
        messages: list[ChatMessage] = []
        seen_ids: set[str] = set()
        offset: int = 0
        page: int = 0

        with TwitchGQLClient(
            timeout=cfg.api_timeout,
            max_retries=cfg.api_retries,
        ) as client:
            while True:
                # --- fetch page ---
                try:
                    data = client.fetch_chat_by_offset(vod_id, offset)
                except Exception as exc:
                    log.warning(
                        "GQL request failed — stopping chat fetch",
                        page=page,
                        offset=offset,
                        error=str(exc),
                    )
                    break

                # --- parse GQL envelope ---
                try:
                    comments_data = data[0]["data"]["video"]["comments"]
                except (KeyError, IndexError, TypeError) as exc:
                    log.warning(
                        "Unexpected GQL response structure",
                        page=page,
                        error=str(exc),
                        preview=str(data)[:300],
                    )
                    break

                edges = comments_data.get("edges", [])
                if not edges:
                    log.info("No more edges — chat download done", page=page, total=len(messages))
                    break

                # --- process edges ---
                new_count, last_ts = self._process_edges(edges, messages, seen_ids, offset)

                if page % 10 == 0:
                    log.info(
                        "Chat progress",
                        page=page,
                        offset=int(offset),
                        total=len(messages),
                        new_this_page=new_count,
                    )

                # --- check for last page ---
                if not comments_data.get("pageInfo", {}).get("hasNextPage", False):
                    log.info("Last GQL page reached", page=page, total=len(messages))
                    break

                # --- advance offset ---
                # If no new messages came in (all deduplicated), nudge offset by +1 s
                # to avoid stalling on a cluster of messages at the same timestamp.
                offset = last_ts + 1 if new_count == 0 else last_ts
                page += 1

                # --- safety stops ---
                if page > cfg.chat_max_pages:
                    log.warning("Safety stop: max pages reached", page=page)
                    break
                if vod_duration and offset > vod_duration + 60:
                    log.warning(
                        "Safety stop: offset beyond VOD duration",
                        offset=int(offset),
                        vod_duration=int(vod_duration),
                    )
                    break

                time.sleep(random.uniform(cfg.chat_rate_limit_min, cfg.chat_rate_limit_max))

        log.info("GQL pagination finished", pages=page + 1, total=len(messages))
        return sorted(messages, key=lambda m: m.timestamp)

    @staticmethod
    def _process_edges(
        edges: list[dict],
        messages: list[ChatMessage],
        seen_ids: set[str],
        current_offset: int,
    ) -> tuple[int, int]:
        """
        Parse edges into ChatMessage objects and append new ones to *messages*.

        Returns:
            (new_count, last_ts_on_page)
        """
        new_count = 0
        last_ts = current_offset

        for edge in edges:
            node = edge.get("node", {})
            msg_id = node.get("id", "")

            if msg_id:
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

            msg = ChatMessage.from_gql_node(node)
            if msg is None:
                continue

            messages.append(msg)
            new_count += 1
            last_ts = max(last_ts, int(msg.timestamp))

        return new_count, last_ts

    # ------------------------------------------------------------------ #
    # Cache I/O
    # ------------------------------------------------------------------ #

    @staticmethod
    def _save(messages: list[ChatMessage], path: Path) -> None:
        with path.open("w", encoding="utf-8") as fh:
            json.dump([m.to_dict() for m in messages], fh, indent=2, ensure_ascii=False)
        log.debug("Chat saved to cache", path=str(path), count=len(messages))

    @staticmethod
    def _load(path: Path) -> list[ChatMessage]:
        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh)
        return [ChatMessage.from_dict(item) for item in raw]