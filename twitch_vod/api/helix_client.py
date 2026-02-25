"""
Twitch Helix REST API client.

Handles OAuth2 Client-Credentials token acquisition and caching,
as well as automatic retry on transient errors.
"""

from __future__ import annotations

from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from twitch_vod.models.vod import VODInfo
from twitch_vod.utils.logger import get_logger

_TWITCH_API_BASE = "https://api.twitch.tv/helix"
_TOKEN_URL = "https://id.twitch.tv/oauth2/token"

log = get_logger(__name__)


class TwitchHelixClient:
    """
    Thin wrapper around the Twitch Helix REST API.

    Manages app-token lifecycle and exposes the calls required by the
    downloader.  Not intended to be a full Helix SDK.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout
        self._max_retries = max_retries
        self._app_token: Optional[str] = None

        self._http = httpx.Client(timeout=timeout)

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #

    def _get_app_token(self) -> str:
        """Return cached app access token, fetching a new one if needed."""
        if self._app_token:
            return self._app_token

        resp = self._http.post(
            _TOKEN_URL,
            params={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        self._app_token = resp.json()["access_token"]
        log.debug("Twitch app token obtained")
        return self._app_token  # type: ignore[return-value]

    def _auth_headers(self) -> dict:
        return {
            "Client-ID": self._client_id,
            "Authorization": f"Bearer {self._get_app_token()}",
        }

    # ------------------------------------------------------------------ #
    # HTTP helpers
    # ------------------------------------------------------------------ #

    def _is_retryable(self, exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in {429, 500, 502, 503, 504}
        return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError))

    def _get(self, endpoint: str, params: dict) -> dict:
        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception(self._is_retryable),
            reraise=True,
        )
        def _call() -> dict:
            url = f"{_TWITCH_API_BASE}/{endpoint}"
            resp = self._http.get(url, headers=self._auth_headers(), params=params)
            if resp.status_code == 401:
                # Token may have expired — clear cache and retry once
                self._app_token = None
                resp = self._http.get(url, headers=self._auth_headers(), params=params)
            resp.raise_for_status()
            return resp.json()

        return _call()

    # ------------------------------------------------------------------ #
    # Domain methods
    # ------------------------------------------------------------------ #

    def get_user_id(self, login: str) -> tuple[str, str]:
        """Return (user_id, display_name) for a login name.

        Raises:
            ValueError: channel not found.
        """
        data = self._get("users", {"login": login})
        users = data.get("data", [])
        if not users:
            raise ValueError(f"Twitch channel not found: '{login}'")
        user = users[0]
        return user["id"], user["login"]

    def get_latest_vod(self, channel: str) -> VODInfo:
        """
        Return metadata for the most recent archived stream of *channel*.

        Raises:
            ValueError: channel not found or has no recorded VODs.
        """
        user_id, display_name = self.get_user_id(channel)
        log.debug("User resolved", user_id=user_id, display_name=display_name)

        data = self._get(
            "videos",
            {"user_id": user_id, "type": "archive", "first": 1, "sort": "time"},
        )
        vods = data.get("data", [])
        if not vods:
            raise ValueError(
                f"No recorded VODs found for channel '{channel}'. "
                "Streams may not be saved or have been deleted."
            )
        return VODInfo.from_api_response(vods[0])

    def get_vod_metadata(self, vod_id: str) -> VODInfo:
        """
        Return metadata for a specific VOD by ID.

        Raises:
            ValueError: VOD not found.
        """
        data = self._get("videos", {"id": vod_id})
        vods = data.get("data", [])
        if not vods:
            raise ValueError(f"VOD not found: {vod_id}")
        return VODInfo.from_api_response(vods[0])

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "TwitchHelixClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()