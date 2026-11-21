# Gas Spending Tracker

A self-hosted, single-user app that records gas purchases from TD MySpend push notifications, estimates litres using locally configured fuel prices, and runs on a ZimaBlade with CasaOS. The repository is public; use synthetic data only.

> **Current status:** The two-database schema and first Alembic migration are set up. Ingest processing, worker logic, and the web UI are not implemented yet.

## Data flow

```text
TD MySpend notification on iPhone
  -> iOS Shortcuts automation
  -> HTTPS POST through Tailscale Funnel
  -> isolated ingest service stores a minimal raw event in inbox.db
  -> worker parses, classifies, resolves holds, and writes gas.db
  -> LAN-only web UI
```

Notifications are the core input. CSV import is optional and may be added only for historical backfill and auditing; no normal workflow requires file uploads. There is no email ingestion, bank API, mobile app, or email notification. Funnel must point only to the loopback-published ingest port. Never expose the web UI through Funnel.

## Stack and services

- Python 3.12, FastAPI, SQLAlchemy, Alembic, SQLite, Jinja, HTMX, pytest, and Ruff.
- `web` serves the dashboard and management UI on the LAN. V1 has no login; keep authentication pluggable.
- `ingest` accepts only authenticated `POST /ingest`, has no parser and no access to `gas.db`, and writes only to `inbox.db`.
- `worker` reads and marks inbox events, classifies them, resolves holds and credits, writes `gas.db`, and copies aggregate ingest statistics for the UI.
- The web container never opens `inbox.db`. Both databases use local disk volumes, SQLite WAL, foreign keys, STRICT tables, CHECK constraints, and ISO-8601 timestamps.
- All instants are stored in UTC; `txn_date` is the local date in `America/Toronto`. Money is integer cents, prices are integer thousandths of a dollar per litre, and litres are integer millilitres. Estimated litres are calculated when read, not stored.

## Local development

Use Python 3.12 or newer and run from the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
python -m gastracker
```

The current scaffold health endpoint is `http://127.0.0.1:8000/health`. `.env` is not loaded automatically by the local Python process; export the variables you need in the shell. Public, non-secret settings are in `config.toml`. Set `GASTRACKER_CONFIG` to use another config file.

Run checks with:

```bash
python -m pytest -q
ruff check .
ruff format --check .
DATABASE_PATH=./data/gas.db INBOX_DATABASE_PATH=./data/inbox.db \
  .venv/bin/alembic upgrade head
```

## Initialize the local databases

From the repository root, apply the first Alembic revision to an empty local database pair:

```bash
mkdir -p data
DATABASE_PATH=./data/gas.db INBOX_DATABASE_PATH=./data/inbox.db \
  .venv/bin/alembic upgrade head
```

This creates `gas.db` for the web app and worker, plus `inbox.db` for ingest and worker only. If `gas.db` already exists, Alembic applies the revision in place; it does not replace the file. The inbox path is supplied explicitly so a local migration never writes to the container path `/data/inbox.db`.

Check the applied revision with:

```bash
DATABASE_PATH=./data/gas.db INBOX_DATABASE_PATH=./data/inbox.db \
  .venv/bin/alembic current
```

The initial schema uses SQLite STRICT tables, foreign keys, WAL mode, and CHECK constraints for enum-like values. Run `python -m pytest -q` to verify the schema constraints and migration on disposable test databases. Local database and WAL files are ignored by Git.

## Notification contract

The Shortcut sends only `body` and `notified_at`, for example:

```json
{"body":"$38.15 at Shell\n[Transportation]","notified_at":"2026-11-21T18:52:00-05:00"}
```

The ingest request includes `X-Ingest-Token`, `X-Ingest-Timestamp`, and `X-Ingest-Nonce`. Purchases and credits are parsed by the worker. TD may truncate merchant names at 16 characters and append `...`; matching must be normalized, case-insensitive, and prefix tolerant. A truncated prefix that might be gas or ambiguous must go to review, never be discarded as non-gas. The category hint is supporting evidence only. Unknown merchants tagged `Transportation` go to review unless an explicit `not_gas` rule matches. Account identity is unknown and must not be guessed.

Ingest deduplication uses a hash of the body and notification time rounded to a minute. Every rejection returns the same empty `404`; accepted requests return empty `204`. Validate token, headers, and declared content length before reading the body. Never log request bodies, tokens, rejected secrets, or real notification text.

## Hold handling

Gas and review-candidate purchases start as `pending`. A lone purchase settles after `settle_minutes`; matching unvoided purchases within `sibling_window_minutes` stay pending together to avoid counting both a pay-at-pump hold and its final charge. A same-amount credit from a matching merchant can void the most recent eligible purchase within `hold_void_lookback_hours`, including one already counted. Re-evaluate siblings after a void. Unmatched credits remain pending for `credit_match_grace_minutes`, then enter review. Unresolved purchases enter review after `hold_expiry_days`. Matching is exact-amount, order-independent, idempotent, and reruns on new events and worker ticks. Round-number amounts are only a UI hint, never a classification or exclusion rule.

The reference synthetic case is a `$200.00` Shell hold, a `$38.15` Shell charge, then a `$200.00` Shell credit. The hold and credit are voided; the `$38.15` purchase settles and is counted.

## Security and privacy

- `INGEST_TOKEN` must be a non-placeholder value generated from at least 32 random bytes. The ingest service must refuse to start without it. `INGEST_TOKEN_PREVIOUS` supports rotation; tokens are compared with `hmac.compare_digest`.
- Replay protection is enabled by default: reject timestamps outside the configured window and reused nonces, and purge nonce records after the window. Do not disable it merely because Shortcut support is uncertain.
- Apply global and failed-auth rate budgets before body processing, cap concurrent requests, set timeouts, and use a rejection circuit breaker. Per-client limits depend on verified Funnel forwarding headers; otherwise use global limits.
- The ingest container is non-root, read-only except for its inbox volume, drops all capabilities, uses `no-new-privileges`, and has process, CPU, and memory limits. It has no Docker socket and cannot access `gas.db`.
- Tailscale runs on the host. Once verified, enable the Funnel listener with `sudo tailscale funnel --bg <ingest-host-port>`. Emergency kill switch: `sudo tailscale funnel reset`.
- Store only required fields for gas/review events. Clearly non-gas notifications are counted in aggregates and their inbox rows deleted without persisting the body. Keep parse-failure excerpts short and purge them after 30 days.
- Never commit `.env`, actual notifications, bank data, database files, backups, real Funnel hostnames, or tokens. Use only synthetic fixtures under `tests/fixtures/`. Before each commit, inspect `git status` and stage files by name.

## Configuration and unresolved checks

`config.toml` holds public defaults and seed rules. `[holds]` defines settlement, sibling, credit-match, and expiry windows; `[ingest]` defines body limits, replay protection, rate budgets, timeouts, and breaker thresholds. Merchant seeds include major gas brands, ambiguous brands, and obvious non-gas Transportation merchants. The database is the source of truth after first-run seeding. Remove amount-tolerance reconciliation; hold amounts are never matched loosely.

The following are explicitly unverified and must be checked with placeholders/synthetic requests before enabling Funnel:

- Whether Shortcuts can provide a current timestamp and random nonce in the required headers. `docs/shortcut.md` must explain the test and must not silently weaken replay protection.
- Which client-IP forwarding headers, if any, Tailscale Funnel adds. Inspect with a throwaway echo server; use global limits if no trusted client address is available.
- Notification formats for debit purchases, refunds, and brands beyond the observed Shell credit-card example; whether every hold release emits a credit; and the longest release delay at other stations.

The web UI is LAN-only, including all dashboard, transaction, review, manual-entry, rules, and status routes. The dashboard reports counted monthly spend, fill-ups, average amount, estimated litres, a simple trend, pending purchases, last notification, and rejected requests over the last 24 hours.

## Build order and progress

Each step should have focused tests before it is marked complete:

1. [ ] Complete scaffold and Docker Compose for isolated `web`, `ingest`, and `worker`, health checks, and CI skeleton.
2. [X] Add first Alembic schemas for `inbox.db` and `gas.db`, including STRICT/check-constrained enums.
3. [ ] Implement the minimal hardened ingest service and test client, including identical empty rejections, replay protection, flood limits, and breaker.
4. [ ] Implement notification parsing, merchant classification, idempotency, holds/credits, expiry, statistics, and inbox purging with frozen-clock tests.
5. [ ] Build the LAN-only web UI: dashboard, transactions, review queue, manual entry and prices, merchant rules, and status.
6. [ ] Document exact iOS Shortcut actions in `docs/shortcut.md`, with placeholders only and tests for unverified timestamp/nonce support.
7. [ ] Add a price-source interface, manual prices, government-average importer, merchant price adjustments, and litre overrides.
8. [ ] Finish CasaOS deployment, persistent volumes, backups and restore test, and Funnel instructions for ingest only.
9. [ ] Add structured logs, lint/tests/image/vulnerability scanning in CI, token-rotation drill, and host update notes.
10. [ ] Optional CSV backfill/audit importer: parse in memory, never save the file, use synthetic tests, and protect any balance-based dedupe value with a keyed hash.

### Completed setup checks

- [X] Tailscale installed and tested on the host; Funnel currently reset/off.
- [X] MySpend notification automation and a real notification format were inspected. Keep any real capture out of this public repository.
- [X] TD CSV format references were inspected; this does not make CSV part of the core workflow.