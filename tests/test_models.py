
# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestParseTwitchDuration:
    def _parse(self, s):
        from twitch_vod.models.vod import _parse_twitch_duration
        return _parse_twitch_duration(s)

    def test_full(self):
        assert self._parse("6h14m27s") == 6 * 3600 + 14 * 60 + 27

    def test_hours_only(self):
        assert self._parse("2h") == 7200

    def test_minutes_seconds(self):
        assert self._parse("45m30s") == 45 * 60 + 30

    def test_zero(self):
        assert self._parse("0s") == 0

    def test_empty(self):
        assert self._parse("") == 0


class TestVODInfoFromApiResponse:
    def _make_raw(self, **overrides):
        base = {
            "id": "123",
            "title": "Test Stream",
            "user_name": "testuser",
            "user_id": "456",
            "created_at": "2024-01-01T00:00:00Z",
            "duration": "1h2m3s",
            "view_count": "9999",
            "url": "https://www.twitch.tv/videos/123",
            "thumbnail_url": "https://example.com/%{width}x%{height}.jpg",
            "language": "en",
        }
        base.update(overrides)
        return base

    def test_basic_parse(self):
        from twitch_vod.models.vod import VODInfo
        vod = VODInfo.from_api_response(self._make_raw())
        assert vod.id == "123"
        assert vod.duration == 3723.0
        assert vod.view_count == 9999

    def test_thumbnail_placeholder_replaced(self):
        from twitch_vod.models.vod import VODInfo
        vod = VODInfo.from_api_response(self._make_raw())
        assert "%{width}" not in vod.thumbnail_url
        assert "1280x720" in vod.thumbnail_url


class TestChatMessageFromGqlNode:
    def _make_node(self, **overrides):
        base = {
            "id": "msg1",
            "contentOffsetSeconds": 42.5,
            "commenter": {"displayName": "CoolUser"},
            "message": {
                "fragments": [{"text": "Hello KEKW", "emote": None}],
                "userBadges": [{"setID": "subscriber"}],
                "userColor": "#FF0000",
            },
        }
        base.update(overrides)
        return base

    def test_basic_parse(self):
        from twitch_vod.models.chat import ChatMessage
        msg = ChatMessage.from_gql_node(self._make_node())
        assert msg is not None
        assert msg.author == "CoolUser"
        assert msg.content == "Hello KEKW"
        assert msg.timestamp == 42.5
        assert msg.is_subscriber is True
        assert msg.color == "#FF0000"

    def test_empty_content_returns_none(self):
        from twitch_vod.models.chat import ChatMessage
        node = self._make_node()
        node["message"]["fragments"] = [{"text": "   ", "emote": None}]
        assert ChatMessage.from_gql_node(node) is None

    def test_emote_extracted(self):
        from twitch_vod.models.chat import ChatMessage
        node = self._make_node()
        node["message"]["fragments"] = [
            {"text": "KEKW", "emote": {"emoteID": "emoteid123"}},
        ]
        msg = ChatMessage.from_gql_node(node)
        assert msg is not None
        assert msg.emotes == [{"name": "KEKW", "id": "emoteid123"}]

    def test_missing_commenter_defaults_to_unknown(self):
        from twitch_vod.models.chat import ChatMessage
        node = self._make_node()
        node["commenter"] = None
        msg = ChatMessage.from_gql_node(node)
        assert msg is not None
        assert msg.author == "unknown"


class TestChatMessageRoundTrip:
    def test_to_dict_from_dict(self):
        from twitch_vod.models.chat import ChatMessage
        original = ChatMessage(
            timestamp=10.0,
            author="Alice",
            content="PogChamp",
            emotes=[{"name": "PogChamp", "id": "123"}],
            color="#00FF00",
            is_subscriber=True,
            is_moderator=False,
        )
        restored = ChatMessage.from_dict(original.to_dict())
        assert restored == original
