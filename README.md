# ElCheapo

A Telegram bot that tracks personal spending through conversation. Send it a
photo of a receipt, a voice note, or a sentence like "45 on dinner last night",
and it proposes an expense as a card. Nothing is stored until you tap Accept.

It also searches Canadian store flyers for deals, and keeps a todo list.

Live at [@elcheapo_bot](https://web.telegram.org/k/#@elcheapo_bot).

## What it can do

| | |
|---|---|
| **Log spending** | Text, receipt photo, PDF or voice note. Gemini reads it; you confirm the card. |
| **Answer questions** | "How much on dining this month?" — answered from your recorded expenses, never estimated. |
| **Export** | An xlsx with totals and a chart, or a CSV, grouped by category, month or merchant. |
| **Find deals** | This week's flyers near your postal code, via the Flipp API. Canada only. |
| **Keep a todo list** | Add, list, complete and reword tasks. |
| `/reset` | Start a fresh conversation. Happens on its own after 15 idle minutes. |

## Running it locally

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), and Docker.

```bash
cp .env.example .env          # then fill in the required values
docker compose up -d          # Postgres on 127.0.0.1:5433
uv run python -m elcheapo.seed    # create the schema, seed the categories
uv run python -m elcheapo.dev_poll
```

`dev_poll` uses long polling, so it needs no public URL and no tunnel. It feeds
the same handler the deployed webhook does, so what you exercise locally is the
real code path.

Required in `.env`: `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, and
`ALLOWED_CHAT_IDS` (find yours with `uv run python -m elcheapo.whoami`).
`FLIPP_API` is optional — without it the bot simply has no deal tools.

Re-run `elcheapo.seed` after pulling schema changes. Every statement is
`IF NOT EXISTS` or `ON CONFLICT DO NOTHING`, so it is safe to run any time.

## How it fits together

| | |
|---|---|
| `elcheapo/main.py` | FastAPI webhook. Authenticates and filters updates, then dispatches. |
| `elcheapo/dev_poll.py` | Long-polling loop for local runs. Assembles the same handler. |
| `elcheapo/handler.py` | Updates → confirmation cards → committed expenses. |
| `elcheapo/commit.py` | The **only** path that writes an expense. Idempotent via `draft_id`. |
| `elcheapo/agent/` | The ADK agent: its instruction, its tools, and one session per chat. |
| `elcheapo/store/` | `repository.py` is the protocol; `postgres.py` and `memory.py` implement it. |
| `elcheapo/channels/telegram/` | Bot API client, cards, and Markdown → HTML for replies. |
| `elcheapo/flipp.py` | Wrapper over the Flipp weekly-ad API. |
| `elcheapo/reports.py` | xlsx and CSV generation. |

Two rules hold the design together. The agent can **propose** an expense but
never write one — only an Accept callback reaches `commit_expense`. And every
tool is built bound to one chat's repository, so a tool call cannot reach
another chat's data even if the model asks for it.

`InMemoryRepository` is not a leftover: it implements the same protocol as
Postgres so the tests and the receipt harness can run without a container.

## Tests

```bash
uv run pytest                  # the whole suite, no network, no database
uv run pytest -m live          # calls real APIs -- costs tokens and credits
```

Live tests are deselected by default. `tests/test_receipts_live.py` runs the
model against the receipt fixtures; `tests/test_flipp_live.py` checks the Flipp
wrapper against the real API, which mocked tests cannot do — a field renamed
upstream would leave them green while the bot answered with blanks.
