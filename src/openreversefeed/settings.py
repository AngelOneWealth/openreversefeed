"""Runtime settings, loaded from environment variables with OFR_ prefix."""
from __future__ import annotations

from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PublisherName = Literal["noop", "webhook", "sqs", "kafka"]
StorageDriver = Literal["local", "s3"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OFR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+psycopg://ofr:ofr@localhost:5432/ofr"
    db_schema: str = "openreversefeed"

    # Storage
    storage_driver: StorageDriver = "local"
    storage_base_uri: str = "file:///tmp/ofr-uploads"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "ofr-uploads"
    aws_region: str = "ap-south-1"

    # Publisher
    publisher: PublisherName = "noop"
    webhook_url: str | None = None
    webhook_secret: SecretStr | None = None
    webhook_timeout_sec: int = 10
    webhook_max_skew_sec: int = 300
    sqs_queue_url: str | None = None
    kafka_brokers: str | None = None
    kafka_topic: str | None = None

    # Pipeline
    batch_size: int = 1000

    # Outbox
    outbox_batch_size: int = 100
    outbox_idle_sleep_sec: int = 5
    outbox_busy_sleep_sec: int = 1
    outbox_max_retries: int = 10

    # Observability
    log_level: str = "INFO"
    otel_enabled: bool = False

    @model_validator(mode="after")
    def _check_publisher_deps(self) -> "Settings":
        if self.publisher == "webhook":
            if not self.webhook_url:
                raise ValueError("OFR_WEBHOOK_URL is required when OFR_PUBLISHER=webhook")
            if not self.webhook_secret:
                raise ValueError("OFR_WEBHOOK_SECRET is required when OFR_PUBLISHER=webhook")
        if self.publisher == "sqs" and not self.sqs_queue_url:
            raise ValueError("OFR_SQS_QUEUE_URL is required when OFR_PUBLISHER=sqs")
        if self.publisher == "kafka":
            if not self.kafka_brokers or not self.kafka_topic:
                raise ValueError(
                    "OFR_KAFKA_BROKERS and OFR_KAFKA_TOPIC are required when OFR_PUBLISHER=kafka"
                )
        return self
