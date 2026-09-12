from elcheapo.channels.telegram.media import attachment_in


def test_a_photo_is_recognised():
    message = {
        "photo": [
            {"file_id": "small", "width": 90, "file_size": 1000},
            {"file_id": "large", "width": 1280, "file_size": 90000},
        ]
    }

    assert attachment_in(message) == ("large", "image/jpeg")


def test_the_largest_photo_size_is_chosen():
    # Telegram sends several renditions; the last is the highest resolution,
    # and a receipt is unreadable at thumbnail size.
    message = {
        "photo": [
            {"file_id": "a", "width": 90},
            {"file_id": "b", "width": 320},
            {"file_id": "c", "width": 1280},
        ]
    }

    assert attachment_in(message)[0] == "c"


def test_a_voice_note_is_recognised():
    message = {"voice": {"file_id": "v1", "mime_type": "audio/ogg", "duration": 3}}

    assert attachment_in(message) == ("v1", "audio/ogg")


def test_a_voice_note_without_a_declared_type_defaults_to_ogg():
    message = {"voice": {"file_id": "v1", "duration": 3}}

    assert attachment_in(message) == ("v1", "audio/ogg")


def test_an_audio_file_is_recognised():
    message = {"audio": {"file_id": "a1", "mime_type": "audio/mpeg"}}

    assert attachment_in(message) == ("a1", "audio/mpeg")


def test_an_image_sent_as_a_document_is_recognised():
    message = {
        "document": {
            "file_id": "d1",
            "mime_type": "image/png",
            "file_name": "receipt.png",
        }
    }

    assert attachment_in(message) == ("d1", "image/png")


def test_a_pdf_document_is_recognised():
    message = {"document": {"file_id": "d2", "mime_type": "application/pdf"}}

    assert attachment_in(message) == ("d2", "application/pdf")


def test_an_unreadable_document_type_is_ignored():
    message = {"document": {"file_id": "d3", "mime_type": "application/zip"}}

    assert attachment_in(message) is None


def test_a_plain_text_message_has_no_attachment():
    assert attachment_in({"text": "lunch 40"}) is None


def test_a_sticker_is_ignored():
    assert attachment_in({"sticker": {"file_id": "s1"}}) is None
