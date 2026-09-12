# ElCheapo

[![Watch the Demo]([https://youtube.com](https://www.youtube.com/watch?v=E36ATyPZ8f4))]([https://youtu.be](https://www.youtube.com/watch?v=E36ATyPZ8f4))

A Telegram bot that tracks personal spending through conversation. Send it a
photo of a receipt, a voice note, or a sentence like "45 on dinner last night",
and it proposes an expense as a card. Nothing is stored until you tap Accept.

It keeps monthly budgets, searches Canadian store flyers for deals, and holds
a todo list.

Live at [@elcheapo_bot](https://web.telegram.org/k/#@elcheapo_bot).

## About

Most expense trackers fail for the same reason: logging is friction. You have to
open an app, pick a category, type an amount — so you do it for a week, then
stop, and the record is worth nothing because it has holes in it.

ElCheapo removes the app. You log an expense in the chat window you already have
open, in whatever form the evidence arrives: a photo of a receipt, a voice note
on the walk home, or three words typed one-handed. Gemini reads it, and the bot
replies with a card showing exactly what it understood. One tap files it.

**The agent can never write to your data.** It proposes; only an Accept callback
commits. Every expense stored was confirmed by a person looking at it, so a model
misreading a receipt costs you a tap, not a corrupted ledger. Every tool is built
bound to one chat's data, so a tool call cannot reach another user's records even
if the model asks it to.

Once the record is trustworthy it can do more than remember. Set a budget and the
bot tells you where it stands at the moment you spend — unprompted, on the
confirmation card, because that is the only moment the number changes anything.
Ask what is on sale and it reads this week's real store flyers near your postal
code, so it helps you spend less rather than only recording that you did.

## Built with

Python 3.12, Google ADK with Gemini for the agent and its tools, FastAPI for the
webhook, Postgres for storage, the Telegram Bot API for the interface, and the
Flipp weekly-ad API for flyer data. 318 tests, no network or database required to
run them.

## What it can do

| | |
|---|---|
| **Log spending** | Text, receipt photo, PDF or voice note. Gemini reads it; you confirm the card. |
| **Answer questions** | "How much on dining this month?" — answered from your recorded expenses, never estimated. |
| **Export** | An xlsx with totals and a chart, or a CSV, grouped by category, month or merchant. |
| **Keep a budget** | Per category, per month. The confirmation card tells you where the budget stands the moment you spend. |
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
| `elcheapo/budgets.py` | Monthly budget standing, derived from recorded expenses. |

Two rules hold the design together. The agent can **propose** an expense but
never write one — only an Accept callback reaches `commit_expense`. And every
tool is built bound to one chat's repository, so a tool call cannot reach
another chat's data even if the model asks for it.

Budgets live in their own per-user table rather than on the category, because
the platform categories are one shared row each — a budget stored there would
be everybody's budget at once.

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
