from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from clone_manager.broadcasts import parse_scheduled_at, serialize_message


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
