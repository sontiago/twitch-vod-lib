"""
Video downloader: wraps yt-dlp to download Twitch VODs.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

from twitch_vod.config import TwitchConfig
from twitch_vod.utils.logger import get_logger

log = get_logger(__name__)

# Minimum file size (bytes) to consider a cached download valid.
# Prevents false cache hits from a failed partial download.
_MIN_VALID_FILE_SIZE = 1 * 1024 * 1024  # 1 MB

# Maps human-friendly quality names to yt-dlp format strings.
QUALITY_MAP: dict[str, str] = {
    "best":    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "1080p60": "bestvideo[height=1080][fps=60]+bestaudio/bestvideo[height=1080]+bestaudio/best",
    "1080p":   "bestvideo[height=1080]+bestaudio/best[height<=1080]",
    "720p60":  "bestvideo[height=720][fps=60]+bestaudio/bestvideo[height=720]+bestaudio/best",
    "720p":    "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p":    "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "worst":   "worstvideo+worstaudio/worst",
}


class VideoDownloader:
    """
    Downloads Twitch VODs via yt-dlp.

    Skips the download if the output file already exists and is larger than
    1 MB (to guard against stale zero-byte or partial files).
    """

    def __init__(self, config: TwitchConfig) -> None:
        self._config = config

    def download(self, vod_id: str, quality: Optional[str] = None) -> Path:
        """
        Download a VOD and return the path to the local MP4 file.

        Args:
            vod_id:  Twitch VOD ID.
            quality: One of the keys in QUALITY_MAP, or a raw yt-dlp format
                     string.  Falls back to ``config.download_quality``.

        Returns:
            Absolute path to the downloaded file.

        Raises:
            RuntimeError: yt-dlp exited with a non-zero return code.
            FileNotFoundError: yt-dlp is not installed / not on PATH.
        """
        output_path = self._config.output_dir / f"{vod_id}.mp4"

        if self._is_cached(output_path):
            log.info("VOD already downloaded, skipping", vod_id=vod_id, path=str(output_path))
            return output_path

        selected_quality = quality or self._config.download_quality
        format_str = QUALITY_MAP.get(selected_quality, selected_quality)
        vod_url = f"https://www.twitch.tv/videos/{vod_id}"

        cmd = self._build_command(output_path, format_str, vod_url)

        log.info("Downloading VOD", vod_id=vod_id, quality=selected_quality)
        start = time.monotonic()

        result = subprocess.run(cmd, capture_output=False, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"yt-dlp failed (exit code {result.returncode}) for VOD {vod_id}. "
                "Check yt-dlp output above for details."
            )

        elapsed = time.monotonic() - start
        size_mb = output_path.stat().st_size / 1024 / 1024
        log.info(
            "VOD downloaded",
            vod_id=vod_id,
            size_mb=round(size_mb, 1),
            elapsed_s=round(elapsed),
            path=str(output_path),
        )
        return output_path

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _build_command(self, output_path: Path, format_str: str, vod_url: str) -> list[str]:
        cmd = [
            "yt-dlp",
            "--format", format_str,
            "--output", str(output_path),
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--no-warnings",
            "--progress",
        ]
        if self._config.cookies_file and Path(self._config.cookies_file).exists():
            cmd += ["--cookies", self._config.cookies_file]
            log.debug("Using cookies file", path=self._config.cookies_file)
        cmd.append(vod_url)
        return cmd

    @staticmethod
    def _is_cached(path: Path) -> bool:
        return path.exists() and path.stat().st_size > _MIN_VALID_FILE_SIZE