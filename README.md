# openreversefeed

> **Apache-2.0 Python library** for ingesting Indian mutual fund registrar feed files (CAMS, KFintech) and producing a clean ledger of transactions and FIFO positions — with a transactional outbox for downstream fan-out.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#)

Every wealth platform in India re-implements reverse feed processing from scratch. The logic is intricate — CAMS and KFintech formats differ, reversals, switch transactions, transfers, family PANs, composite keys — and every implementation accumulates patches over time. **openreversefeed** extracts a battle-tested pipeline, streamlines it, and gives you a plug-in library so you can focus on product instead of registrar plumbing.

---

## Quickstart

```bash
# 1. Clone + venv + install
git clone https://github.com/AngelOneWealth/openreversefeed.git
cd openreversefeed
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Bring up the Postgres container (port 5438, persistent volume)
docker compose up -d postgres

# 3. Run migrations
OFR_DATABASE_URL="postgresql+psycopg://ofr:ofr@localhost:5438/ofr" alembic upgrade head

# 4. Generate synthetic CAMS + KFintech + DBF sample files
python tools/generate_samples.py

# 5. Start the Django reference app (separate terminal)
cd examples/django_reference
python manage.py migrate --run-syncdb                 # Django's internal tables (SQLite)
python manage.py ofr_seed                             # Seed 5 AMCs, 5 schemes, 5 accounts
python manage.py runserver 8765

# 6. Open http://127.0.0.1:8765 and upload a file
```

That gives you a working demo with real Postgres, real parsing, real FIFO, real outbox writes — end to end in under 2 minutes.

---

## Architecture

```
                         ┌───────────────────────────────────────────┐
                         │                 User                      │
                         │  (Django reference app / CLI / library)   │
                         └──────────────────┬────────────────────────┘
                                            │ POST /uploads/new/
                                            │ (multipart: file + provider)
                                            ▼
                         ┌───────────────────────────────────────────┐
                         │       Django Reference App                │
                         │  ┌──────────┐ ┌──────────┐ ┌───────────┐  │
                         │  │ Overview │ │Feed Files│ │ Exceptions│  │
                         │  └──────────┘ └──────────┘ └───────────┘  │
                         │          (sidebar nav, filters)           │
                         └──────────────────┬────────────────────────┘
                                            │ ofr_bridge.save_uploaded_file()
                                            │ ofr_bridge.process_source_file()
                                            ▼
  ╔═══════════════════════════════════════════════════════════════════════════╗
  ║                         openreversefeed library                            ║
  ║                                                                             ║
  ║  ┌──────────────────────────────────────────────────────────────────────┐  ║
  ║  │  ReverseFeedService.process_file(path)                                │  ║
  ║  │                                                                        │  ║
  ║  │  1. Fetch         (local or S3/MinIO)                                 │  ║
  ║  │  2. Detect        AdapterRegistry.detect(headers) → priority tiebreak │  ║
  ║  │  3. Parse         CSV / XLS / XLSX / DBF → raw DataFrame              │  ║
  ║  │  4. Normalize     source columns → canonical columns                  │  ║
  ║  │  5. Clean         pair_removal → negative_fix → aggregate → conflict  │  ║
  ║  │  6. Composite key deterministic string, no hash                       │  ║
  ║  │  7. Classify      action + action_tag + is_reversal per adapter       │  ║
  ║  │  8. Prewarm       5 batch queries, PrewarmCache                       │  ║
  ║  │  9. Per-row txn   validate → resolve account → upsert + outbox emit   │  ║
  ║  │  10. FIFO recompute (buy/sell with overselling protection)            │  ║
  ║  └──────────────────────────────────────────────────────────────────────┘  ║
  ║           ↓                                                                  ║
  ║  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐                     ║
  ║  │  Adapters    │  │   Core       │  │     DB        │                     ║
  ║  │              │  │              │  │               │                     ║
  ║  │  CAMS        │  │ composite_key│  │  models.py    │                     ║
  ║  │  KF Format1  │  │ dedup        │  │  session.py   │                     ║
  ║  │  KF Format2  │  │ pair_removal │  │  alembic/     │                     ║
  ║  │  KF CSV      │  │ aggregation  │  │               │                     ║
  ║  │  Registry    │  │ negative_fix │  │               │                     ║
  ║  │  (priority)  │  │ classifier   │  │               │                     ║
  ║  │              │  │ conflict     │  │               │                     ║
  ║  │              │  │ cleaner      │  │               │                     ║
  ║  │              │  │ validator    │  │               │                     ║
  ║  │              │  │ resolver     │  │               │                     ║
  ║  │              │  │ fifo         │  │               │                     ║
  ║  └──────────────┘  └──────────────┘  └───────────────┘                     ║
  ╚═══════════════════════════════════════════════════════════════════════════╝
                                            │
                                            │ SQLAlchemy (per-row txn + audit session)
                                            ▼
  ╔═══════════════════════════════════════════════════════════════════════════╗
  ║                        Postgres 16 (Docker)                                 ║
  ║                                                                             ║
  ║  schema openreversefeed                                                     ║
  ║  ┌────────┐ ┌────────┐ ┌──────┐ ┌──────┐ ┌──────────────┐                  ║
  ║  │accounts│ │ folios │ │amcs  │ │schemes│ │ source_files │  ← UNIQUE       ║
  ║  └────────┘ └────────┘ └──────┘ └──────┘ └──────────────┘    (checksum)    ║
  ║  ┌─────────────┐ ┌───────────────────┐ ┌─────────────────┐                 ║
  ║  │transactions │ │ ingestion_runs    │ │processing_records│                ║
  ║  │             │ │ (per batch audit) │ │(per row audit)  │                 ║
  ║  │ UNIQUE      │ └───────────────────┘ └─────────────────┘                 ║
  ║  │ (registrar, │ ┌───────────────────┐ ┌─────────────────┐                 ║
  ║  │  amc_id,    │ │ correction_queue  │ │   positions     │                 ║
  ║  │ composite_  │ │ (manual review)   │ │ (FIFO state)    │                 ║
  ║  │   key)      │ └───────────────────┘ └─────────────────┘                 ║
  ║  └─────────────┘ ┌──────────────────────────────────┐                      ║
  ║                  │  outbox_events                   │                      ║
  ║                  │  (transactional, FOR UPDATE      │                      ║
  ║                  │   SKIP LOCKED, at-least-once)    │                      ║
  ║                  └──────────────────────────────────┘                      ║
  ╚═══════════════════════════════════════════════════════════════════════════╝
                                            │
                                            │ drained by outbox_worker
                                            ▼
                         ┌───────────────────────────────────────────┐
                         │      Pluggable publisher                  │
                         │  noop · webhook · SQS · Kafka             │
                         │  (at-least-once, dead-letter after N)     │
                         └───────────────────────────────────────────┘
```

---

## Screenshots

The reference Django app — sidebar nav, light theme, real ledger data.

### Overview
Top-line stats + transaction mix + recent files.
![Overview dashboard](docs/screenshots/overview.png)

### Feed Files
Status summary cards (clickable to filter), search, provider / date chips, reprocess action per row, and an inline error preview on failed files.
![Feed Files list](docs/screenshots/feed-files.png)

### File detail
Per-file processing runs, transactions with per-PAN avatar colours, action-coloured amounts, and Download-source / Export-CSV / Reprocess actions.
![File detail](docs/screenshots/file-detail.png)

### Ingest file
Upload form with provider toggle and drag-drop file picker.
![Ingest file](docs/screenshots/ingest.png)

### Exceptions
Manual-review queue for unknown PANs, ambiguous ownership, folio / scheme mismatches.
![Exceptions](docs/screenshots/exceptions.png)

---

## Deep dive — how CAMS and KFintech logic works

For a full walkthrough of the library internals — pipeline steps, field maps,
classification rules (TRFLAG over TD_PURRED precedence for KFintech, direct
type mapping for CAMS), pair-removal algorithms, aggregation grouping keys,
composite key construction, and the KFintech reversal edge cases — read:

**[`src/openreversefeed/README.md`](src/openreversefeed/README.md)**

That's the definitive reference for anyone embedding the library or writing
a new registrar adapter. The summary table below is a quick index.

## Code map — where each piece of logic lives

| What | File | Notes |
|---|---|---|
| **CAMS adapter** (field map, classifier, composite key) | `src/openreversefeed/adapters/cams.py` | priority 100, `USRTRXNO`-based composite key |
| **KFintech Format1 adapter** (`INWARDNUM0` + `TD_TRNO`) | `src/openreversefeed/adapters/kfintech.py` — `KFintechFormat1Adapter` | priority 90, discriminator headers `TD_PURRED` + `TRFLAG` |
| **KFintech Format2 adapter** (`INWARDNO` variant) | same file, `KFintechFormat2Adapter` | priority 80 |
| **KFintech CSV adapter** (English-header variant) | same file, `KFintechCsvAdapter` | priority 70 |
| **Registrar detection** | `src/openreversefeed/adapters/registry.py` | priority-ranked with discriminator-header tiebreak |
| **CAMS classifier** (P/SI/TI/D/BON → buy, R/SO/TO/DP → sell) | `CamsAdapter.classify_row` in `adapters/cams.py` | longest-prefix match for composite codes like `SISF22S` |
| **KFintech classifier** (TRFLAG override → TD_PURRED fallthrough) | `_KFintechBase.classify_row` in `adapters/kfintech.py` | `TI/TO/SI/SO` flags override purred, mode `R` overrides everything |
| **Composite key builder** (deterministic, no hashing) | `src/openreversefeed/core/composite_key.py` | `CAMS: {orig}_{type}_{trxn}_{yyyymmdd}`, `KFintech: {trxn}_{parent}_{folio}_{yyyymmdd}` |
| **In-file deduplication** | `src/openreversefeed/core/dedup.py` | drops duplicate `composite_key`, preserves first occurrence |
| **Redemption+reversal pair removal (KFintech)** | `remove_kfintech_pairs` in `src/openreversefeed/core/pair_removal.py` | vectorized pandas self-merge on `parent_transaction_number`, `folio_number`, opposite-sign within 1e-6 |
| **Redemption+reversal pair removal (CAMS)** | `remove_cams_pairs` in same file | group by `(folio, transaction_type, transaction_number)`, opposite-sign match |
| **Negative-value correction** (both units + amount negative → flip sign, flip type, mark reversal) | `src/openreversefeed/core/negative_fix.py` | uses adapter's `type_flip_map` |
| **Transfer / switch aggregation (KFintech)** | `aggregate_kfintech_transfers` in `src/openreversefeed/core/aggregation.py` | deterministic pre-sort by `(transaction_date, registrar_row_index)` then groupby TI/SI/SO/TO |
| **Switch aggregation (CAMS)** | `aggregate_cams_switches` in same file | SI/SO only, same deterministic pre-sort |
| **KFintech P+SIN conflict resolution** | `src/openreversefeed/core/conflict.py` | resolves P vs SIN dedup inside a single file |
| **Cleaner composition** (the full pipeline) | `src/openreversefeed/core/cleaner.py` | runs pair removal → negative fix → aggregation → conflict → composite key → in-file dedup → classify, in that order |
| **Per-row validator** (required fields, PAN regex, scheme lookup) | `src/openreversefeed/core/validator.py` | raises `ValidationError` with a `CorrectionType` |
| **Family PAN account resolver** | `src/openreversefeed/core/account_resolver.py` | exact ownership → individual fallback → `AmbiguousPanError` |
| **FIFO investment calculator** | `src/openreversefeed/core/fifo.py` | `Decimal` precision, overselling capped at zero |
| **PrewarmCache dataclass** | `src/openreversefeed/core/cache.py` | carries batch lookups between validator / resolver / repo |
| **Canonical enums** (Registrar, Action, TransactionStatus, CorrectionType) | `src/openreversefeed/core/models.py` | `StrEnum` |
| **SQLAlchemy models for all 11 tables** | `src/openreversefeed/db/models.py` | transactions row is the ledger primitive |
| **Alembic initial migration** | `src/openreversefeed/db/alembic/versions/20260414_0001_initial.py` | creates the whole schema via `metadata.create_all` |
| **Runtime settings** (env-driven, publisher validation) | `src/openreversefeed/settings.py` | `pydantic-settings` with `OFR_` prefix |
| **`orf` CLI** | `src/openreversefeed/cli.py` | typer stub, commands wired in later chunks |
| **Synthetic sample generator** (CAMS CSV + KFintech CSV + KFintech DBF) | `tools/generate_samples.py` | all fake `AAAPL*` PANs + `SYN*` scheme codes |
| **End-to-end demo script** | `tools/end_to_end_demo.py` | seeds accounts / AMCs / schemes, runs all three sample files through the full pipeline |
| **Forbidden-strings CI guard** | `tools/check_forbidden_strings.py` | blocks brand names, personal identifiers, real reference data, secrets |
| **Django reference app (demo)** | `examples/django_reference/` | Django 5, SQLAlchemy bridge, no Django ORM for feed data |

---

## What's in the box

### Library (`src/openreversefeed/`)
```
openreversefeed/
├── adapters/           # CAMS + KFintech Format1/Format2/CSV + registry (priority detection)
├── core/               # pure-function cleaner pipeline
│   ├── composite_key.py   # deterministic string keys, no hashing
│   ├── dedup.py           # drop in-file duplicates by composite_key
│   ├── pair_removal.py    # vectorized redemption+reversal pair removal
│   ├── negative_fix.py    # flip sign + type when both units and amount negative
│   ├── aggregation.py     # merge partial transfer/switch rows (deterministic pre-sort)
│   ├── classifier.py      # KFintech TRFLAG override, CAMS direct mapping
│   ├── conflict.py        # KFintech P+SIN dedup
│   ├── cleaner.py         # composes the full pipeline
│   ├── validator.py       # required fields, PAN regex, scheme lookup
│   ├── account_resolver.py # single/family PAN with ownership priority
│   ├── fifo.py            # FIFO investment calculator (Decimal precision)
│   └── cache.py           # PrewarmCache dataclass
├── db/                 # SQLAlchemy 2.0 models + alembic migrations
│   ├── models.py       # 11 tables per design spec §4
│   ├── session.py      # engine + session factory
│   └── alembic/        # initial migration
├── settings.py         # pydantic-settings with publisher validation
└── cli.py              # typer CLI: orf process, migrate, outbox drain
```

### Database schema (Postgres `openreversefeed.*`)
11 tables enforcing the ledger semantics:

| Table | Purpose | Key constraints |
|---|---|---|
| `accounts` | Investor entities | Ownership CHECK |
| `amcs` | AMC registry | `code` UNIQUE |
| `schemes` | Scheme master | `(scheme_code, plan_type, option)` UNIQUE |
| `folios` | Folio per account/AMC | `(account_id, folio_number, amc_id)` UNIQUE |
| `source_files` | Uploaded feed files | Partial unique `(checksum WHERE checksum IS NOT NULL)` — idempotent upload |
| `ingestion_runs` | Per-batch processing log | — |
| `transactions` | The ledger — one row per processed transaction | **`(registrar, amc_id, composite_key)` UNIQUE** — the dedup primitive |
| `positions` | Current FIFO state per account/folio/scheme | `(account_id, folio_id, scheme_id)` UNIQUE |
| `processing_records` | Per-row audit log | — |
| `correction_queue` | Manual review queue for ambiguous PANs, missing data | — |
| `outbox_events` | Transactional outbox for fan-out | `FOR UPDATE SKIP LOCKED` drain |

### Reference Django app (`examples/django_reference/`)
A runnable demo app that uses the library:
- **Overview** — hero stat cards with pulsing live dot, sparklines, transaction mix by provider
- **Feed Files** — list with search box + provider filter chips + status filter chips
- **File detail** — kv-grid metadata + processing runs + transactions with colored avatars
- **Exceptions** — correction queue with status filter
- **Management command** `python manage.py ofr_seed` loads reference data
- **Background worker** `workers/file_worker.py` polls for pending files

### Sample generator (`tools/generate_samples.py`)
Produces synthetic-but-format-accurate sample files. No real investor data is committed to the repo:
- `cams_sample.csv` — CAMS_FORMAT1 layout
- `kfintech_sample.csv` — KFintech CSV layout
- `kfintech_sample.dbf` — **real dBase III file**, the classic KFintech upload format

---

## Supported file formats

| Format | Extension | Reader | Notes |
|---|---|---|---|
| CSV | `.csv` | `pandas.read_csv` | CAMS + KFintech CSV variants |
| Excel 97-2003 | `.xls` | `xlrd` | KFintech legacy |
| Excel 2007+ | `.xlsx` | `openpyxl` | — |
| **dBase III** | `.dbf` | `dbfread` | **The classic KFintech upload format** |

Detection is header-presence based. Adapters declare `mandatory_headers` + `discriminator_headers` and a `priority`; the registry picks the highest-priority matching adapter. See `adapters/registry.py`.

---

## Design highlights

### Deterministic composite keys replace hashing
```
CAMS:     {original_trans_number}_{transaction_type}_{transaction_number}_{YYYYMMDD}
KFintech: {td_trno}_{parent or 0}_{folio}_{YYYYMMDD}
```
Unique across `(registrar, amc_id, composite_key)` — this is the only dedup primitive in the system. `ON CONFLICT DO UPDATE WHERE ... IS DISTINCT FROM` cleanly classifies rows as `new` / `updated` / `noop_duplicate`. No two layers of manual duplicate detection.

### Vectorized pair removal (spec §5 step 4b)
The source implementation uses row-by-row loops for redemption+reversal pair matching. We replace that with a pandas self-merge under a fixed tolerance — one query for the whole file, deterministic under input shuffle, and ~20x faster on large batches.

### Transactional outbox for fan-out
Every write to `transactions` or `positions` emits an `outbox_events` row **in the same DB transaction** — no dual-write problem. A separate drain worker uses `SELECT ... FOR UPDATE SKIP LOCKED` so multiple replicas can drain concurrently without duplicate delivery. Failed events exponential-backoff and eventually move to `status='dead'` after `OFR_OUTBOX_MAX_RETRIES`.

### Audit session for failure logging
`processing_records` entries survive per-row transaction rollbacks. On row failure we switch to a dedicated audit session and write the error row there, so the audit log is always complete even when the data write rolled back.

### Family PAN resolution
Multi-user PAN (HUF / joint holders / minors) resolves by:
1. Exact ownership_type match
2. Default `individual`
3. Ambiguous → correction queue with candidate account IDs

### FIFO cost basis with overselling protection
Decimal-precision FIFO calculator. If a sell exceeds available lots, it caps at zero instead of producing negative positions (the source system's legacy behavior of crashing on negative holdings is fixed).

---

## Configuration

All env vars are `OFR_`-prefixed and read via `pydantic-settings`:

| Env var | Default | Purpose |
|---|---|---|
| `OFR_DATABASE_URL` | `postgresql+psycopg://ofr:ofr@localhost:5432/ofr` | Library's Postgres URL |
| `OFR_DB_SCHEMA` | `openreversefeed` | Schema name |
| `OFR_STORAGE_DRIVER` | `local` | `local` or `s3` |
| `OFR_STORAGE_BASE_URI` | `file:///tmp/ofr-uploads` | Where files land |
| `OFR_S3_ENDPOINT_URL` | *(unset)* | Override for MinIO / LocalStack |
| `OFR_S3_BUCKET` | `ofr-uploads` | S3 bucket |
| `OFR_PUBLISHER` | `noop` | `noop` \| `webhook` \| `sqs` \| `kafka` |
| `OFR_WEBHOOK_URL` | *(unset)* | Required if `publisher=webhook` |
| `OFR_WEBHOOK_SECRET` | *(unset)* | HMAC secret, required if `publisher=webhook` |
| `OFR_SQS_QUEUE_URL` | *(unset)* | Required if `publisher=sqs` |
| `OFR_KAFKA_BROKERS` / `OFR_KAFKA_TOPIC` | *(unset)* | Required if `publisher=kafka` |
| `OFR_BATCH_SIZE` | `1000` | Prewarm batch limit |
| `OFR_OUTBOX_MAX_RETRIES` | `10` | Before moving an event to `status=dead` |

Copy `.env.example` → `.env` to set these for local dev.

---

## Development

```bash
# Install with dev deps
pip install -e ".[dev,s3,kafka]"

# Run the full unit test suite
pytest tests/unit -v
# 95 tests covering core, adapters, FIFO, resolver, validator

# Run integration tests (requires Docker for testcontainers-postgres)
pytest tests/integration -v -m integration

# Start a fresh Postgres for local testing
docker compose up -d postgres
alembic upgrade head

# Generate sample data for the demo
python tools/generate_samples.py

# End-to-end smoke test (script)
python tools/end_to_end_demo.py
```

### Writing a new adapter
A third-party adapter is a single class:

```python
from openreversefeed.adapters.base import FeedAdapter
from openreversefeed.adapters.registry import default_registry
from openreversefeed.core.models import Action, Registrar

class MyAdapter(FeedAdapter):
    name = "my_provider"
    registrar = Registrar.CAMS          # or KFINTECH
    priority = 50                        # higher wins detection ties
    mandatory_headers = {"COL_A", "COL_B"}
    discriminator_headers = {"COL_C"}    # at least one must be present
    field_map = {"COL_A": "transaction_id", "COL_B": "units", ...}
    type_flip_map = {"P": "R", "R": "P"}

    def parse(self, file_path): ...
    def normalize(self, raw): ...
    def classify_row(self, row): return (Action.BUY, "purchase", False)
    def composite_key(self, row): return f"{row['...']}"

default_registry.register(MyAdapter)
```

Then call `ReverseFeedService.process_file()` with `registrar='auto'` and detection picks it up.

---

## Running the Django reference app

```bash
cd examples/django_reference

# Set env (optional, defaults work if Postgres is on 5438)
export OFR_DATABASE_URL="postgresql+psycopg://ofr:ofr@localhost:5438/ofr"

# One-time setup
python manage.py migrate --run-syncdb         # Django's SQLite for sessions/auth
python manage.py ofr_seed                     # Seed reference data into library Postgres

# Start the web server
python manage.py runserver 8765

# (Optional) start the background worker in another terminal
python workers/file_worker.py
```

Visit **http://127.0.0.1:8765**:
- **Overview** — total transactions, feed files, accounts, outbox stats, exception count
- **Feed Files** — search, filter by provider/status, open any file to see its transactions
- **Exceptions** — manual review queue

![Overview dashboard](docs/screenshots/overview.png)
![Feed Files list](docs/screenshots/feed-files.png)

---

## Project status

**Alpha.** Core library + cleaner pipeline + repositories + Django reference app are complete and green-tested. Not yet in v1:

- [ ] Outbox publishers (noop/webhook/sqs/kafka) — scaffolded, need tests
- [ ] Service facade end-to-end integration tests
- [ ] CLI commands beyond stubs (`orf migrate`, `orf process`)
- [ ] Docker compose demo with Django + MinIO + LocalStack orchestrated
- [ ] Docs site (quickstart, architecture, adapters, embedding, operators)
- [ ] PyPI release

Track remaining work on the issue tracker.

---

## License

Apache License 2.0 — see `LICENSE` and `NOTICE`.

No proprietary registrar-supplied files are committed to this repository. All CAMS and KFintech field names referenced here are reconstructed from publicly documented BSE STAR MF field definitions. Synthetic sample files use deliberately fake PAN prefixes (`AAAPL*`) that cannot collide with real investors.
