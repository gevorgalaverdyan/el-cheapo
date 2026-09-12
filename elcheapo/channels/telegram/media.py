"""Deciding what, if anything, to download from a Telegram message.

Kept free of I/O so the rules are testable without a network or a bot token.
"""

# Gemini reads these directly. Anything else is not worth downloading.
READABLE_DOCUMENT_TYPES = ("image/", "audio/", "application/pdf")

DEFAULT_VOICE_TYPE = "audio/ogg"
PHOTO_TYPE = "image/jpeg"


def attachment_in(message: dict) -> tuple[str, str] | None:
    """Return (file_id, mime_type) for the part worth reading, if any."""
    photos = message.get("photo")
    if photos:
        # Telegram sends several renditions, smallest first. A receipt is
        # illegible at thumbnail size, so always take the last.
        return photos[-1]["file_id"], PHOTO_TYPE

    voice = message.get("voice")
    if voice:
        return voice["file_id"], voice.get("mime_type") or DEFAULT_VOICE_TYPE

    audio = message.get("audio")
    if audio:
        return audio["file_id"], audio.get("mime_type") or DEFAULT_VOICE_TYPE

    document = message.get("document")
    if document:
        mime_type = document.get("mime_type") or ""
        if mime_type.startswith(READABLE_DOCUMENT_TYPES):
            return document["file_id"], mime_type

    return None

