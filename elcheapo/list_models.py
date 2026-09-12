"""List the Gemini models your API key can actually use.

    uv run python -m elcheapo.list_models

Model availability differs by key and changes over time, so guessing a name
from documentation is a good way to get a confusing 404.
"""

from google import genai

from elcheapo.config import Settings


def run() -> None:
    settings = Settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    usable = sorted(
        model.name.removeprefix("models/")
        for model in client.models.list()
        if "generateContent" in (getattr(model, "supported_actions", None) or [])
    )

    configured = settings.gemini_model
    mark = "ok" if configured in usable else "NOT AVAILABLE to this key"
    print(f"configured: {configured}  [{mark}]\n")

    for name in usable:
        print(f"  {'*' if name == configured else ' '} {name}")


if __name__ == "__main__":
    run()
