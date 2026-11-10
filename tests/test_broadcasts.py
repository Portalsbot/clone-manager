from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from clone_manager.broadcasts import parse_scheduled_at, serialize_message
from clone_manager.handlers.clones import _parse_environment, _parse_repository


class FakeMedia:
    file_id = "telegram-file-id"


class FakeMessage:
    text = None
    caption = "hello caption"
    photo = [FakeMedia()]


def test_schedule_time_is_converted_from_india_to_utc():
    value = parse_scheduled_at(
        "2027-01-01 10:30",
        now=datetime(2026, 12, 31, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert value.isoformat() == "2027-01-01T05:00:00+00:00"


def test_schedule_rejects_past_time():
    with pytest.raises(ValueError):
        parse_scheduled_at(
            "2026-01-01 10:30",
            now=datetime(2026, 1, 2, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        )


def test_media_payload_stores_file_id_and_caption():
    payload = serialize_message(FakeMessage())
    assert payload == {
        "kind": "media",
        "media_type": "photo",
        "file_id": "telegram-file-id",
        "caption": "hello caption",
    }


def test_environment_parser_rejects_core_secrets():
    with pytest.raises(ValueError):
        _parse_environment("BOT_TOKEN=should-not-overwrite")


def test_environment_parser_accepts_multiple_custom_values():
    assert _parse_environment("API_KEY=secret\nMAX_FILES=25") == {
        "API_KEY": "secret",
        "MAX_FILES": "25",
    }


def test_github_repository_maps_to_ghcr_image_reference():
    url, image = _parse_repository("https://github.com/Portalsbot/File-Share-Bot")
    assert url == "https://github.com/Portalsbot/File-Share-Bot"
    assert image == "ghcr.io/portalsbot/file-share-bot:latest"


def test_docker_image_reference_is_accepted():
    assert _parse_repository("ghcr.io/example/bot:v2") == (None, "ghcr.io/example/bot:v2")
