"""Turning what the model writes into what Telegram will accept."""

from elcheapo.channels.telegram.markdown import to_html


def test_plain_text_is_left_alone():
    assert to_html("Nothing on sale this week.") == "Nothing on sale this week."


def test_bold_becomes_a_bold_tag():
    assert to_html("**Pharmaprix**: eggs") == "<b>Pharmaprix</b>: eggs"


def test_several_bold_runs_on_one_line_are_all_converted():
    assert to_html("**IGA** and **Metro**") == "<b>IGA</b> and <b>Metro</b>"


def test_bold_does_not_run_across_a_line_break():
    """Otherwise one stray pair of asterisks bolds the rest of the message."""
    assert to_html("**IGA**: eggs\nand **Metro**") == "<b>IGA</b>: eggs\nand <b>Metro</b>"


def test_an_unmatched_asterisk_is_left_as_it_is():
    assert to_html("2 ** 3 is eight") == "2 ** 3 is eight"


def test_a_bulleted_list_survives_as_plain_text():
    """Telegram has no list markup, and a leading dash reads fine on its own."""
    assert to_html("- eggs\n- milk") == "- eggs\n- milk"


def test_a_bullet_written_with_an_asterisk_is_not_mistaken_for_emphasis():
    assert to_html("* eggs\n* milk") == "* eggs\n* milk"


def test_a_heading_becomes_bold_rather_than_leaving_a_hash():
    assert to_html("## Egg deals") == "<b>Egg deals</b>"


def test_inline_code_becomes_a_code_tag():
    assert to_html("call `search_deals`") == "call <code>search_deals</code>"


def test_a_fenced_block_becomes_a_pre_tag():
    assert to_html("```\nM5V 2T6\n```") == "<pre>M5V 2T6</pre>"


# --- the part that stops Telegram rejecting the whole message ----------


def test_an_ampersand_is_escaped():
    """"M&M Food Market" is a real merchant in the flyer data."""
    assert to_html("M&M Food Market") == "M&amp;M Food Market"


def test_an_angle_bracket_is_escaped():
    """Unescaped, Telegram reads this as a tag and rejects the message."""
    assert to_html("anything under <$5") == "anything under &lt;$5"


def test_something_that_looks_like_a_tag_is_escaped_rather_than_sent():
    assert to_html("<b>not mine</b>") == "&lt;b&gt;not mine&lt;/b&gt;"


def test_escaping_happens_before_the_markdown_is_converted():
    assert to_html("**A&W**: burgers") == "<b>A&amp;W</b>: burgers"


def test_code_content_stays_escaped():
    assert to_html("`a < b`") == "<code>a &lt; b</code>"


def test_nothing_in_becomes_nothing_out():
    assert to_html("") == ""
