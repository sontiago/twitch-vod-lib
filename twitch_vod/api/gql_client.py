"""
Low-level Twitch GQL client.

Handles retries, error propagation, and response validation.
The public API hash is intentionally hard-coded — it is a well-known
public hash used by the Twitch web client itself.
"""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

GQL_URL = "https://gql.twitch.tv/gql"

# Public Twitch web client ID — visible in any browser DevTools request to gql.twitch.tv.
# Not a secret; the same value is used by the Twitch website itself.
_PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"

# SHA-256 hash of the VideoCommentsByOffsetOrCursor GQL query body.
# Twitch uses Apollo Persisted Queries — the full query is replaced by its hash.
# If this starts returning errors, the hash may have changed; extract the new one
# from the Twitch web bundle or a browser DevTools GQL request.
_VOD_COMMENTS_HASH = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"


class TwitchGQLError(Exception):
    """Raised when the GQL endpoint returns an application-level error."""

class TwitchGQLClient:
    """
    Minimal async-free GQL client for fetching VOD chat comments.

    Usage (context manager preferred to ensure connection cleanup):

        with TwitchGQLClient() as client:
            data = client.fetch_chat_by_offset(vod_id=123456, offset=0)
    """

    def __init__(
        self,
        timeout: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        self._max_retries = max_retries
        self._client = httpx.Client(
            headers={
                "Client-ID": _PUBLIC_CLIENT_ID,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def fetch_chat_by_offset(self, vod_id: str, offset: int) -> dict:
        """
        Fetch one page of chat comments starting at *offset* seconds.

        Args:
            vod_id: Twitch VOD ID (string).
            offset: Start position in seconds from the beginning of the VOD.

        Returns:
            Parsed JSON response (list with one element).

        Raises:
            TwitchGQLError: GQL application-level error.
            httpx.HTTPStatusError: Non-retryable HTTP error (4xx except 429).
            httpx.TimeoutException / httpx.ConnectError: Network issues
                (retried automatically up to max_retries).
        """
        return self._fetch_with_retry(vod_id, offset)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _is_retryable(self, exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in {429, 500, 502, 503, 504}
        return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError))

    def _fetch_with_retry(self, vod_id: str, offset: int) -> dict:
        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception(self._is_retryable),
            reraise=True,
        )
        def _call() -> dict:
            resp = self._client.post(
                GQL_URL,
                json=[
                    {
                        "operationName": "VideoCommentsByOffsetOrCursor",
                        "variables": {
                            "videoID": str(vod_id),
                            "contentOffsetSeconds": offset,
                        },
                        "extensions": {
                            "persistedQuery": {
                                "version": 1,
                                "sha256Hash": _VOD_COMMENTS_HASH,
                            }
                        },
                    }
                ],
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data and data[0].get("errors"):
                raise TwitchGQLError(f"GQL error: {data[0]['errors']}")
            return data

        return _call()

    # ------------------------------------------------------------------ #
    # Context manager
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "TwitchGQLClient":
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()