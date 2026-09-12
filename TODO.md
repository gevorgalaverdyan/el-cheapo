# TODO — Firestore persistence

Everything above the storage layer is built and tested. What's missing is one
class: a Firestore implementation of `ExpenseRepository`. Write that, wire it in,
and the bot is end-to-end.

Run `uv run pytest` first. 115 tests should pass before you change anything.

---

## 1. What already exists

| | |
|---|---|
| `elcheapo/agent/` | ADK `LlmAgent`, session per chat, tools: `propose_expense`, `list_categories`, `query_expenses` |
| `elcheapo/handler.py` | Telegram updates → confirmation cards → commit |
| `elcheapo/commit.py` | The **only** write path. Idempotent via `draft_id` |
| `elcheapo/store/repository.py` | The protocol you are implementing |
| `elcheapo/store/memory.py` | `InMemoryRepository` — the reference behaviour |
| `elcheapo/repositories.py` | `for_chat(chat_id)` — where your class gets plugged in |

**Do not modify** `handler.py`, `commit.py`, `channels/`, or `agent/`. If you
think you need to, the interface is wrong — say so rather than reaching past it.

---

## 2. The contract

From `elcheapo/store/repository.py`:

```python
categories()                  -> list[Category]
add_category(name)            -> None
append_expense(expense)       -> None
recent_draft_ids(limit=200)   -> set[str]
query(ExpenseQuery)           -> list[Expense]   # newest first
```

Models are in `elcheapo/models.py`. Read `Expense`, `Category`, and
`ExpenseQuery` before starting — `ExpenseQuery.matches()` defines the exact
filter semantics you must reproduce.

---

## 3. Data model

```
categories/{slug}                    platform categories, shared by everyone
users/{uid}/categories/{slug}        user-added categories
users/{uid}/expenses/{expense_id}    one confirmed expense
```

`uid` is `str(chat_id)` for now. It becomes a real account id when OAuth lands;
nothing outside `for_chat` should ever see it.

### Expense document

| field | type | notes |
|---|---|---|
| `date` | string | `YYYY-MM-DD`. ISO strings sort correctly, and this is a calendar date, not an instant. |
| `amount_cents` | integer | **Not a float.** See §4. |
| `category` | string | |
| `merchant` | string | may be empty |
| `merchant_lower` | string | `merchant.casefold()`, for querying |
| `note` | string | may be empty |
| `source` | string | `text` \| `image` \| `voice` |
| `logged_at` | timestamp | UTC |
| `draft_id` | string | idempotency key |

Use `draft_id` as the **document id**. Then `append_expense` is naturally
idempotent and a double-tapped Accept cannot create two rows even if the
`recent_draft_ids` check races.

### Category document

`name` (string), `emoji` (string), `monthly_budget` (number or null),
`scope` (`platform` | `user`).

`categories()` returns platform categories first, then user categories, each
group sorted by name. Deterministic ordering matters — `list_categories` feeds
the model's prompt, and an unstable list makes its behaviour unstable.

---

## 4. Three things that will bite you

**Money must not become a float.** `Expense.amount` is a `Decimal`. Firestore
has no decimal type and its number type is a double, so `45.20` round-trips as
`45.19999999999999`. Store `amount_cents` as an integer
(`int(amount * 100)`) and rebuild with `Decimal(cents) / 100`. Amount-range
filters then work server-side as integer comparisons.

**Firestore cannot do substring search.** `ExpenseQuery.merchant="tim"` must
match `"Tim Hortons #2841"`, and `text` is matched against merchant *and* note.
There is no server-side operator for this. Do this instead:

1. Push what Firestore supports into the query: `category` (equality),
   `date_from`/`date_to` (range on `date`), `min_amount`/`max_amount` (range on
   `amount_cents`), ordering by `date` descending.
2. Fetch those results.
3. Apply `query.matches(expense)` in Python to handle `merchant` and `text`.
4. Apply `query.limit` **after** step 3, or you will return fewer rows than asked.

Reusing `matches()` rather than reimplementing it is what keeps the two
repositories in agreement.

**Firestore allows one range field per query.** A range on `date` *and* a range
on `amount_cents` in the same query is rejected. Keep the range on `date`, and
let `matches()` handle the amount bounds client-side.

You will also hit a missing composite index the first time you combine
`category` with an ordered `date`. The error carries a URL that creates it —
follow it, then commit the generated `firestore.indexes.json`.

---

## 5. Tasks

- [ ] Add `firebase-admin` to `pyproject.toml`; drop `google-api-python-client`
      and `google-auth` if nothing else uses them.
- [ ] Add `FIREBASE_PROJECT_ID` to `Settings` (`elcheapo/config.py`) and to
      `.env.example`. Every field in `Settings` must appear in `.env.example` —
      there is a test that checks this.
- [ ] Write `elcheapo/store/firestore.py` with `FirestoreRepository`.
- [ ] Write `elcheapo/store/seed.py` to create the platform categories:
      Groceries, Dining, Transport, Utilities, Rent, Health, Shopping,
      Entertainment, Travel, Subscriptions, Other. Idempotent — safe to re-run.
- [ ] Replace `SingleUserRepositories(InMemoryRepository())` in
      `elcheapo/dev_poll.py` with the Firestore-backed one.
- [ ] Keep `InMemoryRepository`. Tests depend on it, and it is what lets the
      suite run with no credentials.

---

## 6. Testing

**Write a shared contract test.** Create
`tests/test_repository_contract.py` parametrized over both implementations, so
they are held to identical behaviour:

```python
@pytest.fixture(params=["memory", "firestore"])
def repository(request): ...
```

Move the cases in `tests/test_queries.py` into it. Mark the Firestore parameter
so it is skipped when no emulator is running — the default `uv run pytest` must
stay green offline, with no credentials.

Use the **emulator**, not a real project:

```bash
firebase emulators:start --only firestore
export FIRESTORE_EMULATOR_HOST=localhost:8080
uv run pytest -m firestore
```

Add a `firestore` marker to `pyproject.toml` alongside the existing `live` one,
and deselect it by default the same way.

Cases worth having beyond the query filters:

- [ ] `45.20` survives a write/read round trip as exactly `Decimal("45.20")`
- [ ] Appending the same `draft_id` twice leaves one document
- [ ] `categories()` returns platform before user, each sorted by name
- [ ] `query(limit=2)` returns 2 when 5 rows match a merchant substring
      (this is the client-side-filter trap in §4)
- [ ] Two different `uid`s never see each other's expenses

---

## 7. Done when

- `uv run pytest` passes with no credentials and no emulator
- `uv run pytest -m firestore` passes against the emulator
- `uv run python -m elcheapo.dev_poll`, then sending the bot a receipt photo and
  tapping Accept, puts a document in `users/{uid}/expenses`
- Asking it "how much did I spend on dining?" answers from Firestore

---

## Out of scope

The Python executor sandbox is **cancelled** — do not build it.

OAuth and multi-user accounts are a later phase. `for_chat` is the seam they
will use; leave it alone.

`docs/superpowers/specs/2026-09-12-elcheapo-design.md` still describes a Google
Sheets workbook with pie charts. It is **stale** — §6 and §12 do not apply.
Treat this file as the source of truth for storage and don't update the spec;
it is being rewritten separately.
