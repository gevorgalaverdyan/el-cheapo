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


def settings_from_env_file(tmp_path, contents: str) -> Settings:
    """Load through a real .env file -- the path the bug actually lived on."""
    env_file = tmp_path / ".env"
    env_file.write_text(contents, encoding="utf-8")
    return Settings(_env_file=str(env_file))


def test_one_chat_id_loads_from_a_dotenv_file(tmp_path):
    settings = settings_from_env_file(
        tmp_path, "TELEGRAM_BOT_TOKEN=token\nALLOWED_CHAT_IDS=111\n"
    )

    assert settings.allowed_chat_ids == {111}


def test_two_chat_ids_load_from_a_dotenv_file(tmp_path):
    settings = settings_from_env_file(
        tmp_path, "TELEGRAM_BOT_TOKEN=token\nALLOWED_CHAT_IDS=111,222\n"
    )

    assert settings.allowed_chat_ids == {111, 222}


def test_a_group_chat_id_loads_from_a_dotenv_file(tmp_path):
    settings = settings_from_env_file(
        tmp_path, "TELEGRAM_BOT_TOKEN=token\nALLOWED_CHAT_IDS=111,-1001234567890\n"
    )

    assert settings.allowed_chat_ids == {111, -1001234567890}
