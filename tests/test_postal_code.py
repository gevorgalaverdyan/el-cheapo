"""Canadian postal codes: what counts as one, and how it is remembered."""

from elcheapo.postal import normalise
from elcheapo.store.memory import InMemoryRepository


def test_a_postal_code_is_normalised_to_the_printed_form():
    assert normalise("m5v2t6") == "M5V 2T6"


def test_a_postal_code_that_is_already_printed_properly_survives():
    assert normalise("M5V 2T6") == "M5V 2T6"


def test_a_hyphen_is_accepted_as_a_separator():
    assert normalise("M5V-2T6") == "M5V 2T6"


def test_surrounding_whitespace_is_ignored():
    assert normalise("  m5v 2t6  ") == "M5V 2T6"


def test_a_us_zip_is_not_a_canadian_postal_code():
    """The bot is Canada-only, and Flipp would answer a ZIP with US flyers."""
    assert normalise("95054") is None


def test_something_that_is_not_a_postal_code_at_all_is_refused():
    assert normalise("downtown toronto") is None


def test_a_postal_code_missing_a_character_is_refused():
    assert normalise("M5V 2T") is None


def test_nothing_is_refused():
    assert normalise("") is None


# --- remembering it ----------------------------------------------------


def test_a_new_user_has_no_postal_code():
    assert InMemoryRepository().postal_code() is None


def test_a_postal_code_is_remembered():
    repository = InMemoryRepository()

    repository.set_postal_code("M5V 2T6")

    assert repository.postal_code() == "M5V 2T6"


def test_a_postal_code_replaces_the_one_before_it():
    """People move, and the stored code is the one the deals are drawn from."""
    repository = InMemoryRepository()

    repository.set_postal_code("M5V 2T6")
    repository.set_postal_code("K1A 0B1")

    assert repository.postal_code() == "K1A 0B1"
