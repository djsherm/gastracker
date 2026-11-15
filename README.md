# Gas Spending Tracker

A self-hosted, single-user web app that tracks how much you spend on gas, estimates the litres you bought, and runs in Docker on a ZimaBlade with CasaOS.

> **Status:** planning. Nothing is built yet. See [Development steps](#development-steps) for the build order and the checklist at the bottom for progress.

## Goals

- Detect gas purchases on a TD credit card (primary) and TD debit account (secondary).
- Store the **date** and **amount** of each gas purchase in SQLite.
- Estimate litres from the amount and the local price per litre (bonus: scrape or import local gas prices).
- Web UI only. No email notifications or mobile app.
- Runs in Docker on CasaOS. Reachable on the LAN; only a tiny ingest endpoint is exposed to the internet.

## How data gets in

TD Canada does not offer a per-purchase email alert. EasyWeb only offers two alerts (low account balance and low available credit), and neither carries a merchant or purchase amount. So the app uses three input sources that all feed the same parser, classifier, and database:

| Source | Latency | Notes |
|---|---|---|
| **TD CSV import** | Manual (weekly or monthly) | Source of truth. Always works. Provides the posted amount. |
| **iPhone notification automation** | Near real time | Shortcuts automation fires on the TD / MySpend purchase notification and POSTs it to the app. Creates a **provisional** row. |
| **Manual entry** | Immediate | For cash purchases or anything missed. |

### Real-time path

```
Purchase at the pump
  -> TD MySpend push notification on iPhone
  -> iOS Shortcuts automation ("When I get a notification")
  -> HTTPS POST to the Tailscale Funnel URL (works on cellular, away from home)
  -> ingest service on the ZimaBlade stores a provisional transaction
  -> next CSV import confirms it with the posted amount
```

Why this shape:

- The phone does not need a VPN. Shortcuts cannot toggle VPN settings, so a private-only setup would silently fail whenever the VPN was off.
- The CSV is the backstop. If the server is off or the phone has no signal, the CSV import still records the purchase.
- Pay-at-pump pre-authorizations can differ from the final charge, so the CSV row wins when the two are reconciled.

### Fallbacks if the notification trigger is not workable

- **Wallet "Transaction" trigger** (Shortcuts): fires on Apple Pay tap-to-pay and passes merchant and amount directly. Only works if the card is in Apple Wallet and you pay with it. It feeds the same `/ingest` endpoint.
- **CSV-only**: the tracker is fully usable without any real-time capture.

## Architecture

- **Language/stack:** Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite.
- **UI:** server-rendered (Jinja + HTMX). No JavaScript build step.
- **Two services in one compose file:**
  - `web`: dashboard, upload page, transaction list, review queue. Bound to the LAN only. **Not exposed to the internet.**
  - `ingest`: a tiny listener that accepts only `POST /ingest` with a secret token header. This is the only thing exposed through Tailscale Funnel.
- **Storage:** SQLite file on a mounted `/data` volume, with a nightly `.backup` to another folder.
- **Timezone:** America/Toronto.

### Security model for the public ingest endpoint

Tailscale Funnel makes a port reachable by anyone who has the URL, so the ingest service is locked down:

- Single route (`POST /ingest`), nothing else answers.
- Long random secret in a request header; reject everything without it.
- Strict JSON validation, request size limit, and rate limiting.
- Responses contain no data.
- Everything received is **provisional** and is not trusted until it matches a row in a CSV import. Unmatched provisional rows are flagged for review.
- The web UI is never behind Funnel.

## Data model (draft)

All money is stored as integer cents.

- `transactions`: id, account, source (`csv` / `ingest` / `manual`), status (`provisional` / `confirmed`), date, amount_cents, merchant_raw, merchant_normalized, category (`gas` / `not_gas` / `needs_review`), card_type (`credit` / `debit`), estimated_litres, price_per_litre_used, litres_override, import_key
- `merchant_rules`: pattern, category, priority (editable in the UI, not hardcoded)
- `gas_prices`: date, region/station, grade, price_per_litre_cents, source
- `parse_failures`: source, raw_text, error, created_at

## TD CSV formats

Neither export has a header row, and neither contains an account number, so the upload form asks which account the file belongs to.

| | Credit card CSV | Debit account CSV |
|---|---|---|
| Date | `MM/DD/YYYY` | `YYYY-MM-DD` |
| Row order | Newest first | Oldest first |
| Quoting | Unquoted | Every field quoted |
| Amounts | Two decimals | Variable (`30`, `12976.5`) |
| Columns | date, description, charge, payment, balance | date, description, charge, payment, balance |
| Balance | Card balance after the row (charges increase it) | Account balance after the row (charges decrease it) |

Notes:

- The running balance is a built-in integrity check and makes `(account, date, description, amount, balance)` a reliable dedupe key, even for identical same-day charges and overlapping export ranges.
- Dates are probably posting dates and can trail the purchase date by a day or two.
- Exports can include future-dated (pending or scheduled) rows. Accept them and mark them pending.
- Transfers to the credit card, investment contributions, and payments are not spending and are ignored.
- Gas merchants appear as e.g. `SHELL C#####` (credit). Debit purchase rows carry a suffix like `_V`. Match on "contains `SHELL`", not exact strings.

## Privacy

Exports contain balances, payroll, and unrelated merchants. The importer:

- parses the uploaded file **in memory** and never saves the original,
- keeps only `gas` and `needs_review` rows,
- discards everything else.

Never commit real exports to this repo. Test fixtures must be synthetic rows in the same formats. Add `*.csv` and `.env` to `.gitignore`.

## Gas classification

- Editable merchant rules table seeded with `SHELL` and the major Ontario brands (Petro-Canada, Esso, Pioneer, Ultramar, Sunoco, Circle K, Canadian Tire Gas+, Costco Gas, and so on).
- Case-insensitive substring/regex matching, since merchant strings are messy.
- A small-amount check so a Shell coffee is not counted as a fill-up.
- Ambiguous merchants (Costco, Canadian Tire, convenience stores) go to a `needs_review` queue; tag once and keep the rule.

## Litres and gas prices

Litres = amount / price per litre. Because TD only gives dollars, litres are an **estimate**:

- Store the price used and its source, and flag the value as estimated.
- Allow a manual override from a pump receipt.
- Allow a per-merchant adjustment (for example, Costco is usually below the regional average).
- Price source is a plugin with a common interface. Start with government average prices (stable, regional and weekly), and consider station-level sources later. Station-level scraping is fragile and often against terms of service, so keep it optional.

## Development steps

Each step produces something testable. The CSV-only tracker is usable after Step 6.

### Step 0: checks (no code)

1. [ ] Create a free Tailscale account, install it on the ZimaBlade, and enable Funnel in the admin console.
2. [ ] Turn on MySpend transaction notifications. Build a test Shortcuts automation (notification trigger that appends Title, Body, and Date to a note) and capture what a real fill-up notification looks like.
3. [ ] Export fresh TD CSVs (credit and debit) as format references.

### Phase A: CSV-first tracker

1. [ ] **Project scaffold:** Python 3.12, FastAPI, SQLAlchemy + Alembic, pytest, linter, Dockerfile from day one, timezone set.
2. [ ] **Database schema and migrations.** *Done when:* migrations run on an empty database.
3. [ ] **TD CSV parsers:** `td_credit` and `td_debit` profiles, dedupe key, balance check, synthetic test fixtures. *Done when:* both formats parse correctly and overlapping imports create no duplicates.
4. [ ] **Gas classifier:** rules table, three outcomes, small-amount check.
5. [ ] **Import pipeline:** upload, parse in memory, classify, store only gas and needs-review rows, discard the file.
6. [ ] **Web UI v1:** CSV upload with account dropdown, transaction list with edit, needs-review queue, parse-failure list, manual add, basic dashboard (monthly spend, fill-up count, average per fill-up), "last import" indicator with a suggested start date for the next export. *Done when:* you can upload a CSV and see your gas history.

### Phase B: real-time capture

7. [ ] **Ingest service:** separate listener, `POST /ingest` only, secret token, validation, rate limiting, notification parsing, provisional rows. *Done when:* a request from outside your home network creates a provisional row.
8. [ ] **Reconciliation:** match provisional rows to CSV rows (same amount, date within a day or two, similar merchant), promote to confirmed with the posted amount, and list unmatched ones for review.
9. [ ] **iPhone shortcut:** notification-triggered automation that POSTs to the Funnel URL, set to run without asking. *Done when:* a real fill-up appears in the app within about a minute.

### Phase C: prices and deployment

10. [ ] **Gas prices and estimated litres:** price-source plugin, litres estimate, manual override, per-merchant adjustment.
11. [ ] **Deployment:** compose file with both services, persistent `/data` volume, env vars for the token, healthcheck, restart policy. Import into CasaOS, point Funnel at the ingest port only, schedule nightly SQLite backups, and test a restore.
12. [ ] **Hardening:** structured logging, "last ingest received" indicator, token rotation, parser tests for new formats, small CI pipeline (lint, tests, image build), dependency pinning.

## Open decisions

- **Step 6:** does the web UI need a login, or is LAN-only enough?
- **Step 7:** exact notification format (depends on the Step 0 screenshot).
- **Step 10:** start with government average prices (recommended) or look for a station-level source?
- **Debit gas purchases:** no example seen yet. Export a range that includes one so the debit gas format can be confirmed. Until then, ship credit-first.

## Risks

- **Notification trigger is best-effort.** A developer reported dropped runs for rapid-fire notifications with no error. The CSV reconciliation is the safety net.
- **MySpend reliability.** At least one recent review says its notifications stopped sending. Test before depending on it.
- **Bank format changes.** Parser failures go to `parse_failures` instead of being dropped, and imports can be re-run.
- **Public endpoint.** Mitigated by the token, rate limiting, provisional-only data, and keeping the UI off Funnel.
- **Server availability.** If the ZimaBlade is off, real-time events are lost until the next CSV import.

## Progress checklist

- [ ] Step 0: Tailscale + Funnel, test notification automation, fresh CSV exports
- [ ] Step 1: scaffold and Docker
- [ ] Step 2: schema and migrations
- [ ] Step 3: TD CSV parsers
- [ ] Step 4: gas classifier
- [ ] Step 5: import pipeline
- [ ] Step 6: web UI v1
- [ ] Step 7: ingest service
- [ ] Step 8: reconciliation
- [ ] Step 9: iPhone shortcut
- [ ] Step 10: gas prices and litres
- [ ] Step 11: CasaOS deployment and backups
- [ ] Step 12: hardening and CI
