# openreversefeed

Apache-2.0 Python library for ingesting Indian mutual fund registrar (CAMS, KFintech) feed files and producing a clean ledger of transactions and FIFO positions.

## Status

**Alpha — under active development.** See `docs/superpowers/plans/2026-04-14-openreversefeed.md` for the implementation plan.

## What it does

- Parses CAMS and KFintech (formerly KARVY) reverse feed files across multiple formats
- Deduplicates, aggregates, and classifies transactions with a pure-function cleaner pipeline
- Computes FIFO positions per (account, folio, scheme)
- Writes to Postgres with a transactional outbox for fan-out to downstream services
- Ships with a runnable Django reference app and `docker compose up` demo

## Full docs coming soon

See `docs/` once published. In the meantime, refer to the design spec:
`docs/superpowers/specs/2026-04-14-openreversefeed-design.md`

## License

Apache-2.0. See `LICENSE` and `NOTICE`.
