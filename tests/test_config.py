import pytest

from elcheapo.config import Settings


def settings_with(value) -> Settings:
    return Settings(
        _env_file=None, telegram_bot_token="token", allowed_chat_ids=value
    )


def test_a_single_chat_id_is_accepted():
    # pydantic-settings JSON-decodes env values first, so a lone number arrives
    # as an int rather than the string it was written as.
    assert settings_with(987654321).allowed_chat_ids == {987654321}


def test_a_single_chat_id_written_as_text_is_accepted():
    assert settings_with("987654321").allowed_chat_ids == {987654321}


def test_several_chat_ids_are_split_on_commas():
    assert settings_with("111,222").allowed_chat_ids == {111, 222}


def test_spaces_around_chat_ids_are_tolerated():
    assert settings_with(" 111 , 222 ").allowed_chat_ids == {111, 222}


def test_a_negative_group_chat_id_is_accepted():
    # Telegram group chat ids are negative.
    assert settings_with("-1001234567890").allowed_chat_ids == {-1001234567890}


def test_an_empty_value_allows_nobody():
    assert settings_with("").allowed_chat_ids == set()


def test_a_non_numeric_chat_id_is_rejected_loudly():
    with pytest.raises(ValueError):
        settings_with("me,you")
