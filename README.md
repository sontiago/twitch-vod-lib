# twitch-vod-lib
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE.md)
[![Tests](https://img.shields.io/badge/tests-pytest-blue?logo=pytest&logoColor=white)](https://pytest.org)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000?logo=ruff)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue)](https://mypy-lang.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](https://github.com/sontiago/twitch-vod-lib/pulls)

A clean Python library for downloading Twitch VOD metadata, video files, and chat logs.

## Features

- Fetch VOD metadata via **Twitch Helix API**
- Download video via **yt-dlp** (supports quality selection, cookies for sub-only VODs)
- Download full chat replay via **Twitch GQL** with pagination, deduplication and caching
- Structured logging (stdlib or `structlog`)
- Retry logic with exponential back-off on transient errors
- File-based caching — re-running skips already completed work
- Config from environment variables, dict, or YAML (bring your own loader)

## Requirements

- Python 3.10+
- `yt-dlp` on `PATH` (only needed for video downloads)
- Twitch Developer Application credentials → https://dev.twitch.tv/console/apps

## Installation

### Poetry (recommended)
```bash
git clone https://github.com/sontiago/twitch-vod-lib.git
cd twitch-vod-lib
poetry install                   # installs main deps
poetry install --with dev        # installs dev deps (pytest, ruff, mypy)
```

Copy the env file and fill in your credentials:

```bash
cp .env.example .env
# edit .env — set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET
```

Run the library:

```bash
poetry run python your_script.py
```

### pip (alternative)

```bash
pip install -e ".[dev]"
```

## Quick start

```python
from twitch_vod import TwitchVodClient, TwitchConfig

# Reads TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET from environment
with TwitchVodClient() as client:
    vod = client.get_latest_vod("xqcow")
    print(f"VOD: {vod.title}  ({vod.duration / 3600:.1f}h)")

    video_path = client.download_video(vod.id, quality="720p")
    messages   = client.download_chat(vod.id, vod_duration=vod.duration)

    print(f"Downloaded {len(messages)} chat messages → {video_path}")
```

Or use the one-shot helper:

```python
vod, video_path, messages = client.fetch_all("xqcow", quality="480p")
```

## Environment variables

Copy `.env.example` to `.env` and fill in your values (use `python-dotenv` or export manually):

| Variable | Required | Default | Description |
|---|---|---|---|
| `TWITCH_CLIENT_ID` | ✅ | — | Twitch app client ID |
| `TWITCH_CLIENT_SECRET` | ✅ | — | Twitch app client secret |
| `TWITCH_USER_ACCESS_TOKEN` | ❌ | `""` | User token for sub-only VODs |
| `TWITCH_COOKIES_FILE` | ❌ | `None` | Path to Netscape cookies file |
| `TWITCH_DOWNLOAD_QUALITY` | ❌ | `best` | `best`, `1080p60`, `1080p`, `720p60`, `720p`, `480p`, `worst` |
| `TWITCH_OUTPUT_DIR` | ❌ | `output/raw` | Directory for video and chat files |
| `TWITCH_API_TIMEOUT` | ❌ | `30` | HTTP timeout in seconds |
| `TWITCH_API_RETRIES` | ❌ | `3` | Number of retry attempts |
| `TWITCH_CHAT_MAX_PAGES` | ❌ | `10000` | Hard cap on GQL pagination pages |
| `TWITCH_CHAT_RATE_LIMIT_MIN` | ❌ | `0.05` | Min sleep between GQL pages (s) |
| `TWITCH_CHAT_RATE_LIMIT_MAX` | ❌ | `0.5` | Max sleep between GQL pages (s) |
| `LOG_LEVEL` | ❌ | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Configuration from dict / YAML

```python
import yaml
from twitch_vod import TwitchVodClient, TwitchConfig

with open("config.yaml") as f:
    raw = yaml.safe_load(f)

cfg = TwitchConfig.from_dict(raw["twitch"])
client = TwitchVodClient(cfg)
```

Example `config.yaml`:

```yaml
twitch:
  client_id: abc123
  client_secret: secret
  download_quality: 720p
  output_dir: data/raw
```

## Project layout

```
twitch_vod/
├── __init__.py          # Public API: TwitchVodClient, TwitchConfig, VODInfo, ChatMessage
├── client.py            # TwitchVodClient — façade / entry point
├── config.py            # TwitchConfig — env-based configuration
├── api/
│   ├── helix_client.py  # Twitch Helix REST API (auth, VOD metadata)
│   └── gql_client.py    # Twitch GQL (chat pagination)
├── downloader/
│   ├── video.py         # yt-dlp wrapper
│   └── chat.py          # GQL chat downloader with caching
├── models/
│   ├── vod.py           # VODInfo dataclass
│   └── chat.py          # ChatMessage dataclass
└── utils/
    └── logger.py        # Structured logging (structlog / stdlib)
```

## Running tests

```bash
pytest # or poetry run pytest
```

With coverage:

```bash
pytest --cov=twitch_vod --cov-report=term-missing
```

## Linting & type-checking

```bash
ruff check .
mypy ./
```

## Caching behaviour

| File | When created | Skip condition |
|---|---|---|
| `output/raw/{vod_id}.mp4` | `download_video()` | File exists and > 1 MB |
| `output/raw/{vod_id}_chat.json` | `download_chat()` | File exists |

Delete the relevant file to force a re-download.

## License

MIT

## Known issues

### Chat pagination may miss messages in high-traffic streams

The Twitch GQL API paginates chat by `contentOffsetSeconds`, meaning each page
is fetched starting from the timestamp of the last seen message.

This approach has a fundamental limitation:

- The API returns messages matching `ts >= offset`
- Multiple messages can share the same `ts` (same second)
- If more messages exist within a single second than the page size allows,
  the overflow messages will never appear in any subsequent page request

Deduplication by message `id` prevents duplicates but **cannot recover
messages that were never returned by the API in the first place**.

In practice this means very popular streams (e.g. large hype moments with
thousands of messages per second) may have small gaps in the chat log.
This is a limitation of the Twitch GQL API itself, not of this library.