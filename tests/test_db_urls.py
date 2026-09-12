import pytest

from elcheapo.store.postgres import async_url

SYNC = "postgresql+pg8000://elcheapo:elcheapo@127.0.0.1:5433/elcheapo"


def test_a_sync_driver_is_swapped_for_an_async_one():
    """ADK's session store needs an async engine; pg8000 cannot provide one."""
    assert async_url(SYNC) == (
        "postgresql+asyncpg://elcheapo:elcheapo@127.0.0.1:5433/elcheapo"
    )


def test_credentials_and_database_survive_the_swap():
    converted = async_url(SYNC)

    assert "elcheapo:elcheapo@127.0.0.1:5433" in converted
    assert converted.endswith("/elcheapo")


def test_a_bare_postgresql_url_gains_an_async_driver():
    assert async_url("postgresql://u:p@host/db").startswith("postgresql+asyncpg://")


def test_an_already_async_url_is_left_alone():
    url = "postgresql+asyncpg://u:p@host/db"

    assert async_url(url) == url


def test_a_non_postgres_url_is_refused_rather_than_mangled():
    with pytest.raises(ValueError):
        async_url("sqlite:///local.db")
