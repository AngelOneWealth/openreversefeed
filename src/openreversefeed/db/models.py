"""SQLAlchemy declarative models — see docs/superpowers/specs/2026-04-14-openreversefeed-design.md §4."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openreversefeed.db.session import Base


# ---------- §4.1 accounts ----------
class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    pan: Mapped[str | None] = mapped_column(Text)
    ownership_type: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "ownership_type IS NULL OR ownership_type IN "
            "('individual','joint','huf','corporate','minor','nri','custom')",
            name="ck_accounts_ownership_type",
        ),
        Index("ix_accounts_pan", "pan"),
        Index("ix_accounts_pan_ownership", "pan", "ownership_type"),
    )


# ---------- §4.2 amcs ----------
class Amc(Base):
    __tablename__ = "amcs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


# ---------- §4.3 schemes ----------
class Scheme(Base):
    __tablename__ = "schemes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scheme_code: Mapped[str] = mapped_column(Text, nullable=False)
    isin: Mapped[str | None] = mapped_column(Text)
    amc_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("amcs.id", ondelete="RESTRICT", name="fk_schemes_amc_id_amcs"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    plan_type: Mapped[str | None] = mapped_column(Text)
    option: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

    __table_args__ = (
        UniqueConstraint(
            "scheme_code", "plan_type", "option", name="uq_schemes_code_plan_option"
        ),
        Index("ix_schemes_isin", "isin"),
        CheckConstraint(
            "plan_type IS NULL OR plan_type IN ('growth','idcw_payout','idcw_reinvest')",
            name="ck_schemes_plan_type",
        ),
        CheckConstraint(
            "option IS NULL OR option IN ('direct','regular')",
            name="ck_schemes_option",
        ),
    )


# ---------- §4.4 folios ----------
class Folio(Base):
    __tablename__ = "folios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT", name="fk_folios_account_id_accounts"),
        nullable=False,
    )
    folio_number: Mapped[str] = mapped_column(Text, nullable=False)
    amc_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("amcs.id", ondelete="RESTRICT", name="fk_folios_amc_id_amcs"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

    __table_args__ = (
        UniqueConstraint(
            "account_id", "folio_number", "amc_id", name="uq_folios_account_folio_amc"
        ),
        CheckConstraint("source IN ('registrar','manual')", name="ck_folios_source"),
    )


# ---------- §4.5 source_files ----------
class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    registrar: Mapped[str | None] = mapped_column(Text)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "registrar IS NULL OR registrar IN ('cams','kfintech')",
            name="ck_source_files_registrar",
        ),
        CheckConstraint(
            "status IN ('pending','processing','completed','failed')",
            name="ck_source_files_status",
        ),
        Index(
            "uq_source_files_checksum_partial",
            "checksum",
            unique=True,
            postgresql_where=text("checksum IS NOT NULL"),
        ),
    )


# ---------- §4.6 ingestion_runs ----------
class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_file_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "source_files.id",
            ondelete="SET NULL",
            name="fk_ingestion_runs_source_file_id_source_files",
        ),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

    __table_args__ = (
        CheckConstraint(
            "status IN ('running','succeeded','failed')",
            name="ck_ingestion_runs_status",
        ),
    )


# ---------- §4.7 transactions ----------
class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT", name="fk_transactions_account_id_accounts"),
        nullable=False,
    )
    folio_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("folios.id", ondelete="RESTRICT", name="fk_transactions_folio_id_folios"),
        nullable=False,
    )
    scheme_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("schemes.id", ondelete="RESTRICT", name="fk_transactions_scheme_id_schemes"),
        nullable=False,
    )
    amc_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("amcs.id", ondelete="RESTRICT", name="fk_transactions_amc_id_amcs"),
        nullable=False,
    )
    source_file_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "source_files.id",
            ondelete="SET NULL",
            name="fk_transactions_source_file_id_source_files",
        ),
    )
    ingestion_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "ingestion_runs.id",
            ondelete="SET NULL",
            name="fk_transactions_ingestion_run_id_ingestion_runs",
        ),
    )

    registrar: Mapped[str] = mapped_column(Text, nullable=False)
    composite_key: Mapped[str] = mapped_column(Text, nullable=False)
    registrar_transaction_id: Mapped[str] = mapped_column(Text, nullable=False)
    registrar_transaction_number: Mapped[str | None] = mapped_column(Text)
    parent_transaction_number: Mapped[str | None] = mapped_column(Text)
    parent_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "transactions.id",
            ondelete="RESTRICT",
            name="fk_transactions_parent_transaction_id_transactions",
        ),
    )

    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    nav: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    units: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)

    action: Mapped[str] = mapped_column(Text, nullable=False)
    action_tag: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    broker_code: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "registrar", "amc_id", "composite_key", name="uq_transactions_registrar_amc_composite"
        ),
        CheckConstraint("registrar IN ('cams','kfintech')", name="ck_transactions_registrar"),
        CheckConstraint("action IN ('buy','sell','no_effect')", name="ck_transactions_action"),
        CheckConstraint(
            "status IN ('pending','successful','reversed','failed')",
            name="ck_transactions_status",
        ),
        Index(
            "ix_transactions_registrar_amc_reg_txn_id",
            "registrar",
            "amc_id",
            "registrar_transaction_id",
        ),
        Index(
            "ix_transactions_registrar_amc_reg_txn_number",
            "registrar",
            "amc_id",
            "registrar_transaction_number",
        ),
        Index("ix_transactions_account_scheme", "account_id", "scheme_id"),
        Index("ix_transactions_status_date", "status", "transaction_date"),
        Index("ix_transactions_folio", "folio_id"),
        Index("ix_transactions_parent", "parent_transaction_id"),
    )


# ---------- §4.8 positions ----------
class Position(Base):
    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT", name="fk_positions_account_id_accounts"),
        nullable=False,
    )
    folio_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("folios.id", ondelete="RESTRICT", name="fk_positions_folio_id_folios"),
        nullable=False,
    )
    scheme_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("schemes.id", ondelete="RESTRICT", name="fk_positions_scheme_id_schemes"),
        nullable=False,
    )
    units: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    cost_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    last_transaction_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "account_id", "folio_id", "scheme_id", name="uq_positions_account_folio_scheme"
        ),
        CheckConstraint(
            "source IS NULL OR source IN ('reverse_feed','manual','api')",
            name="ck_positions_source",
        ),
    )


# ---------- §4.9 processing_records ----------
class ProcessingRecord(Base):
    __tablename__ = "processing_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ingestion_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "ingestion_runs.id",
            ondelete="RESTRICT",
            name="fk_processing_records_ingestion_run_id_ingestion_runs",
        ),
        nullable=False,
    )
    source_file_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "source_files.id",
            ondelete="SET NULL",
            name="fk_processing_records_source_file_id_source_files",
        ),
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    composite_key: Mapped[str | None] = mapped_column(Text)
    transaction_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "transactions.id",
            ondelete="SET NULL",
            name="fk_processing_records_transaction_id_transactions",
        ),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('success','skipped_duplicate','queued_correction','failed')",
            name="ck_processing_records_status",
        ),
    )


# ---------- §4.10 correction_queue ----------
class CorrectionQueue(Base):
    __tablename__ = "correction_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_file_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "source_files.id",
            ondelete="RESTRICT",
            name="fk_correction_queue_source_file_id_source_files",
        ),
    )
    ingestion_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "ingestion_runs.id",
            ondelete="RESTRICT",
            name="fk_correction_queue_ingestion_run_id_ingestion_runs",
        ),
    )
    correction_type: Mapped[str] = mapped_column(Text, nullable=False)
    pan: Mapped[str | None] = mapped_column(Text)
    candidate_account_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    selected_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "accounts.id",
            ondelete="RESTRICT",
            name="fk_correction_queue_selected_account_id_accounts",
        ),
    )
    record_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_by: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "correction_type IN ('duplicate_pan','pan_not_found','user_mismatch',"
            "'folio_mismatch','scheme_not_found','transfer_in_unmatched','other')",
            name="ck_correction_queue_type",
        ),
        CheckConstraint(
            "status IN ('pending','resolved','skipped')",
            name="ck_correction_queue_status",
        ),
    )


# ---------- §4.11 outbox_events ----------
class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','published','dead')",
            name="ck_outbox_events_status",
        ),
        Index("ix_outbox_events_status_retry", "status", "next_retry_at"),
        Index("ix_outbox_events_aggregate", "aggregate_id"),
    )
