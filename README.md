# Gas Spending Tracker

A self-hosted, single-user web app that tracks how much you spend on gas, estimates the litres you bought, and runs in Docker on a ZimaBlade with CasaOS.

> **Status:** Step 1 scaffold is implemented. Domain tables, CSV import, and the dashboard are not built yet. See [Development steps](#development-steps) for the build order.

## Run the scaffold

Run these commands from the repository root. Use Python 3.12 (the Docker image uses 3.12; newer Python versions are also accepted by the package).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
set -a
source .env
set +a
python -m gastracker
```

Open http://127.0.0.1:8000/docs for the scaffold's API documentation, or test it from a second terminal:

```bash
curl --fail http://127.0.0.1:8000/health
```

Expected response: `{"status":"ok","timezone":"America/Toronto"}`. The root URL `/` returns 404 until the web UI is implemented in Step 6. Stop the server with Ctrl+C.

The app loads public settings from `config.toml` (relative to the current directory). `GASTRACKER_CONFIG` selects another file. Environment variables `APP_NAME`, `APP_TIMEZONE`, `APP_LOG_LEVEL`, `DATABASE_PATH`, `WEB_HOST`, and `WEB_PORT` override the corresponding TOML values. `.env` is not loaded automatically; the shell commands above export it. The example uses a local `./data/gas.db` rather than the container-only `/data/gas.db`. Application dates should use the configured `ZoneInfo` timezone, including Toronto daylight-saving changes.

### Automated checks

With the virtual environment active:

```bash
python -m pytest -q
ruff check .
ruff format --check .
DATABASE_PATH=./data/gas.db alembic upgrade head
DATABASE_PATH=./data/gas.db alembic check
```

The tests cover the health endpoint, environment overrides, timezone validation and daylight saving, SQLite connectivity, and Alembic startup. Alembic currently has no revisions or domain tables; `upgrade head` only validates the migration wiring, and `check` should report no new upgrade operations. The first schema migration belongs to Step 2.

### Docker setup on Arch Linux (once per machine)

Docker must be installed on the host; the project's Dockerfile does not install Docker itself. These are the setup steps used on the Arch Linux development machine:

```bash
sudo pacman -Syu docker docker-buildx
sudo systemctl enable --now docker.service
sudo docker version
sudo docker buildx version
sudo docker info
```

`enable --now` starts the daemon immediately and enables it at boot. Buildx provides the current BuildKit image builder and avoids the legacy-builder deprecation warning. The commands below use `sudo` because Docker socket access requires elevated privileges with this setup; adding yourself to the `docker` group is not necessary and would grant effectively root-level access.

### Build the image

From the repository root:

```bash
sudo docker buildx build --load --progress=plain -t gastracker:dev .
```

This builds the application into an image named `gastracker:dev` and loads it into the local Docker engine. The first build downloads Python 3.12 and the Python dependencies; later builds reuse cached layers. `--progress=plain` shows which operation is running. Wait for a successful finish before running the container. A host Python installation or virtual environment is not needed for this Docker path.

### Run and test the container

```bash
sudo docker run --rm --name gastracker \
  -p 127.0.0.1:8001:8000 \
  -v gastracker-data:/data \
  gastracker:dev
```

`docker run` creates and starts a container from the image. Keep this terminal open while testing. Host port **8001** is used because the local Python server already occupied port 8000 during setup; the container still listens on port 8000 internally. The named volume `gastracker-data` is created automatically on first use and retains `/data` across container runs. The image runs the application as a non-root user even though the host Docker command uses `sudo`.

From a second terminal:

```bash
curl --fail http://127.0.0.1:8001/health
sudo docker ps --filter name=gastracker
sudo docker inspect --format '{{.State.Health.Status}}' gastracker
```

The health endpoint should return `{"status":"ok","timezone":"America/Toronto"}`. The container healthcheck runs every 30 seconds, so its status can initially be `starting`. API documentation is at http://127.0.0.1:8001/docs. The root URL http://127.0.0.1:8001/ currently returns `{"detail":"Not Found"}` because no homepage has been implemented; this is not a Docker failure.

The port is published on loopback only for this smoke test. Never point Tailscale Funnel at this web service. Compose, LAN deployment, and the isolated ingest/worker containers belong to later steps.

### Stop the servers

Stop the container from a second terminal:

```bash
sudo docker stop gastracker
```

Because it was started with `--rm`, Docker removes the stopped container, but keeps the image and the named data volume. Start it again with the same `docker run` command, not `docker start`. This test container does not restart automatically after a reboot. To stop a separate local Python server, press Ctrl+C in the terminal running `python -m gastracker` (or terminate the VS Code run task).

### When to repeat each step

| Change or event | What to repeat |
|---|---|
| Normal development session, no file changes | Run the existing image with `docker run`; no build or installation needed. |
| Application code, templates, dependency declarations, Dockerfile, migrations, or `config.toml` changes | Rebuild the image, stop the old container, and run a new one. These files are copied into the image; this setup has no live reload or source bind mount. Rebuilding does not update an already-running container. |
| Host port, volume mapping, or environment variable changes | Stop and recreate the container with updated `docker run` arguments; no image rebuild needed. Pass environment overrides with `-e NAME=value`. The current run command does not automatically load the host `.env`. |
| Machine reboot | The enabled Docker service starts automatically. Run the container again when needed. |
| New development machine | Install Docker and Buildx, enable the service, then build and run. |
| Base-image or dependency security refresh | Rebuild periodically, for example monthly and promptly after relevant security advisories, using the command below; then stop and recreate the container. |

```bash
sudo docker buildx build --load --pull --no-cache --progress=plain -t gastracker:dev .
```

`--pull` refreshes the Python base image and `--no-cache` reruns dependency installation. Normal builds can omit both flags. Dependencies currently use version ranges rather than a lockfile, so fresh dependency resolution can select newer compatible releases; run the tests after updating. Once schema migrations exist, a rebuild alone will not apply them; follow the migration instructions introduced with Step 2. Stopping, removing, or rebuilding the container does not delete `gastracker-data`. Do not remove that volume unless you intend to delete its stored data.

### Setup troubleshooting

- `docker: command not found`: install Docker using the Arch setup commands above.
- Legacy-builder warning or missing `docker buildx`: install `docker-buildx`.
- Cannot connect to the Docker daemon: check `systemctl is-active docker.service` and start it with `sudo systemctl start docker.service` if inactive.
- Permission denied accessing the Docker socket: use `sudo docker ...` with this setup.
- `address already in use`: stop the process using the host port, or change only the host side of the mapping, for example `-p 127.0.0.1:8002:8000`, and browse port 8002.
- A pasted command starts with `^[[200~` or ends with an unexpected `~`: cancel with Ctrl+C and enter the clean command again; those are not part of Docker's syntax.

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
  -> ingest service on the ZimaBlade stores the raw request in an inbox
  -> a separate worker parses it into a provisional transaction
  -> next CSV import confirms it with the posted amount
```

Why this shape:

- **The phone does not run Tailscale.** The iPhone only needs normal cellular data. The trade-off is that the ingest endpoint is public, which is why the [authentication and hardening plan](#authentication-and-hardening-plan) below matters.
- The CSV is the backstop. If the server is off or the phone has no signal, the CSV import still records the purchase.
- Pay-at-pump pre-authorizations can differ from the final charge, so the CSV row wins when the two are reconciled.

### Fallbacks if the notification trigger is not workable

- **Wallet "Transaction" trigger** (Shortcuts): fires on Apple Pay tap-to-pay and passes merchant and amount directly. Only works if the card is in Apple Wallet and you pay with it. It feeds the same `/ingest` endpoint.
- **CSV-only**: the tracker is fully usable without any real-time capture.

### Considered and not chosen: Tailscale on the phone

Installing Tailscale on the iPhone would remove the public endpoint entirely (only your own devices could reach the service). Tailscale's iOS app has VPN On Demand, which addresses most of the "VPN might be off" concern. It was not chosen because the phone app will not be installed. Possible downsides of that route are a race between the tunnel coming up and the first request, battery or connectivity quirks, and only one On Demand VPN app being allowed at a time.

The ingest service should be written so it can be moved behind a tailnet-only address later without code changes (only `PUBLIC_BASE_URL` and the Funnel setting change).

## Architecture

- **Language/stack:** Python 3.12, FastAPI, SQLAlchemy + Alembic, SQLite.
- **UI:** server-rendered (Jinja + HTMX). No JavaScript build step.
- **Three pieces in one compose file:**
  - `web`: dashboard, upload page, transaction list, review queue. Bound to the LAN only. **Not exposed to the internet.**
  - `ingest`: a tiny, isolated listener that accepts only `POST /ingest`, checks authentication, and drops the raw request into an inbox. It does **no parsing** and has **no access to the main database**. This is the only thing exposed through Tailscale Funnel.
  - `worker`: reads the inbox, parses and classifies each entry, and writes provisional transactions to the main database.
- **Storage:** SQLite file on a mounted `/data` volume, with a nightly `.backup` to another folder. The inbox lives in a separate small file or volume that the ingest container can write to and the worker can read.
- **Timezone:** America/Toronto.

## Authentication and hardening plan

The ingest endpoint is public (Tailscale Funnel gives it an HTTPS address that anyone with the hostname can reach). The hostname is discoverable: it appears in public certificate logs, and scanner probes were already seen minutes after the first test. So the design assumes the URL is known and relies on the token, not on obscurity.

### What is exposed and what can go wrong

- **Exposed:** one write-only route. No pages, no GET routes, no stored data to read. The web UI, database, and other CasaOS apps are not reachable through Funnel.
- **Fake purchases:** needs the token. Anything received is provisional and flagged until matched to a CSV row, so the impact is junk rows.
- **Flooding:** a token does not stop requests from arriving, only from succeeding. Mitigated with rate limits, resource caps, and a circuit breaker (below). Worst case is a slow ingest service and some missed real-time captures, which the CSV import recovers.
- **A bug in the ingest code:** the one real risk of any internet-facing service. Mitigated by keeping the service tiny, isolating it, and keeping parsing out of it.
- **Token leak:** via a shared shortcut, a committed `.env`, or a screenshot. Mitigated by rotation (below).

### Authentication layers

1. **Header token.** A long random secret (32+ bytes, generated with `secrets.token_urlsafe(32)`) sent in the `X-Ingest-Token` header, never in the URL. URLs end up in logs and browser history; headers usually do not.
2. **Constant-time comparison.** Compare with `hmac.compare_digest`. Reject with the same empty 404 whether the path or the token is wrong.
3. **Check before reading.** Validate the token, headers, and declared body size *before* reading or parsing the body.
4. **Replay protection.** Require `X-Ingest-Timestamp` (reject if more than about 5 minutes off the server clock) and a unique `X-Ingest-Nonce` (reject any nonce already seen in that window). A captured request then cannot be replayed. *Needs testing:* confirm Shortcuts can send a current-date header and a random nonce. If Shortcuts can compute an HMAC, a signed request is an optional upgrade, but this has not been verified.
5. **Token rotation.** The service accepts two tokens at once, `INGEST_TOKEN` (current) and `INGEST_TOKEN_PREVIOUS` (optional, only during a rotation). Rotation procedure: generate a new token, move the old one to `INGEST_TOKEN_PREVIOUS`, put the new one in `INGEST_TOKEN`, restart, update the shortcut, then clear `INGEST_TOKEN_PREVIOUS`. Rotate immediately if a leak is suspected.
6. **Optional secret path segment.** `INGEST_PATH_SECRET` makes the route `/ingest/<value>`. This only reduces scanner noise and is weaker than the header token, since paths show up in more places. Treat it as a bonus, not a defense.

### Limiting what a flood or a bug can do

- **Dumb inbox design.** The ingest service only authenticates, enforces size limits, and stores the raw request. A separate worker parses it. A parsing bug cannot be reached from the internet.
- **Hardened container.** Non-root user, read-only root filesystem, all Linux capabilities dropped, `no-new-privileges`, a process-count limit, no Docker socket, and write access only to the inbox. No access to the main database.
- **Resource limits.** CPU and memory limits on the ingest container so a flood cannot starve the rest of the ZimaBlade.
- **Request limits.** Tiny body-size cap (see `config.toml`), request and connection timeouts (to handle slow or half-open connections), and a cap on concurrent connections.
- **Rate limiting.** Applied before any other work, with a tight separate budget for failed authentication attempts. Per-client limits only work if Funnel passes the real client IP to the service. The test server log only showed `127.0.0.1`, so this is **unverified**; check which forwarding headers Funnel sends and fall back to global limits if there are none.
- **Circuit breaker.** If rejected requests spike past a threshold, the service returns an immediate empty 404 for everything until traffic calms down. Failing closed costs little because the CSV import is the backstop.
- **Kill switch.** `sudo tailscale funnel reset` turns the public address off instantly.

### Data minimization and visibility

- The shortcut sends only what the app needs: merchant, amount, and date. Do not send card digits or other fields from the notification.
- Log rejected requests (path, status, timing) but **never request bodies**.
- Dashboard shows "last ingest received" and "rejected requests in the last 24 hours", so probing or an outage is visible.
- Funnel traffic passes through Tailscale's infrastructure, so assume the notification text is visible there in some form, and keep the payload minimal.

### Housekeeping

- Secrets live only in `.env` and the iPhone shortcut. Never share the shortcut or its iCloud link (it contains the hostname and token), and never screenshot them.
- Pin dependencies, rebuild the image regularly, and scan it for vulnerabilities in CI (for example with Trivy).
- Turn on automatic security updates on the ZimaBlade.
- Only the ingest port is ever pointed at by Funnel. Never the web UI port.
- Optional: rename the machine in Tailscale so the public hostname does not advertise "casaos".

### Considered and not used

- **IP allowlisting:** cellular addresses change constantly and Funnel may hide the source address anyway.
- **Client certificates:** no practical way to use them from Shortcuts (not confirmed).
- **Stacking more secrets** (extra paths, extra headers): little gain over one strong token.

## Data model (draft)

All money is stored as integer cents.

- `transactions`: id, account, source (`csv` / `ingest` / `manual`), status (`provisional` / `confirmed`), date, amount_cents, merchant_raw, merchant_normalized, category (`gas` / `not_gas` / `needs_review`), card_type (`credit` / `debit`), estimated_litres, price_per_litre_used, litres_override, import_key
- `merchant_rules`: pattern, category, priority (editable in the UI, not hardcoded)
- `gas_prices`: date, region/station, grade, price_per_litre_cents, source
- `parse_failures`: source, raw_text, error, created_at
- `ingest_inbox` (separate store, written by `ingest`, read by `worker`): id, received_at, raw_body, processed (bool), error

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

1. [X] Create a free Tailscale account, install it on the ZimaBlade, and enable Funnel in the admin console.
2. [ ] Turn on MySpend transaction notifications. Build a test Shortcuts automation (notification trigger that appends Title, Body, and Date to a note) and capture what a real fill-up notification looks like.
3. [X] Export fresh TD CSVs (credit and debit) as format references.

### Phase A: CSV-first tracker

1. [X] **Project scaffold:** Python 3.12, FastAPI, SQLAlchemy + Alembic, pytest, linter, Dockerfile from day one, timezone set.
2. [ ] **Database schema and migrations.** *Done when:* migrations run on an empty database.
3. [ ] **TD CSV parsers:** `td_credit` and `td_debit` profiles, dedupe key, balance check, synthetic test fixtures. *Done when:* both formats parse correctly and overlapping imports create no duplicates.
4. [ ] **Gas classifier:** rules table, three outcomes, small-amount check.
5. [ ] **Import pipeline:** upload, parse in memory, classify, store only gas and needs-review rows, discard the file.
6. [ ] **Web UI v1:** CSV upload with account dropdown, transaction list with edit, needs-review queue, parse-failure list, manual add, basic dashboard (monthly spend, fill-up count, average per fill-up), "last import" indicator with a suggested start date for the next export. *Done when:* you can upload a CSV and see your gas history.

### Phase B: real-time capture

7. [ ] **Ingest service and worker:** implement the [authentication and hardening plan](#authentication-and-hardening-plan): `POST /ingest` only, header token with constant-time check, timestamp and nonce replay protection, two-token rotation, size and rate limits, circuit breaker, hardened and resource-limited container, raw-request inbox, and a separate worker that parses notifications into provisional rows. *Done when:* a request from outside your home network creates a provisional row, and requests with a bad token, stale timestamp, reused nonce, or oversized body are rejected with an empty 404.
8. [ ] **Reconciliation:** match provisional rows to CSV rows (same amount, date within a day or two, similar merchant), promote to confirmed with the posted amount, and list unmatched ones for review.
9. [ ] **iPhone shortcut:** notification-triggered automation that POSTs to the Funnel URL with the token, timestamp, and nonce headers, set to run without asking. *Done when:* a real fill-up appears in the app within about a minute.

### Phase C: prices and deployment

10. [ ] **Gas prices and estimated litres:** price-source plugin, litres estimate, manual override, per-merchant adjustment.
11. [ ] **Deployment:** compose file with the three pieces, persistent `/data` volume, env vars for the tokens, healthcheck, restart policy, container resource limits. Import into CasaOS, point Funnel at the ingest port only, schedule nightly SQLite backups, and test a restore.
12. [ ] **Hardening:** structured logging, "last ingest received" and "rejected requests" indicators, rotation drill (practice the token rotation once), parser tests for new formats, small CI pipeline (lint, tests, image build, vulnerability scan), dependency pinning, automatic OS updates.

## Open decisions

- **Step 6:** does the web UI need a login, or is LAN-only enough?
- **Step 7:** exact notification format (depends on the Step 0 screenshot).
- **Step 7:** can Shortcuts send a current-date header and a random nonce (needed for replay protection)? Can it compute an HMAC? Test before committing to a signed-request design.
- **Step 7:** does Funnel forward the real client IP (for per-client rate limits)? Check the headers Funnel adds.
- **Step 10:** start with government average prices (recommended) or look for a station-level source?
- **Debit gas purchases:** no example seen yet. Export a range that includes one so the debit gas format can be confirmed. Until then, ship credit-first.

## Risks

- **Notification trigger is best-effort.** A developer reported dropped runs for rapid-fire notifications with no error. The CSV reconciliation is the safety net.
- **MySpend reliability.** At least one recent review says its notifications stopped sending. Test before depending on it.
- **Bank format changes.** Parser failures go to `parse_failures` instead of being dropped, and imports can be re-run.
- **Public endpoint.** A token does not prevent flooding, only misuse. Mitigated by rate limits, resource caps, the circuit breaker, a minimal and isolated ingest service, provisional-only data, and keeping the UI off Funnel. Residual risk is a software vulnerability in the service or its dependencies.
- **Server availability.** If the ZimaBlade is off, real-time events are lost until the next CSV import.

## Progress checklist

- [ ] Step 0: Tailscale + Funnel, test notification automation, fresh CSV exports
- [X] Step 1: scaffold and Docker
- [ ] Step 2: schema and migrations
- [ ] Step 3: TD CSV parsers
- [ ] Step 4: gas classifier
- [ ] Step 5: import pipeline
- [ ] Step 6: web UI v1
- [ ] Step 7: ingest service and worker (auth and hardening)
- [ ] Step 8: reconciliation
- [ ] Step 9: iPhone shortcut
- [ ] Step 10: gas prices and litres
- [ ] Step 11: CasaOS deployment and backups
- [ ] Step 12: hardening and CI
