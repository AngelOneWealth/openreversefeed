import pytest

from openreversefeed.adapters.base import FeedAdapter
from openreversefeed.adapters.registry import AdapterRegistry, UnknownFormatError
from openreversefeed.core.models import Action, Registrar


def _make_adapter(name, priority, mandatory, discriminator=None, registrar=Registrar.CAMS):
    class _A(FeedAdapter):
        def parse(self, file_path):  # pragma: no cover
            raise NotImplementedError

        def normalize(self, raw):  # pragma: no cover
            return raw

        def pair_strategy(self):  # pragma: no cover
            return None  # type: ignore[return-value]

        def aggregation_strategy(self):  # pragma: no cover
            return None  # type: ignore[return-value]

        def classify_row(self, row):  # pragma: no cover
            return Action.NO_EFFECT, "other", False

        def composite_key(self, row):  # pragma: no cover
            return ""

    _A.name = name
    _A.registrar = registrar
    _A.priority = priority
    _A.mandatory_headers = set(mandatory)
    _A.discriminator_headers = set(discriminator or [])
    _A.field_map = {}
    _A.type_flip_map = {}
    return _A


def test_detect_unique_match():
    reg = AdapterRegistry()
    reg.register(_make_adapter("A", 10, {"X", "Y"}))
    assert reg.detect({"X", "Y", "Z"}).name == "A"


def test_detect_no_match_raises():
    reg = AdapterRegistry()
    reg.register(_make_adapter("A", 10, {"X", "Y"}))
    with pytest.raises(UnknownFormatError) as exc_info:
        reg.detect({"Z"})
    assert "Z" in str(exc_info.value)


def test_detect_priority_tiebreak():
    reg = AdapterRegistry()
    reg.register(_make_adapter("low", 5, {"X"}))
    reg.register(_make_adapter("high", 10, {"X"}))
    assert reg.detect({"X", "Z"}).name == "high"


def test_detect_requires_all_mandatory():
    reg = AdapterRegistry()
    reg.register(_make_adapter("A", 10, {"X", "Y", "Z"}))
    with pytest.raises(UnknownFormatError):
        reg.detect({"X", "Y"})


def test_detect_discriminator_required():
    reg = AdapterRegistry()
    reg.register(_make_adapter("A", 10, mandatory={"X"}, discriminator={"D1", "D2"}))
    with pytest.raises(UnknownFormatError):
        reg.detect({"X"})
    assert reg.detect({"X", "D1"}).name == "A"


def test_detect_name_tiebreak_when_priority_equal():
    reg = AdapterRegistry()
    reg.register(_make_adapter("bravo", 10, {"X"}))
    reg.register(_make_adapter("alpha", 10, {"X"}))
    assert reg.detect({"X"}).name == "alpha"
