import json

from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

# ---------------------------------------------------------------------------
# ChatDownloader unit tests (mocked GQL)
# ---------------------------------------------------------------------------

class TestChatDownloader:
    def _make_gql_response(self, edges, has_next=False):
        return [{
            "data": {
                "video": {
                    "comments": {
                        "edges": edges,
                        "pageInfo": {"hasNextPage": has_next},
                    }
                }
            }
        }]

    def _make_edge(self, msg_id, ts, text, author="User"):
        return {
            "node": {
                "id": msg_id,
                "contentOffsetSeconds": ts,
                "commenter": {"displayName": author},
                "message": {
                    "fragments": [{"text": text, "emote": None}],
                    "userBadges": [],
                    "userColor": None,
                },
            }
        }

    def test_downloads_messages(self, tmp_path):
        from twitch_vod.config import TwitchConfig
        from twitch_vod.downloader.chat import ChatDownloader

        cfg = TwitchConfig.from_dict({
            "client_id": "x",
            "client_secret": "y",
            "output_dir": str(tmp_path),
        })

        gql_response = self._make_gql_response(
            [self._make_edge("1", 0, "Hello"), self._make_edge("2", 5, "World")],
            has_next=False,
        )

        with patch("twitch_vod.downloader.chat.TwitchGQLClient") as MockGQL:
            instance = MockGQL.return_value.__enter__.return_value
            instance.fetch_chat_by_offset.return_value = gql_response
            downloader = ChatDownloader(cfg)
            messages = downloader.download("vod123", vod_duration=60)

        assert len(messages) == 2
        assert messages[0].content == "Hello"
        assert messages[1].content == "World"

    def test_cache_is_used_on_second_call(self, tmp_path):
        from twitch_vod.config import TwitchConfig
        from twitch_vod.downloader.chat import ChatDownloader

        cfg = TwitchConfig.from_dict({
            "client_id": "x",
            "client_secret": "y",
            "output_dir": str(tmp_path),
        })

        # Pre-populate cache
        from twitch_vod.models.chat import ChatMessage
        cached = [ChatMessage(timestamp=1.0, author="A", content="cached")]
        cache_file = tmp_path / "vod_cached_chat.json"
        cache_file.write_text(
            json.dumps([c.to_dict() for c in cached]), encoding="utf-8"
        )

        with patch("twitch_vod.downloader.chat.TwitchGQLClient") as MockGQL:
            downloader = ChatDownloader(cfg)
            messages = downloader.download("vod_cached")
            MockGQL.assert_not_called()

        assert len(messages) == 1
        assert messages[0].content == "cached"

    def test_deduplication(self, tmp_path):
        from twitch_vod.config import TwitchConfig
        from twitch_vod.downloader.chat import ChatDownloader

        cfg = TwitchConfig.from_dict({
            "client_id": "x",
            "client_secret": "y",
            "output_dir": str(tmp_path),
        })

        # Both pages contain message "1"
        page1 = self._make_gql_response(
            [self._make_edge("1", 0, "Duplicate")], has_next=True
        )
        page2 = self._make_gql_response(
            [self._make_edge("1", 0, "Duplicate"), self._make_edge("2", 1, "New")],
            has_next=False,
        )

        with patch("twitch_vod.downloader.chat.TwitchGQLClient") as MockGQL:
            instance = MockGQL.return_value.__enter__.return_value
            instance.fetch_chat_by_offset.side_effect = [page1, page2]
            downloader = ChatDownloader(cfg)
            messages = downloader.download("vod_dup", vod_duration=10)

        assert len(messages) == 2
        contents = {m.content for m in messages}
        assert "Duplicate" in contents
        assert "New" in contents