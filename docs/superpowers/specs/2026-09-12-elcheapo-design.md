# ElCheapo — Conversational Expense Tracker

**Status:** Design approved, pending implementation plan
**Date:** 2026-09-12

## 1. Overview

A personal expense tracker driven entirely through a Telegram chat. The user
sends a photo of a receipt, a voice note, or a line of text. An LLM agent
interprets it and proposes a structured expense, rendered in the chat as a
confirmation card. Nothing reaches the spreadsheet until the user taps
**Accept**. Corrections are conversational: replying to a card with "make it 45,
that was dinner" revises the card in place.

Data lives in a Google Sheets workbook that this project generates — formatted,
validated, and carrying a dashboard of charts.

### 1.1 Core property

**The agent cannot write to the spreadsheet.** Its only proposal tool returns a
draft object. The single code path that calls the Sheets write API is the
Accept callback handler, which is reachable only by a human tapping a button.
A misread receipt is a card the user declines, not a row they must later find
and fix.

## 2. Goals

- Log an expense from an image, voice note, or text message in one exchange.
- Review every expense before it is written.
- Refine a proposed expense conversationally, without re-sending the input.
- Keep a clean, closed-ish category list that the agent may extend but not
  silently pollute.
- Provide a spreadsheet that is useful to open directly — charts, budgets,
  formatting — not a bare data grid.
- Cost approximately nothing at idle.

## 3. Non-goals

- Multi-user or multi-tenant operation. Single household, an explicit allowlist.
- Multi-currency. One currency, no conversion.
- Income, transfers, account balances, or reconciliation. Expenses only.
- A web or mobile frontend. Telegram is the entire interface.
- Splitting one receipt into multiple line-item expenses.

## 4. Decisions and rationale

| Decision | Choice | Rationale |
|---|---|---|
| Chat surface | Telegram | Free Bot API, native photo/voice/commands, webhook setup is one call, no business verification. |
| Storage | Google Sheets only | Familiar UI, manual correction, charts for free. Personal volume (hundreds to low thousands of rows/year) stays well inside API limits. |
| Agent framework | Google ADK | Native multimodal `Part` handling, `adk web` dev UI for testing without Telegram, eval harness, single Google service account for both Gemini and Sheets. |
| Hosting | Cloud Run, scale to zero | Costs nothing idle; ADC gives keyless auth to Google APIs. Cold start of a few seconds is imperceptible in chat. |
| Draft state | Encoded in the card message | No database. Survives cold starts, container replacement, and redeploys indefinitely. |
| Processing | Synchronous | On scale-to-zero Cloud Run the container may freeze the instant a response is sent, which would kill background work. Telegram's retry-on-non-200 becomes a safety net. |
| Currency | Single, no conversion | Explicit user requirement. |
| Categories | Seeded list in a sheet tab, agent may append | Keeps summaries comparable while allowing growth; new categories are surfaced for approval. |

## 5. Architecture

### 5.1 Components

| Component | Responsibility |
|---|---|
| `webhook` (FastAPI) | Authenticates and routes every Telegram update. |
| `command router` | Handles `/`-prefixed messages deterministically, no model call. |
| `agent` (ADK `LlmAgent`) | Interprets free-form input; calls proposal and read tools. |
| `card` module | Renders drafts as Telegram messages; encodes/decodes the hidden payload. |
| `SheetsRepository` | All spreadsheet reads and writes, behind an interface. |
| `bootstrap` | One-off script that creates the formatted workbook. |

### 5.2 Request flow

```
 Telegram --HTTPS push--> Cloud Run: POST /telegram/webhook
                          |
                          +- secret token header mismatch --> 403
                          +- chat_id not in allowlist      --> 200, ignored
                          +- update_id already seen        --> 200, ignored
                          |
                          +- callback_query --> accept / discard handler
                          |                     (decode payload from message)
                          |
                          +- text starts with "/" --> command router
                          |                           (direct repository call)
                          |
                          +- anything else --> ADK Runner --> Gemini
                                                   |
                                                   +- propose_expense --> card
                                                   +- search_expenses --> text
                                                   +- summarize       --> text
```

### 5.3 Deployment

Single container on Cloud Run, `min-instances=0`. The webhook is registered once
via Telegram's `setWebhook` with a `secret_token`. The runtime service account is
granted the Sheets and Vertex AI scopes, and the workbook is shared with that
service account's email address. No Google credential files exist anywhere in the
project.

## 6. Data model

### 6.1 `Expenses` tab

| Column | Type | Notes |
|---|---|---|
| `date` | date | Date of *spending*, not of logging. |
| `amount` | number | Currency-formatted. |
| `category` | string | Data validation against `Categories!$A$2:$A$1000`. |
| `merchant` | string | May be empty. |
| `note` | string | May be empty. |
| `source` | enum | `text` / `image` / `voice`. |
| `logged_at` | timestamp | UTC ISO 8601. |
| `draft_id` | string | Hidden column. Idempotency key; see §10.2. |

`source` exists so the user can filter to `image` rows and assess how accurately
receipt photos are actually being read — otherwise that is a vague feeling rather
than a measurable fact.

### 6.2 `Categories` tab

| Column | Type | Notes |
|---|---|---|
| `name` | string | Referenced by the Expenses validation range. |
| `emoji` | string | Used in card rendering. |
| `monthly_budget` | number | User-maintained; blank means untracked. |
| `total_spent` | formula | `SUMIF` over the current month. |
| `created_by` | enum | `seed` / `agent`. |
| `created_at` | timestamp | |

Seed categories: Groceries, Dining, Transport, Utilities, Rent, Health, Shopping,
Entertainment, Travel, Subscriptions, Other.

The validation range is deliberately open-ended (`$A$2:$A$1000`) so that an agent
appending a category requires no change to the validation rule. Validation is set
non-strict (warn, not reject) so a write can never hard-fail; correctness is
enforced by commit ordering instead (§8.3).

### 6.3 `Dashboard` tab

- **KPI cells:** this month's total, last month's total, average per day.
- **Pie chart:** spend by category, current month.
- **Column chart:** monthly totals across the year.
- **Top merchants table:** ten highest-spend merchants this month.
- **Budget progress:** per-category spend against `monthly_budget`.

Charts require concrete ranges rather than live aggregates, so each is fed by a
hidden helper range of `QUERY`/`SUMIFS` formulas placed to the right of the
visible area. A single defined colour palette is applied across both charts.

### 6.4 Draft payload

A draft is a JSON object with short keys, base64url-encoded, carried in the card
message as the URL of a zero-width link. The visible card reads:

```
🧾 45.20
🛒 Groceries
Seoudi · 12 Sep 2026
[ ✓ Accept ]  [ ✗ Discard ]
```

with a zero-width-space link appended to the final line whose URL is
`https://t.me/#d1.<base64url payload>`.

Payload fields: schema version prefix `d1`, then `i` (draft_id), `a` (amount),
`c` (category), `n` (is_new_category), `m` (merchant), `t` (note), `d` (date),
`s` (source).

**The payload is never parsed from the visible text.** On callback the handler
reads `callback_query.message.entities`, finds the `text_link` entity, and decodes
its URL. This decoupling is the point: the card's visible layout can be restyled
freely without breaking previously-sent cards. The `d1` version prefix means a
future schema change is detected and refused with a clear message rather than
silently mis-parsed.

No signature is applied. Telegram populates `callback_query.message` server-side
from the bot's own sent message, and users cannot edit a bot's messages, so the
payload is not user-forgeable.

Button `callback_data` carries only an action and the `draft_id`
(`acc:<draft_id>` / `dsc:<draft_id>`), staying well inside Telegram's 64-byte
limit. The full draft always comes from the message entity, never from
`callback_data`.

## 7. Draft lifecycle

### 7.1 States

A draft is `PENDING` from the moment its card is sent until a callback resolves
it to `COMMITTED` or `DISCARDED`. State is held entirely in the card message;
there is no server-side draft store. Multiple drafts may be pending at once.

### 7.2 Transitions

| Event | Result |
|---|---|
| Media or free text, no pending target | Agent proposes; new card sent. |
| Tap **Accept** | `commit_expense` runs; card edited to a confirmed state, buttons removed. |
| Tap **Discard** | Card edited to a struck-through state, buttons removed. |
| Free text targeting a pending draft | Agent revises; the *same* card is edited in place via `editMessageText`. |

Editing in place rather than posting a new card keeps a fiddly expense as one
tidy message instead of a column of superseded ones.

Every `callback_query` is acknowledged with `answerCallbackQuery` so the client
spinner clears, including on the error paths.

### 7.3 Targeting rules

- A button tap carries its own card, so it is unambiguous.
- Free text that uses Telegram's native reply targets the replied-to card.
- Free text without a reply targets the most recent pending card, resolved from
  an in-process cache of `chat_id -> last card message_id`.

The cache is best-effort and is lost on cold start. When it is empty, the bot
replies asking the user to reply to the card they mean. **Correctness never
depends on this cache — only convenience does.** Accept, Discard, and
reply-targeted refinement work identically whether the container is warm or cold.

New media sent while other drafts are pending is always treated as a new expense
and produces a new card. Only free text refines an existing draft.

### 7.4 New-category flag

When the agent proposes a category not present in `Categories`, the card marks it
explicitly (`✨ Groceries — new category`).

Category lists degrade invisibly; a single typo persists forever. Surfacing the
creation at the moment the user is already reviewing the card is the cheapest
possible check.

## 8. Agent design

### 8.1 Configuration

- `LlmAgent` on a pinned Gemini Flash model.
- Instruction includes the current date in the configured timezone, the
  configured currency, and the current category list.
- `InMemorySessionService`. Sessions are short-lived and non-authoritative:
  every durable fact lives in the card payload or the spreadsheet.

### 8.2 Tools exposed to the model

| Tool | Effect |
|---|---|
| `propose_expense(amount, category, merchant, date, note, is_new_category)` | Validates against the Pydantic model, returns a draft. **Writes nothing.** |
| `search_expenses(text?, category?, date_from?, date_to?)` | Read-only. |
| `summarize(period, category?)` | Read-only aggregate. |

Refinement re-invokes `propose_expense` with the current draft supplied as
context; there is no separate revise tool.

### 8.3 Paths the model cannot reach

`commit_expense(draft)` is called only by the Accept handler. It runs in a fixed
order: create the category if `is_new_category`, then append the expense row. This
ordering guarantees the validation range already contains the value being written.

### 8.4 Multimodal input

Telegram updates carry a `file_id`, not bytes. The handler calls `getFile`,
downloads from the file endpoint, and wraps the result as
`types.Part.from_bytes(data=..., mime_type=...)` alongside any caption text:

- Photos: largest size from `message.photo[-1]`, `image/jpeg`.
- Voice notes: `message.voice`, `audio/ogg`.

Gemini reads images and hears audio directly. **There is no OCR service and no
transcription service in this system.**

## 9. Commands

Parsed in the webhook before the agent, dispatched straight to the repository —
instant, free, and deterministic.

| Command | Behaviour |
|---|---|
| `/summary [month]` | Totals and per-category breakdown; defaults to the current month. |
| `/search <text>` | Matches merchant and note. |
| `/categories` | Lists categories with month-to-date spend and budget. |
| `/start`, `/help` | Usage. |

## 10. Reliability

### 10.1 Caching

The category list and a trailing window of expenses are cached in-process with a
~60s TTL, invalidated on commit, so a burst of receipts does not produce a burst
of Sheets reads.

### 10.2 Idempotency

Double-tapping Accept, or a Telegram webhook retry after a timeout, could append
the same expense twice. Every draft carries a `draft_id`, written to the hidden
`draft_id` column. `commit_expense` scans recent rows for that id and no-ops if
present.

This is why drafts carry an id despite the payload being self-contained: it makes
Accept safely retryable, which matters because Telegram's retry behaviour is
outside this system's control.

Webhook `update_id`s are additionally deduplicated in-process as a cheap first
line of defence, but the `draft_id` guard is the one that is actually load-bearing.

### 10.3 Failure modes

| Failure | Behaviour |
|---|---|
| Sheets 429 / 5xx | Retry with exponential backoff. On give-up the card stays pending and the user can tap Accept again. |
| Gemini cannot interpret the input | No card. The bot asks a clarifying question. |
| Unparseable or unknown-version payload | Card edited to an explanatory error; user re-sends the expense. |
| Cold start mid-conversation | Accept/Discard unaffected. Unreplied free text prompts the user to reply to a card. |

## 11. Security

- **Webhook authentication:** the `X-Telegram-Bot-Api-Secret-Token` header must
  match the configured secret; 403 otherwise.
- **Allowlist:** an explicit set of permitted `chat_id`s, checked before any other
  work. Anyone who discovers the bot's username can message it, and every message
  otherwise costs tokens and writes to a private spreadsheet. This check is the
  entire access-control model and is not optional.
- **Google auth:** ADC via the Cloud Run runtime service account. No key files.
- **Secrets:** the Telegram bot token and webhook secret, held in Secret Manager.

## 12. Workbook bootstrap

`bootstrap.py` creates the workbook through the Sheets API in a single batch
update: sheet creation, frozen bold headers, alternating row banding, number and
date formats, the category data-validation rule, seed category rows, helper
formula ranges, and both charts.

Scripted rather than hand-made so it is reproducible, diffable in git, and
regenerable in one command for a new year or a second household. It is run once
per workbook and is not part of the request path.

## 13. Repository layout

```
elcheapo/
  config.py           # env-derived settings
  main.py             # FastAPI app, webhook route, auth
  models.py           # Pydantic: Expense, Draft, Category
  telegram/
    client.py         # Bot API calls (send, edit, getFile, answerCallback)
    cards.py          # render drafts; encode/decode hidden payload
    router.py         # command dispatch
    handlers.py       # message and callback_query handling
  agent/
    agent.py          # LlmAgent construction
    tools.py          # propose_expense, search_expenses, summarize
    prompt.py         # instruction template
  sheets/
    repository.py     # SheetsRepository interface + Google implementation
    bootstrap.py      # workbook creation script
tests/
```

## 14. Configuration

| Variable | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot API auth. |
| `TELEGRAM_WEBHOOK_SECRET` | Webhook header check. |
| `ALLOWED_CHAT_IDS` | Comma-separated allowlist. |
| `SPREADSHEET_ID` | Target workbook. |
| `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | Vertex AI. |
| `GOOGLE_GENAI_USE_VERTEXAI` | `TRUE`, for keyless Gemini access. |
| `CURRENCY` | Display and number format. |
| `TIMEZONE` | Resolves "today" and "yesterday" correctly. |

## 15. Testing strategy

Test-driven, with seams placed so that most logic is testable without network access.

- **Pure functions:** payload encode/decode round-trip, schema validation,
  date resolution against a fixed timezone, category matching, card rendering.
- **Repository:** `SheetsRepository` is an interface; a fake backs all handler
  and command tests.
- **Handlers:** webhook auth, allowlist rejection, update deduplication, draft
  targeting rules, and commit idempotency, all against the fake repository.
- **Live model tests:** opt-in only, against a small set of recorded receipt and
  voice fixtures, since they cost tokens on every run.
- **Manual:** `adk web` exercises the agent loop without Telegram in the way.

## 16. Future work

Deliberately excluded from this design, recorded so the boundary is explicit:

- Recurring or subscription expense detection.
- Splitting one receipt into multiple line items.
- Multi-currency with FX conversion.
- Proactive budget alerts pushed without a user message.
- An `/undo` command for committed rows — the confirmation step makes this rare,
  and the spreadsheet is directly editable.
