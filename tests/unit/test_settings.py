import os
from unittest.mock import patch

import pytest

from openreversefeed.settings import Settings


def test_defaults():
    with patch.dict(os.environ, {}, clear=True):
        s = Settings()
    assert s.database_url == "postgresql+psycopg://ofr:ofr@localhost:5432/ofr"
    assert s.db_schema == "openreversefeed"
    assert s.storage_driver == "local"
    assert s.storage_base_uri == "file:///tmp/ofr-uploads"
    assert s.publisher == "noop"
    assert s.batch_size == 1000
    assert s.log_level == "INFO"


def test_env_override():
    env = {
        "OFR_DATABASE_URL": "postgresql+psycopg://user:pass@host:5432/db",
        "OFR_PUBLISHER": "webhook",
        "OFR_WEBHOOK_URL": "https://example.invalid/hook",
        "OFR_WEBHOOK_SECRET": "topsecret",
        "OFR_BATCH_SIZE": "2000",
    }
    with patch.dict(os.environ, env, clear=True):
        s = Settings()
    assert s.database_url == env["OFR_DATABASE_URL"]
    assert s.publisher == "webhook"
    assert s.webhook_url == env["OFR_WEBHOOK_URL"]
    assert s.webhook_secret.get_secret_value() == "topsecret"
    assert s.batch_size == 2000


def test_webhook_requires_url_when_selected():
    env = {"OFR_PUBLISHER": "webhook"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="OFR_WEBHOOK_URL"):
            Settings()


def test_sqs_requires_queue_url():
    env = {"OFR_PUBLISHER": "sqs"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="OFR_SQS_QUEUE_URL"):
            Settings()


def test_kafka_requires_brokers_and_topic():
    env = {"OFR_PUBLISHER": "kafka"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="OFR_KAFKA"):
            Settings()
