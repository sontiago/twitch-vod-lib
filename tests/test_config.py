import pytest

# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestTwitchConfig:
    def test_from_dict(self):
        from twitch_vod.config import TwitchConfig
        cfg = TwitchConfig.from_dict({
            "client_id": "abc",
            "client_secret": "secret",
            "output_dir": "/tmp/twitch_test",
        })
        assert cfg.client_id == "abc"
        assert cfg.download_quality == "best"

    def test_missing_client_id_raises(self, monkeypatch):
        monkeypatch.delenv("TWITCH_CLIENT_ID", raising=False)
        monkeypatch.delenv("TWITCH_CLIENT_SECRET", raising=False)
        from twitch_vod.config import TwitchConfig
        with pytest.raises((ValueError, KeyError)):
            TwitchConfig()