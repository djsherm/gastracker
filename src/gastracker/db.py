"""SQLAlchemy models and SQLite connection setup."""

from sqlalchemy import (
    URL,
    CheckConstraint,
    Engine,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gastracker.config import Settings


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = {"sqlite_strict": True}

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class MerchantRule(Base):
    __tablename__ = "merchant_rules"
    __table_args__ = (
        CheckConstraint("match_type IN ('prefix', 'contains', 'regex')"),
        CheckConstraint("category IN ('gas', 'not_gas', 'needs_review')"),
        CheckConstraint("enabled IN (0, 1)"),
        {"sqlite_strict": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    match_type: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    min_amount_cents: Mapped[int | None] = mapped_column(Integer)
    price_adjustment_milli: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("source IN ('ingest', 'manual', 'csv')"),
        CheckConstraint("kind IN ('purchase', 'credit')"),
        CheckConstraint("status IN ('pending', 'counted', 'voided', 'review')"),
        CheckConstraint("category IN ('gas', 'not_gas', 'needs_review')"),
        CheckConstraint("category_locked IN (0, 1)"),
        CheckConstraint("merchant_truncated IN (0, 1)"),
        CheckConstraint("amount_cents > 0"),
        Index("ix_transactions_status_occurred", "status", "occurred_at"),
        Index("ix_transactions_merchant_amount", "merchant_normalized", "amount_cents"),
        {"sqlite_strict": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))
    source: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    txn_date: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[str] = mapped_column(Text, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    merchant_raw: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_truncated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    category_locked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("merchant_rules.id"))
    bank_category_hint: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    inbox_id: Mapped[int | None] = mapped_column(Integer)
    settle_at: Mapped[str | None] = mapped_column(Text)
    price_per_litre_milli: Mapped[int | None] = mapped_column(Integer)
    price_source: Mapped[str | None] = mapped_column(Text)
    litres_ml_override: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class TransactionLink(Base):
    __tablename__ = "transaction_links"
    __table_args__ = (
        CheckConstraint("type IN ('void_hold', 'csv_match')"),
        {"sqlite_strict": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    to_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class GasPrice(Base):
    __tablename__ = "gas_prices"
    __table_args__ = (
        CheckConstraint("price_milli > 0"),
        UniqueConstraint("price_date", "region", "brand", "grade", "source"),
        {"sqlite_strict": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    price_date: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(Text)
    grade: Mapped[str] = mapped_column(Text, nullable=False)
    price_milli: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[str] = mapped_column(Text, nullable=False)


class ParseFailure(Base):
    __tablename__ = "parse_failures"
    __table_args__ = (
        CheckConstraint("resolved IN (0, 1)"),
        {"sqlite_strict": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class IngestStatsSummary(Base):
    __tablename__ = "ingest_stats_summary"
    __table_args__ = {"sqlite_strict": True}

    day: Mapped[str] = mapped_column(Text, primary_key=True)
    accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_by_reason: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


def create_database_engine(settings: Settings) -> Engine:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(settings.database_path)),
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine
